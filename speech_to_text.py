#!/usr/bin/env python3

import argparse
import queue
import sys
import sounddevice as sd
import numpy as np

from json import dumps, loads
from datetime import datetime

# Vosk imports
from vosk import Model, KaldiRecognizer
# Faster Whisper import (replaces standard whisper)
from faster_whisper import WhisperModel
from pynput.keyboard import Key, KeyCode, Listener as KeyListener

import time as t

def select_input_device():
    devices = sd.query_devices()
    for i, device in enumerate(devices):
        if device['max_input_channels'] > 0:
            print(f'Device {i}: \n' + dumps(device) + '\n ---- \n')
    index = int(input('Enter the index of the device you want to use: '))
    print(f'Using device {index} ')
    return index


class Listener:
    def __init__(self, device=None, engine='vosk', model='en-us', ptt: bool = False, 
                 silence_threshold=0.02, silence_duration=1.0, speech_timeout=30):
        """
        device: audio input device index or name
        engine: 'vosk' or 'whisper'
        model: vosk language model code or whisper model size
        ptt: if True, press SPACE to start/stop
        silence_threshold: audio level below which is considered silence (0.0-1.0)
        silence_duration: seconds of silence before stopping (float)
        speech_timeout: max seconds to record before forcing stop
        """
        self.engine = engine.lower()
        self.device = device
        self.ptt = ptt
        self.recording = False
        self.pressed_keys = set()
        self.q = queue.Queue()
        self.audio_frames = []
        
        # Silence detection parameters
        self.silence_threshold = silence_threshold
        self.silence_duration = silence_duration
        self.speech_timeout = speech_timeout
        self.last_audio_time = None
        self.speech_detected = False
        self.current_audio_level = 0.0

        # Load speech model
        if self.engine == 'vosk':
            self.asr = Model(lang=model, model_name=f'vosk-model-small-{model}-0.15')
        elif self.engine == 'whisper':
            if model == 'en-us':
                model = 'base'  # Much faster than large models
            
            # Use faster-whisper with Apple Silicon optimization
            print(f"Loading faster-whisper model: {model}")
            self.asr = WhisperModel(
                model, 
                device="auto",  # Will automatically use GPU if available
                compute_type="int8"  # Faster on Apple Silicon
            )
        else:
            raise ValueError(f"Unknown engine: {engine}")

        # Keyboard listener for Ctrl+P toggle and SPACE start/stop
        def _on_press(key):
            self.pressed_keys.add(key)
            # Ctrl+P to toggle PTT
            if ((Key.ctrl_l in self.pressed_keys or Key.ctrl_r in self.pressed_keys)
                    and key == KeyCode.from_char('p')):
                self._toggle_ptt()
            # SPACE toggles recording when PTT active
            elif key == Key.space and self.ptt:
                self.recording = not self.recording
                if self.recording:
                    print('Recording started (press SPACE again to stop)')
                    self.audio_frames = []
                    self._reset_silence_detection()
                else:
                    print('Recording stopped')

        def _on_release(key):
            if key in self.pressed_keys:
                self.pressed_keys.remove(key)

        self._key_listener = KeyListener(on_press=_on_press, on_release=_on_release)
        self._key_listener.daemon = True
        self._key_listener.start()

        self.samplerate = 16000

    def _reset_silence_detection(self):
        """Reset silence detection state"""
        self.last_audio_time = t.time()
        self.speech_detected = False
        self.current_audio_level = 0.0

    def _toggle_ptt(self):
        """Toggle PTT mode with Ctrl+P"""
        self.ptt = not self.ptt
        self.recording = False
        mode = 'PTT' if self.ptt else 'always-listening'
        print(f'PTT mode toggled. Now in {mode} mode.')

    def _should_stop_recording(self):
        """Check if recording should stop based on silence detection"""
        current_time = t.time()
        
        # If we haven't detected speech yet, don't stop
        if not self.speech_detected:
            return False
        
        # Check for speech timeout
        if self.last_audio_time and (current_time - self.last_audio_time) > self.speech_timeout:
            print("Speech timeout reached")
            return True
        
        if self.current_audio_level < self.silence_threshold:
            silence_time = current_time - self.last_audio_time
            if silence_time >= self.silence_duration:
                print(f"Silence detected for {silence_time:.1f}s - stopping")
                return True
        
        return False

    def listen(self, max_duration=20) -> str:
        """
        Listen and return transcribed text.
        In PTT mode: press SPACE to start/stop.
        Otherwise: always-listen with silence detection for Whisper.
        """
        if self.engine == 'vosk':
            rec = KaldiRecognizer(self.asr, self.samplerate)
        
        # Reset silence detection
        self._reset_silence_detection()
        
        # open audio stream once
        with sd.RawInputStream(
            samplerate=self.samplerate,
            blocksize=4000,  # Smaller blocks for better silence detection
            device=self.device,
            dtype='int16',
            channels=1,
            callback=self.callback
        ):
            if self.ptt:
                print('PTT active: press SPACE to start, press again to stop.')
                # wait start
                while not self.recording:
                    t.sleep(0.05)
                print('Begin streaming...')
                # stream until STOP
                while self.recording:
                    data = self.q.get()
                    if self.engine == 'vosk':
                        rec.AcceptWaveform(data)
                        self.audio_frames = None
                    else:
                        self.audio_frames.append(data)
                # finalize
                if self.engine == 'vosk':
                    return loads(rec.FinalResult()).get('text', '').strip()
                else:
                    return self._transcribe_whisper(self.audio_frames)
            else:
                # always-listen with silence detection
                start = datetime.now()
                if self.engine == 'vosk':
                    print('Listening (Vosk)...')
                    while (datetime.now() - start).seconds < max_duration:
                        data = self.q.get()
                        if rec.AcceptWaveform(data):
                            text = loads(rec.Result()).get('text', '').strip()
                            if text:
                                return text
                    return loads(rec.FinalResult()).get('text', '').strip()
                else:
                    print(f'Listening (Whisper with silence detection)...')
                    frames = []
                    while (datetime.now() - start).seconds < max_duration:
                        if not self.q.empty():
                            frames.append(self.q.get())
                            # Check if we should stop due to silence
                            if self._should_stop_recording():
                                break
                        else:
                            t.sleep(0.01)  # Small delay to prevent busy waiting
                    
                    if not frames:
                        return ""
                    return self._transcribe_whisper(frames)

    def _transcribe_whisper(self, frames: list) -> str:
        if not frames:
            return ""
        
        # combine raw byte frames into numpy array
        raw = b''.join(frames)
        audio_int16 = np.frombuffer(raw, np.int16)
        # normalize to float32 [-1,1]
        audio = audio_int16.astype(np.float32) / 32768.0
        
        # Check if audio is too short
        if len(audio) < self.samplerate * 0.1:  # Less than 0.1 seconds
            print("Audio too short for transcription")
            return ""
        
        # Check for silent audio to avoid warnings
        audio_level = np.sqrt(np.mean(audio**2))
        if audio_level < 1e-6:  # Very quiet audio
            print("Audio too quiet for transcription")
            return ""
        
        # Clip audio to prevent overflow issues
        audio = np.clip(audio, -1.0, 1.0)
        
        # faster-whisper expects 16000 Hz
        try:
            # Suppress numpy warnings temporarily
            import warnings
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", category=RuntimeWarning)
                
                # faster-whisper returns segments and info, not a dict
                segments, info = self.asr.transcribe(
                    audio, 
                    beam_size=1,  # Faster with beam_size=1
                    language="en",  # Specify language for speed
                    condition_on_previous_text=False,  # Faster processing
                    no_speech_threshold=0.6  # Higher threshold to avoid processing silence
                )
                
                # Extract text from segments
                result_text = " ".join([segment.text for segment in segments])
                return result_text.strip()
        
        except Exception as e:
            print(f"Transcription error: {e}")
            return ""

    def callback(self, indata, frames, time, status):
        if status:
            print(status, file=sys.stderr)
        
        # FIXED: Handle CFFI buffer properly
        try:
            # Convert CFFI buffer to numpy array first
            if hasattr(indata, 'shape'):
                # Already a numpy array
                audio_data = indata
            else:
                # CFFI buffer - convert to numpy array
                audio_data = np.frombuffer(indata, dtype=np.int16).reshape(-1, 1)
                        
            # Handle the data type and convert to float
            if audio_data.dtype == np.int16:
                # Data is properly formatted as int16
                audio_float = audio_data.flatten().astype(np.float32) / 32768.0
            elif audio_data.dtype == np.uint8:
                # Data is incorrectly formatted as uint8 (0-255 range)
                print("WARNING: Audio data is uint8, converting to proper range")
                # Convert uint8 (0-255) to int16 (-32768 to 32767) range
                audio_int16 = (audio_data.flatten().astype(np.int16) - 128) * 256
                audio_float = audio_int16.astype(np.float32) / 32768.0
            elif audio_data.dtype == np.float32:
                # Data is already float32, just flatten
                audio_float = audio_data.flatten()
            else:
                # Try to force interpret as int16
                print(f"Unknown dtype {audio_data.dtype}, attempting to reinterpret as int16")
                raw_bytes = audio_data.tobytes()
                audio_int16 = np.frombuffer(raw_bytes, dtype=np.int16)
                audio_float = audio_int16.astype(np.float32) / 32768.0
            
            # Calculate RMS (Root Mean Square) for more stable level detection
            if len(audio_float) > 0:
                audio_level = np.sqrt(np.mean(audio_float**2))
                # Also calculate max for comparison
                max_level = np.max(np.abs(audio_float))
            else:
                audio_level = 0.0
                max_level = 0.0
                
        except Exception as e:
            print(f"Audio level calculation error: {e}")
            audio_level = 0.0
            max_level = 0.0

        self.current_audio_level = audio_level
        
        # Update silence detection state
        if audio_level > self.silence_threshold:
            self.speech_detected = True
            self.last_audio_time = t.time()
        
        # Store the raw bytes for processing (convert CFFI buffer to bytes)
        if hasattr(indata, 'tobytes'):
            self.q.put(indata.tobytes())
        else:
            # CFFI buffer - convert to bytes
            self.q.put(bytes(indata))


