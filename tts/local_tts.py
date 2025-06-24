import argparse
import threading
import queue
import time
import subprocess
import platform


class TextToSpeech:
    def __init__(self, voice_id=None, rate=200):
        self.text_queue = queue.Queue()
        self.speaking = False
        self.voice_id = voice_id
        self.rate = rate
        self.is_mac = platform.system() == "Darwin"
        
        # Thread synchronization
        self.worker_ready = threading.Event()  # This is the key fix!
        
        # Start worker thread
        self.worker_thread = threading.Thread(target=self._worker, daemon=True)
        self.worker_thread.start()
        
        # Wait for worker thread to be ready
        self.worker_ready.wait()  # Blocks until worker signals it's ready
        print("[TTS] Worker thread ready")

        self._init_phrase = " "
        if not self.is_mac:
            self._init_phrase = ". init . init ."

    def _speak_subprocess(self, text):
        try:
            if self.is_mac:
                cmd = ["say", "-r", str(self.rate), text]
                if self.voice_id:
                    cmd = ["say", "-v", self.voice_id, "-r", str(self.rate), text]
            else:
                cmd = ["espeak-ng", text]
                if self.voice_id:
                    cmd = ["espeak-ng", "-v", self.voice_id, text]
            
            process = subprocess.Popen(cmd, stderr=subprocess.PIPE)
            process.wait()
            
            if process.returncode != 0:
                print(f"Subprocess TTS error: {process.stderr.read().decode()}")
                
        except Exception as e:
            print(f"Subprocess TTS error: {e}")

    def _worker(self):
        # Signal that worker thread is ready to process
        self.worker_ready.set()  # This tells __init__ we're ready!
        
        while True:
            try:
                text = self.text_queue.get(timeout=0.1)
                self.speaking = True
                print(f"[speaking] {text}")
                self._speak_subprocess(text)
                time.sleep(0.1)
                self.speaking = False
                
            except queue.Empty:
                continue
            except Exception as e:
                print(f"TTS Worker Error: {e}")
                self.speaking = False

    def speak(self, text):
        if not self.speaking and self.text_queue.empty():
            self.text_queue.put(self._init_phrase)
        self.text_queue.put(text)

    def completed_speaking(self):
        return self.text_queue.empty() and not self.speaking

    def select_voice(self):
        if self.is_mac:
            subprocess.run(["say", "-v", "?"])
        else:
            subprocess.run(["espeak-ng", "--voices"])

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--text", type=str, default="Hello, how are you?")
    parser.add_argument("--select-voice", action="store_true")
    args = parser.parse_args()

    print("Initializing TTS...")
    tts = TextToSpeech(rate=200)  # This now blocks until worker is ready

    if args.select_voice:
        tts.select_voice()

    print(f"Speaking: {args.text}")
    for i in range(0, 5):
        tts.speak(args.text + f' iteration {i}')

    while not tts.completed_speaking():
        time.sleep(1.5)
        print("Waiting for TTS to finish...")
    
    print("TTS completed!")


