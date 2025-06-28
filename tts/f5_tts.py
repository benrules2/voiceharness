import argparse
import pkgutil
import queue
import re
import sys
import threading
import time
from datetime import datetime
from collections import deque
from threading import Event, Lock
from typing import Optional

import mlx.core as mx
import numpy as np
import sounddevice as sd
import soundfile as sf
import hashlib
from pathlib import Path

from f5_tts_mlx.cfm import F5TTS
from f5_tts_mlx.utils import convert_char_to_pinyin

SAMPLE_RATE = 24_000
TARGET_RMS = 0.1
mx.set_default_device(mx.gpu)


def split_sentences(text: str):
    parts = re.split(r"([.!?;:])", text)
    if len(parts) <= 1:
        return [text.strip()] if text.strip() else []

    sentences = [
        parts[i] + parts[i + 1] for i in range(0, len(parts) - 1, 2)
        if (parts[i] + parts[i + 1]).strip()
    ]

    # Merge sentences until minimum length is reached
    merged_sentences = []
    current_sentence = ""
    for sentence in sentences:
        if len(current_sentence.split()) < 5:
            current_sentence += " " + sentence.strip()
        else:
            merged_sentences.append(current_sentence.strip())
            current_sentence = sentence.strip()

    if current_sentence.strip():
        merged_sentences.append(current_sentence.strip())

    return merged_sentences


# ─────────────────────────── AUDIO ─────────────────────────── #
class AudioPlayer:
    def __init__(self, sample_rate=SAMPLE_RATE, buffer_size=4096):
        self.sample_rate = sample_rate
        self.buffer_size = buffer_size
        self.audio_buffer = deque()
        self.buffer_lock = Lock()
        self.drain_event = Event()
        self.stream = None
        self.playing = False
        self.last_audio_ts = time.monotonic()

    def _callback(self, outdata, frames, time_info, status):
        with self.buffer_lock:
            if self.audio_buffer:
                n = min(frames, len(self.audio_buffer[0]))
                chunk = self.audio_buffer[0][:n]
                self.audio_buffer[0] = self.audio_buffer[0][n:]
                if self.audio_buffer[0].size == 0:
                    self.audio_buffer.popleft()
                    if not self.audio_buffer:
                        self.drain_event.set()

                outdata[:, 0] = 0
                outdata[:n, 0] = chunk
                if np.any(chunk):
                    self.last_audio_ts = time.monotonic()
            else:
                outdata[:, 0] = 0
                self.drain_event.set()

    def _ensure_stream(self):
        if not self.playing:
            self.stream = sd.OutputStream(
                samplerate=self.sample_rate,
                channels=1,
                blocksize=self.buffer_size,
                callback=self._callback,
            )
            self.stream.start()
            self.playing = True

    def queue_audio(self, samples: np.ndarray):
        with self.buffer_lock:
            self.audio_buffer.append(samples.astype(np.float32))
        self.drain_event.clear()
        self._ensure_stream()

    def stop(self):
        self.drain_event.wait()
        if self.stream:
            self.stream.stop()
            self.stream.close()
        self.playing = False


