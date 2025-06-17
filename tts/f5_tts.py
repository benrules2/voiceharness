import argparse
from collections import deque
import datetime
import pkgutil
import re
import sys
from threading import Event, Lock
from typing import Literal, Optional

import mlx.core as mx
import numpy as np

from f5_tts_mlx.cfm import F5TTS
from f5_tts_mlx.utils import convert_char_to_pinyin

import sounddevice as sd
import soundfile as sf

from tqdm import tqdm

SAMPLE_RATE = 24_000
HOP_LENGTH = 256
FRAMES_PER_SEC = SAMPLE_RATE / HOP_LENGTH
TARGET_RMS = 0.1


# utilities


def split_sentences(text):
    sentence_endings = re.compile(r"([.!?;:])")
    sentences = sentence_endings.split(text)
    sentences = [
        sentences[i] + sentences[i + 1] for i in range(0, len(sentences) - 1, 2)
    ]
    return [sentence.strip() for sentence in sentences if sentence.strip()]


def estimated_duration(ref_audio: mx.array, ref_text: str, gen_text: str, speed: float = 1.0):
    ref_audio_len = ref_audio.shape[0] // HOP_LENGTH
    zh_pause_punc = r"。，、；：？！"
    ref_text_len = len(ref_text.encode('utf-8')) + 3 * len(re.findall(zh_pause_punc, ref_text))
    gen_text_len = len(gen_text.encode('utf-8')) + 3 * len(re.findall(zh_pause_punc, gen_text))
    duration_in_frames = ref_audio_len + int(ref_audio_len / ref_text_len * gen_text_len / speed)
    print(f"Got estimated duration: {duration_in_frames / FRAMES_PER_SEC}")
    return duration_in_frames / FRAMES_PER_SEC


# audio player


class AudioPlayer:
    def __init__(self, sample_rate=24000, buffer_size=2048):
        self.sample_rate = sample_rate
        self.buffer_size = buffer_size
        self.audio_buffer = deque()
        self.buffer_lock = Lock()
        self.playing = False
        self.drain_event = Event()
        self.stream = None

    def callback(self, outdata, frames, time, status):
        with self.buffer_lock:
            if len(self.audio_buffer) > 0:
                available = min(frames, len(self.audio_buffer[0]))
                chunk = self.audio_buffer[0][:available].copy()
                self.audio_buffer[0] = self.audio_buffer[0][available:]

                if len(self.audio_buffer[0]) == 0:
                    self.audio_buffer.popleft()
                    if len(self.audio_buffer) == 0:
                        self.drain_event.set()

                outdata[:, 0] = np.zeros(frames)
                outdata[:available, 0] = chunk
            else:
                outdata[:, 0] = np.zeros(frames)
                self.drain_event.set()

    def play(self):
        if not self.playing:
            self.stream = sd.OutputStream(
                samplerate=self.sample_rate,
                channels=1,
                callback=self.callback,
                blocksize=self.buffer_size,
            )
            self.stream.start()
            self.playing = True
            self.drain_event.clear()

    def queue_audio(self, samples):
        self.drain_event.clear()
        
        with self.buffer_lock:
            self.audio_buffer.append(np.array(samples))
        if not self.playing:
            self.play()

    def wait_for_drain(self):
        return self.drain_event.wait()

    def stop(self):
        if self.playing:
            self.wait_for_drain()
            sd.sleep(100)
            
            self.stream.stop()
            self.stream.close()
            self.playing = False

    def clear_buffer(self):
        """Clear the audio buffer without stopping playback"""
        with self.buffer_lock:
            self.audio_buffer.clear()
            self.drain_event.set()


# main TTS class


