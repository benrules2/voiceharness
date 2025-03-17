import pyttsx3
import argparse
import threading
import queue

import time

class TextToSpeech:
    def __init__(self, voice_id=None, rate=None, debug=False):

        self.engine = pyttsx3.init(debug=debug)
        if voice_id:
            self.voice_id = voice_id
            self.engine.setProperty('voice', voice_id)
        if rate:
            self.rate = rate
            self.engine.setProperty('rate', rate)        
        self.queue = queue.Queue()

    def get_lock(self):
        return self.speech_lock.acquire(blocking=True, timeout=10)

    def speak(self, text: str):
        self.engine.say(text)
        self.engine.runAndWait()

    def select_voice(self):
        voices = self.engine.getProperty('voices')       #getting details of current voice
        for i, voice in enumerate(voices):
            print(f"Voice: {voice.name} ({voice.id})")  
            self.engine.setProperty('voice', voice.id)   #changing index, changes voices. 1 for female
            self.engine.say(f"Hello, how are you? This is voice {i}")
            self.engine.runAndWait()

            if input("Accept voice? (y/n)") == 'y':
                break

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