if __name__ == '__main__':
    def int_or_str(text):
        try:
            return int(text)
        except ValueError:
            return text

    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('-l', '--list-devices', action='store_true', help='show devices and exit')
    args, remaining = parser.parse_known_args()
    if args.list_devices:
        print(sd.query_devices())
        parser.exit(0)

    parser = argparse.ArgumentParser(parents=[parser])
    parser.add_argument('-d', '--device', type=int_or_str, help='input device ID or substring')
    parser.add_argument('-e', '--engine', choices=['vosk', 'whisper'], default='whisper',
                        help='ASR engine')
    parser.add_argument('-m', '--model', default='en-us',
                        help='vosk model code or whisper size')
    parser.add_argument('--ptt', action='store_true', help='enable push-to-talk via SPACE')
    parser.add_argument('--silence-threshold', type=float, default=0.01,
                        help='audio level threshold for silence detection (0.0-1.0)')
    parser.add_argument('--silence-duration', type=float, default=2.0,
                        help='seconds of silence before stopping')
    parser.add_argument('--speech-timeout', type=float, default=30,
                        help='max seconds to record before forcing stop')
    args = parser.parse_args(remaining)

    print(f"Starting listener with:")
    print(f"  Engine: {args.engine}")
    print(f"  Device: {args.device}")
    print(f"  Silence threshold: {args.silence_threshold}")
    print(f"  Silence duration: {args.silence_duration}s")
    print(f"  Speech timeout: {args.speech_timeout}s")
    print(f"  PTT mode: {args.ptt}")
    print()

    listener = Listener(device=args.device, engine=args.engine,
                        model=args.model, ptt=args.ptt,
                        silence_threshold=args.silence_threshold,
                        silence_duration=args.silence_duration,
                        speech_timeout=args.speech_timeout)
    try:
        while True:
            text = listener.listen()
            if text:
                print(f'\nRecognized: {text}')
            else:
                print('\nNo speech detected')
    except KeyboardInterrupt:
        print('\nDone')
        parser.exit(0)