# ───────────────────────  F5-TTS WRAPPER  ────────────────────── #
class F5TTSGenerator:
    def __init__(
        self,
        quantization_bits: Optional[int],
        ref_audio_path: Optional[str],
        ref_audio_text: Optional[str],
        steps=10,
        method="euler",
        cfg_strength=1.5,
        sway=-1.0,
        speed=1.0,
        model_name: str = "lucasnewman/f5-tts-mlx",
        cache_dir: Optional[str] = None,
    ):
        # generation parameters
        self.steps = steps
        self.method = method
        self.cfg_strength = cfg_strength
        self.sway = sway
        self.speed = speed

        # model info
        self.model_name = model_name
        self.quantization_bits = quantization_bits

        # for save logic
        self._done_event = Event()
        self._remaining = 0

        print(f"🧠 Loading model '{model_name}' (q={quantization_bits})")
        self.f5tts = F5TTS.from_pretrained(model_name, quantization_bits=quantization_bits)
        if quantization_bits is None:
            self._cast_state_fp16(self.f5tts.state)

        # prepare cache directory
        base = Path(cache_dir) if cache_dir else Path.home() / ".cache" / "f5tts"
        self.cache_dir = base
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # audio playback
        self.audio = AudioPlayer()
        self.audio._ensure_stream()
        self._load_reference_audio(ref_audio_path, ref_audio_text)

        # async playback queue
        self.task_queue = queue.Queue()
        self.active_lock = Lock()
        self.gpu_alive = True

        # buffer for saving
        self._save_buffer: Optional[list[np.ndarray]] = None
        self._output_path: Optional[str] = None

        threading.Thread(target=self._gpu_worker, daemon=True).start()
        self.speaking = False

    @staticmethod
    def _cast_state_fp16(tree):
        for k, v in tree.items():
            if isinstance(v, dict):
                F5TTSGenerator._cast_state_fp16(v)
            elif isinstance(v, mx.array) and v.dtype == mx.float32:
                tree[k] = v.astype(mx.float16)

    def _load_reference_audio(self, path, text):
        if path is None:
            wav = pkgutil.get_data("f5_tts_mlx", "tests/test_en_1_ref_short.wav")
            tmp = "/tmp/_f5_ref.wav"
            with open(tmp, "wb") as f:
                f.write(wav)
            audio, _ = sf.read(tmp)
            text = "Some call me nature, others call me mother nature."
        else:
            audio, _ = sf.read(path)

        self.ref_audio = mx.array(audio)
        self.ref_audio_text = text or ""
        rms = mx.sqrt(mx.mean(mx.square(self.ref_audio)))
        if rms < TARGET_RMS:
            self.ref_audio *= TARGET_RMS / rms
        print("✅ Reference audio loaded")

    def _gpu_worker(self):
        while self.gpu_alive:
            try:
                text, p = self.task_queue.get(timeout=1.0)
            except queue.Empty:
                continue
            if text == "STOP":
                break

            # compute cache key and path
            key = self._cache_key(text, p)
            cache_path = self.cache_dir / f"{key}.npy"

            if cache_path.exists():
                samples = np.load(cache_path)
                print(f"🔄 Cache hit for: '{text}' -> {cache_path.name}")
            else:
                with self.active_lock:
                    print(f"[GPU] ⏳ Generating & caching: '{text}'")
                wave, _ = self._do_sample(text, **p)
                wave = wave[self.ref_audio.shape[0]:]
                mx.eval(wave)
                samples = np.asarray(wave)
                # save to disk cache
                np.save(cache_path, samples)

            # playback
            self.audio.queue_audio(samples)

            # accumulate for saving if requested
            if self._save_buffer is not None:
                self._save_buffer.append(samples)
                with self.active_lock:
                    self._remaining -= 1
                    if self._remaining == 0:
                        self._done_event.set()

    def _cache_key(self, text: str, params: dict) -> str:
        hasher = hashlib.sha256()
        hasher.update(self.model_name.encode("utf-8"))
        hasher.update(str(self.quantization_bits).encode("utf-8"))
        hasher.update(self.ref_audio_text.encode("utf-8"))
        hasher.update(str(self.steps).encode("utf-8"))
        hasher.update(text.encode("utf-8"))
        for k in sorted(params.keys()):
            hasher.update(str(k).encode("utf-8"))
            hasher.update(str(params[k]).encode("utf-8"))
        return hasher.hexdigest()

    def _do_sample(self, text, steps, method, cfg_strength, sway, speed, seed):
        prompt = convert_char_to_pinyin([self.ref_audio_text + " " + text])
        return self.f5tts.sample(
            mx.expand_dims(self.ref_audio, 0),
            text=prompt,
            steps=steps,
            method=method,
            speed=speed,
            cfg_strength=cfg_strength,
            sway_sampling_coef=sway,
            seed=seed,
        )

    def speak(self, text: str, seed: int = 1, output: Optional[str] = None):
        """
        Async streaming TTS to AudioPlayer.
        If `output` is provided, buffers the generated samples and writes once done.
        Uses on-disk cache to reuse previously-generated sentences.
        """
        sentences = split_sentences(text)
        if output:
            # reset & set up our “all done” event
            self._done_event.clear()
            self._remaining = len(sentences)
            self._save_buffer = []
            self._output_path = output if output.lower().endswith(".wav") else output + ".wav"

        # enqueue sentences
        for s in sentences:
            params = dict(
                steps=self.steps,
                method=self.method,
                cfg_strength=self.cfg_strength,
                sway=self.sway,
                speed=self.speed,
                seed=seed,
            )
            self.task_queue.put((s, params))

        # if saving, block on both events, then flush buffer
        if self._save_buffer is not None:
            # 1) wait until GPU has appended every chunk
            self._done_event.wait()
            # 2) wait until playback is fully drained
            self.audio.drain_event.wait()

            # now write out
            all_samples = np.concatenate(self._save_buffer, axis=0)
            sf.write(self._output_path, all_samples, samplerate=self.audio.sample_rate)
            print(f"💾 Saved WAV to {self._output_path}")

            # reset
            self._save_buffer = None
            self._output_path = None

    def completed_speaking(self) -> bool:
        latency = self.audio.buffer_size / self.audio.sample_rate
        quiet = time.monotonic() - self.audio.last_audio_ts >= latency
        with self.active_lock:
            return quiet and not self.audio.audio_buffer and self.task_queue.empty()

    def cleanup(self):
        self.gpu_alive = False
        self.task_queue.put(("STOP", None))
        self.audio.stop()
        print("🧹 Cleanup complete")


# ─────────────────────────  CLI  ───────────────────────── #
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="lucasnewman/f5-tts-mlx")
    ap.add_argument("--text")
    ap.add_argument("--steps", type=int, default=8)
    ap.add_argument("--method", choices=["euler", "midpoint", "rk4"], default="rk4")
    ap.add_argument("--cfg", type=float, default=1.2)
    ap.add_argument("--sway", type=float, default=-1.0)
    ap.add_argument("--speed", type=float, default=1.0)
    ap.add_argument("--seed", type=int)
    ap.add_argument("--q", type=int, help="weight-quant bits (4,8)")
    ap.add_argument("--ref-audio", help="path to reference WAV")
    ap.add_argument("--ref-text", help="text matching the reference audio")
    ap.add_argument("--output", help="save full waveform to this WAV file", default=None)

    args = ap.parse_args()

    tts = F5TTSGenerator(
        model_name=args.model,
        quantization_bits=args.q,
        ref_audio_path=args.ref_audio,
        ref_audio_text=args.ref_text,
        steps=args.steps,
        method=args.method,
        speed=args.speed,
    )

    try:
        if args.text is None:
            args.text = input("> ").strip()
        while args.text:
            time_start = datetime.now()
            tts.speak(args.text, output=args.output)
            while not tts.completed_speaking():
                time.sleep(0.1)
            elapsed = (datetime.now() - time_start).total_seconds()
            print(f"⏱️  Generated in {elapsed:.2f} seconds")
            args.text = input("> ").strip()
    finally:
        tts.cleanup()


if __name__ == "__main__":
    main()