class F5TTSGenerator:
    def __init__(
        self,
        model_name: str = "lucasnewman/f5-tts-mlx",
        quantization_bits: Optional[int] = None,
        sample_rate: int = 24000,
        buffer_size: int = 2048,
        ref_audio_path: Optional[str] = None,
        ref_audio_text: Optional[str] = None,
    ):
        """
        Initialize F5TTS generator with pre-loaded model and audio player.
        
        Args:
            model_name: Name of the F5TTS model to load
            quantization_bits: Quantization bits for model (4 or 8)
            sample_rate: Audio sample rate
            buffer_size: Audio buffer size
            ref_audio_path: Path to reference audio file
            ref_audio_text: Text corresponding to reference audio
        """
        print(f"Loading F5TTS model: {model_name}")
        self.f5tts = F5TTS.from_pretrained(model_name, quantization_bits=quantization_bits)
        print("Model loaded successfully")
        
        self.audio_player = AudioPlayer(sample_rate=sample_rate, buffer_size=buffer_size)
        
        # Load and process reference audio
        self._load_reference_audio(ref_audio_path, ref_audio_text)
        
    def _load_reference_audio(self, ref_audio_path: Optional[str], ref_audio_text: Optional[str]):
        """Load and process reference audio"""
        if ref_audio_path is None:
            # Use default reference audio
            data = pkgutil.get_data("f5_tts_mlx", "tests/test_en_1_ref_short.wav")
            tmp_ref_audio_file = "/tmp/ref.wav"
            with open(tmp_ref_audio_file, "wb") as f:
                f.write(data)
            
            audio, sr = sf.read(tmp_ref_audio_file)
            self.ref_audio_text = "Some call me nature, others call me mother nature."
        else:
            audio, sr = sf.read(ref_audio_path)
            if sr != SAMPLE_RATE:
                raise ValueError("Reference audio must have a sample rate of 24kHz")
            self.ref_audio_text = ref_audio_text

        self.ref_audio = mx.array(audio)
        ref_audio_duration = self.ref_audio.shape[0] / SAMPLE_RATE
        print(f"Got reference audio with duration: {ref_audio_duration:.2f} seconds")

        # Normalize audio RMS
        rms = mx.sqrt(mx.mean(mx.square(self.ref_audio)))
        if rms < TARGET_RMS:
            self.ref_audio = self.ref_audio * TARGET_RMS / rms

    def update_reference_audio(self, ref_audio_path: str, ref_audio_text: str):
        """Update the reference audio and text"""
        self._load_reference_audio(ref_audio_path, ref_audio_text)

    def generate(
        self,
        generation_text: str,
        duration: Optional[float] = None,
        estimate_duration: bool = False,
        steps: int = 8,
        method: Literal["euler", "midpoint", "rk4"] = "rk4",
        cfg_strength: float = 2.0,
        sway_sampling_coef: float = -1.0,
        speed: float = 1.0,
        seed: Optional[int] = None,
        output_path: Optional[str] = None,
        play_audio: bool = True,
    ):
        """
        Generate audio from text using the pre-loaded model.
        
        Args:
            generation_text: Text to generate speech from
            duration: Duration of generated audio in seconds
            estimate_duration: Whether to estimate duration using heuristic
            steps: Number of sampling steps
            method: Sampling method ("euler", "midpoint", "rk4")
            cfg_strength: Classifier-free guidance strength
            sway_sampling_coef: Sway sampling coefficient
            speed: Speed factor for duration heuristic
            seed: Random seed
            output_path: Path to save generated audio
            play_audio: Whether to play audio through speakers
        """
        sentences = split_sentences(generation_text)
        is_single_generation = len(sentences) <= 1 or duration is not None

        if is_single_generation:
            return self._generate_single(
                generation_text, duration, estimate_duration, steps, method,
                cfg_strength, sway_sampling_coef, speed, seed, output_path, play_audio
            )
        else:
            return self._generate_multi_sentence(
                sentences, duration, estimate_duration, steps, method,
                cfg_strength, sway_sampling_coef, speed, seed, output_path, play_audio
            )

    def _generate_single(
        self, generation_text, duration, estimate_duration, steps, method,
        cfg_strength, sway_sampling_coef, speed, seed, output_path, play_audio
    ):
        """Generate audio for single sentence/fixed duration"""
        if duration is not None:
            duration = int(duration * FRAMES_PER_SEC)
        elif estimate_duration:
            duration = int(estimated_duration(self.ref_audio, self.ref_audio_text, generation_text, speed) * FRAMES_PER_SEC)

        generation_text = convert_char_to_pinyin([self.ref_audio_text + " " + generation_text])

        start_date = datetime.datetime.now()

        wave, _ = self.f5tts.sample(
            mx.expand_dims(self.ref_audio, axis=0),
            text=generation_text,
            duration=duration,
            steps=steps,
            method=method,
            speed=speed,
            cfg_strength=cfg_strength,
            sway_sampling_coef=sway_sampling_coef,
            seed=seed,
        )

        wave = wave[self.ref_audio.shape[0]:]
        mx.eval(wave)

        generated_duration = wave.shape[0] / SAMPLE_RATE
        print(f"Generated {generated_duration:.2f}s of audio in {datetime.datetime.now() - start_date}.")

        if play_audio:
            self.audio_player.queue_audio(wave)

        if output_path is not None:
            sf.write(output_path, np.array(wave), SAMPLE_RATE)

        if play_audio:
            self.audio_player.stop()

        return wave

    def _generate_multi_sentence(
        self, sentences, duration, estimate_duration, steps, method,
        cfg_strength, sway_sampling_coef, speed, seed, output_path, play_audio
    ):
        """Generate audio for multiple sentences"""
        start_date = datetime.datetime.now()
        output = []

        for sentence_text in tqdm(sentences):
            sentence_duration = None
            if duration is not None:
                sentence_duration = int(duration * FRAMES_PER_SEC)
            elif estimate_duration:
                sentence_duration = int(estimated_duration(self.ref_audio, self.ref_audio_text, sentence_text, speed) * FRAMES_PER_SEC)

            text = convert_char_to_pinyin([self.ref_audio_text + " " + sentence_text])

            wave, _ = self.f5tts.sample(
                mx.expand_dims(self.ref_audio, axis=0),
                text=text,
                duration=sentence_duration,
                steps=steps,
                method=method,
                speed=speed,
                cfg_strength=cfg_strength,
                sway_sampling_coef=sway_sampling_coef,
                seed=seed,
            )

            # Trim the reference audio
            wave = wave[self.ref_audio.shape[0]:]
            mx.eval(wave)

            output.append(wave)

            if play_audio:
                self.audio_player.queue_audio(wave)

        wave = mx.concatenate(output, axis=0)

        generated_duration = wave.shape[0] / SAMPLE_RATE
        print(f"Generated {generated_duration:.2f}s of audio in {datetime.datetime.now() - start_date}.")

        if output_path is not None:
            sf.write(output_path, np.array(wave), SAMPLE_RATE)

        if play_audio:
            self.audio_player.stop()

        return wave

    def cleanup(self):
        """Clean up resources"""
        if hasattr(self, 'audio_player'):
            self.audio_player.stop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generate audio from text using f5-tts-mlx"
    )

    parser.add_argument(
        "--model",
        type=str,
        default="lucasnewman/f5-tts-mlx",
        help="Name of the model to use",
    )
    parser.add_argument(
        "--text",
        type=str,
        default=None,
        help="Text to generate speech from (leave blank to input via stdin)",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=None,
        help="Duration of the generated audio in seconds",
    )
    parser.add_argument(
        "--estimate-duration",
        type=bool,
        default=False,
        help="If true, estimate the duration using a heuristic based on the text instead of the duration predictor model.",
    )
    parser.add_argument(
        "--ref-audio",
        type=str,
        default=None,
        help="Path to the reference audio file",
    )
    parser.add_argument(
        "--ref-text",
        type=str,
        default=None,
        help="Text spoken in the reference audio",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Path to save the generated audio output",
    )
    parser.add_argument(
        "--steps",
        type=int,
        default=4,
        help="Number of steps to take when sampling the neural ODE",
    )
    parser.add_argument(
        "--method",
        type=str,
        default="midpoint",
        choices=["euler", "midpoint", "rk4"],
        help="Method to use for sampling the neural ODE",
    )
    parser.add_argument(
        "--cfg",
        type=float,
        default=2.0,
        help="Strength of classifer free guidance",
    )
    parser.add_argument(
        "--sway-coef",
        type=float,
        default=-1.0,
        help="Coefficient for sway sampling",
    )
    parser.add_argument(
        "--speed",
        type=float,
        default=1.0,
        help="Speed factor for the duration heuristic",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Seed for noise generation",
    )
    parser.add_argument(
        "--q",
        type=int,
        default=4,
        help="Number of bits to use for quantization. 4 and 8 are supported.",
    )

    args = parser.parse_args()

    generator = F5TTSGenerator(
        model_name=args.model,
        quantization_bits=args.q,
        ref_audio_path=args.ref_audio,
        ref_audio_text=args.ref_text,
    )

    if args.text is None:
        if not sys.stdin.isatty():
            args.text = sys.stdin.read().strip()
        else:
            print("Please enter the text to generate:")
            args.text = input("> ").strip()

    generator.generate(
        generation_text=args.text,
        duration=args.duration,
        estimate_duration=args.estimate_duration,
        steps=args.steps,
        method=args.method,
        cfg_strength=args.cfg,
        sway_sampling_coef=args.sway_coef,
        speed=args.speed,
        seed=args.seed,
        output_path=args.output,
    )