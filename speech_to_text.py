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
# Faster Whisper import
from faster_whisper import WhisperModel
from pynput.keyboard import Key, KeyCode, Listener as KeyListener

import time as t
from enum import StrEnum


class InputType(StrEnum):
    """Types of input modes supported"""
    ASR = 'asr'
    PTT = 'ptt'
    TEXT = 'text'


def select_input_device():
    devices = sd.query_devices()
    for i, device in enumerate(devices):
        if device['max_input_channels'] > 0:
            print(f'Device {i}: \n' + dumps(device) + '\n ---- \n')
    index = int(input('Enter the index of the device you want to use: '))
    print(f'Using device {index}')
    return index


class Listener:
    def __init__(
        self,
        device=None,
        engine='vosk',
        model='en-us',
        mode: InputType = InputType.ASR,
        silence_threshold=0.01,
        silence_duration=2,
        speech_timeout=60
    ):
        """
        device: audio input device index or name
        engine: 'vosk' or 'whisper'
        model: vosk language model code or whisper model size
        mode: InputType (ASR, PTT, TEXT)
        silence_threshold: level below which is silence (0.0-1.0)
        silence_duration: seconds of silence before stopping
        speech_timeout: max recording seconds
        """
        self.engine = engine.lower()
        self.device = device
        self.mode = mode
        self.recording_ptt = False
        self.pressed_keys = set()
        self.q = queue.Queue()
        self.audio_frames = []

        # Flag to catch switches from asr to ptt
        self.mode_toggled = False 

        # Silence detection
        self.silence_threshold = silence_threshold
        self.silence_duration = silence_duration
        self.speech_timeout = speech_timeout
        self.last_audio_time = None
        self.speech_detected = False
        self.current_audio_level = 0.0

        # Load ASR model
        if self.engine == 'vosk':
            self.asr = Model(lang=model, model_name=f'vosk-model-small-{model}-0.15')
        elif self.engine == 'whisper':
            if model == 'en-us':
                model = 'base'
            print(f"Loading faster-whisper model: {model}")
            self.asr = WhisperModel(model, device='auto', compute_type='int8')
        else:
            raise ValueError(f"Unknown engine: {engine}")

        # Keyboard listener: Ctrl+P for PTT, Ctrl+T for TEXT, SPACE toggles recording in PTT
        def _on_press(key):
            self.pressed_keys.add(key)
            ctrl = any(k in self.pressed_keys for k in (Key.ctrl_l, Key.ctrl_r))
            if ctrl and key == KeyCode.from_char('p'):
                self._toggle_mode_ptt()
            elif ctrl and key == KeyCode.from_char('t'):
                self._toggle_mode_text()
            elif key == Key.space and self.mode == InputType.PTT:
                self.recording_ptt = not self.recording_ptt
                if self.recording_ptt:
                    #Reset audio queue so it only takes new audio
                    print('Recording started (press SPACE again to stop)')
                    self._reset_audio_buffers()
                else:
                    print('Recording stopped')

        def _on_release(key):
            self.pressed_keys.discard(key)

        self._key_listener = KeyListener(on_press=_on_press, on_release=_on_release)
        self._key_listener.daemon = True
        self._key_listener.start()

        self.samplerate = 16000

    def _reset_silence_detection(self):
        self.last_audio_time = t.time()
        self.speech_detected = False
        self.current_audio_level = 0.0

    def _toggle_mode_ptt(self):
        """Toggle between ASR and PTT modes"""
        self.mode = InputType.PTT if self.mode != InputType.PTT else InputType.ASR
        self.recording_tts = False
        self.mode_toggled = True
        self._reset_audio_buffers()
        print(f'Mode switched. Now in {self.mode} mode.')

    def _toggle_mode_text(self):
        """Toggle between ASR and TEXT modes"""
        self.mode = InputType.TEXT if self.mode != InputType.TEXT else InputType.ASR
        print(f'Mode switched. Now in {self.mode} mode.')
        self.recording_tts = False
        self.mode_toggled = True
        self._reset_audio_buffers()

    def _reset_audio_buffers(self):
        with self.q.mutex:
            self.q.queue.clear()
        self.audio_frames = []
        self._reset_silence_detection()

    def _should_stop_recording(self):
        now = t.time()
        if not self.speech_detected:
            return False
        if (now - self.last_audio_time) > self.speech_timeout:
            print('Speech timeout reached')
            return True
        if self.current_audio_level < self.silence_threshold:
            if (now - self.last_audio_time) >= self.silence_duration:
                print(f"Silence for {now - self.last_audio_time:.1f}s - stopping")
                return True
        return False
    
    def _finalize(self, rec=None):
        if self.engine == 'vosk':
            return loads(rec.FinalResult()).get('text','').strip()
        else:
            return self._transcribe_whisper(self.audio_frames)

    def listen(self, max_duration=60) -> str:

        # TEXT mode: manual entry
        if self.mode == InputType.TEXT:
            return input('Enter text (or Ctrl+T to return to ASR): ').strip()

        # prepare ASR or PTT
        if self.engine == 'vosk':
            rec = KaldiRecognizer(self.asr, self.samplerate)
        self._reset_silence_detection()

        #listen for switch from ptt, text, asr
        self.mode_toggled = False 

        with sd.RawInputStream(
            samplerate=self.samplerate,
            blocksize=4000,
            device=self.device,
            dtype='int16',
            channels=1,
            callback=self.callback
        ):
            # PTT mode
            if self.mode == InputType.PTT:
                rec = None
                print('PTT mode: press SPACE to toggle recording')
                while not self.recording_ptt and not self.mode_toggled:
                    t.sleep(0.05)
                while self.recording_ptt and not self.mode_toggled:
                    frame = self.q.get()
                    if self.engine == 'vosk': 
                        # This code is broken
                        rec.AcceptWaveform(frame)
                    else:
                        self.audio_frames.append(frame)

                return self._finalize()

            # ASR mode
            elif self.mode == InputType.ASR:
                start = datetime.now()
                if self.engine == 'vosk':
                    print('ASR always-listen (Vosk)...')
                    while (datetime.now() - start).seconds < max_duration and not self.mode_toggled:
                        frame = self.q.get()
                        if rec.AcceptWaveform(frame):
                            text = loads(rec.Result()).get('text', '').strip()
                            if text:
                                return text
                    return loads(rec.FinalResult()).get('text', '').strip()
                else:
                    print('ASR always-listen (Whisper)...')
                    frames = []
                    while (datetime.now() - start).seconds < max_duration and not self.mode_toggled:
                        if not self.q.empty():
                            frames.append(self.q.get())
                            if self._should_stop_recording():
                                break
                        else:
                            t.sleep(0.01)
                    
                    if not frames:
                        return ""
                    
                    return self._transcribe_whisper(frames)

            # fallback
            return ""

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
        try: return int(text)
        except: return text

    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('-l','--list-devices',action='store_true')
    args, rem = parser.parse_known_args()
    if args.list_devices:
        print(sd.query_devices()); parser.exit(0)

    parser = argparse.ArgumentParser(parents=[parser])
    parser.add_argument('-d','--device',type=int_or_str)
    parser.add_argument('-e','--engine',choices=['vosk','whisper'],default='whisper')
    parser.add_argument('-m','--model',default='en-us')
    parser.add_argument('--mode',type=InputType,default=InputType.ASR)
    parser.add_argument('--silence-threshold',type=float,default=0.02)
    parser.add_argument('--silence-duration',type=float,default=2.5)
    parser.add_argument('--speech-timeout',type=float,default=180)
    args = parser.parse_args(rem)

    print(f"Starting: engine={args.engine}, device={args.device}, mode={args.mode}")
    listener = Listener(
        device=args.device,
        engine=args.engine,
        model=args.model,
        mode=args.mode,
        silence_threshold=args.silence_threshold,
        silence_duration=args.silence_duration,
        speech_timeout=args.speech_timeout
    )
    try:
        while True:
            text = listener.listen()
            print(f"Recognized: {text}" if text else "No input detected")
    except KeyboardInterrupt:
        print("Done")
        parser.exit(0)
