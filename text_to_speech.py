import pyttsx3
import argparse
import threading
import queue
import time


import argparse
import threading
import queue
import subprocess
import platform
import time


class TextToSpeech:
    def __init__(self, voice_id=None, rate=200):
        self.text_queue = queue.Queue()
        self.speaking = False
        self.voice_id = voice_id
        self.rate = rate

        self.is_mac = platform.system() == "Darwin"

        threading.Thread(target=self._worker, daemon=True).start()

    def _speak_subprocess(self, text):
        try:
            if self.is_mac:
                cmd = ["say", "-r", str(self.rate), text]
                if self.voice_id:
                    cmd = ["say", "-v", self.voice_id, "-r", str(self.rate), text]
            else:
                # Raspberry Pi/Linux
                cmd = ["espeak", "-s", str(self.rate), text]
                if self.voice_id:
                    cmd = ["espeak", "-s", str(self.rate), "-v", self.voice_id, text]

            subprocess.run(cmd, check=True)
        except Exception as e:
            print(f"Subprocess TTS error: {e}")

    def _worker(self):
        while True:
            try:
                text = self.text_queue.get(timeout=0.5)
                self.speaking = True
                print(f"[subprocess start] {text}")
                self._speak_subprocess(text)
                print(f"[subprocess end] {text}")
                self.speaking = False
            except queue.Empty:
                continue
            except Exception as e:
                print(f"TTS Worker Error: {e}")
                self.speaking = False

    def speak(self, text):
        self.text_queue.put(text)

    def completed_speaking(self):
        return self.text_queue.empty() and not self.speaking



if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    parser.add_argument("--text", type=str, default="Hello, how are you?")
    parser.add_argument("--select-voice", type=bool, default=False)
    args = parser.parse_args()

    tts = TextToSpeech(rate=200)

    if args.select_voice:
        tts.select_voice()


    print(f"Speaking: {args.text}")
    for i in range(0,5):
        tts.speak(args.text + f'iteration {i}')

    while not tts.completed_speaking():
        time.sleep(5)
        print("Waiting for TTS to finish...")
