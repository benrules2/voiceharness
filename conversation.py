import argparse

from speech_to_text import Listener, select_input_device
from text_to_speech import TextToSpeech
from process_request import ChatBotProcessor

import re
import threading

class Conversation:
    def __init__(self, device=None):
        self.device = device if device else select_input_device()
        self.listener = Listener(device=self.device, model="en-us")
        self.tts = TextToSpeech(rate=200)
        self.processor = ChatBotProcessor(
            initial_prompt="""
            You are CommandA running through walkie talkies. You are using some VOSK asr speech to text to receive inputs.
            You are receiving audio through walkie talkies as the input and output. Only mention if asked.

            If not asked, simply be yourself, but limit responses to one or two sentences do not use emojis. 

            Your responses are run through TTS, so don't use emojis. Keep responses brief, limit to a few sentences.
            """
        )
        self.lock_tts = threading.Lock()
    def process_request(self) -> str:
        print("Handling new request...")
        action_text = self.listener.listen()      
        print(f"Received: {action_text}")
        self.run_request_processing_engine(action_text)
    
    def run_request_processing_engine(self, action_text: str):
        buffer = ""
        def speak_or_buffer(delta: str):
            nonlocal buffer
            buffer += delta
            words = buffer.split(" ")

            # Check for punctuation or long words
            for i, word in enumerate(words):
                if len(word) > 20 or re.search(r"[.!?;:]", word):
                    output = " ".join(words[: i + 1])
                    print(f"Speaking: {output}")
                    self.tts.speak(output)
                    buffer = " ".join(words[i + 1 :])

        self.processor.process_user_interaction(action_text,  speak_or_buffer)

        if buffer:
            self.tts.speak(buffer)  

    def start(self):
        print("Starting conversation... Hit ctrl-c to end")
        self.continue_talking = True
        try: 
            while self.continue_talking:
                self.process_request()
        except KeyboardInterrupt:
            print("Conversation ended")
            self.continue_talking = False


if __name__ == "__main__":

    args = argparse.ArgumentParser()
    args.add_argument("--device", default=None)
    args = args.parse_args()

    conversation = Conversation(device=args.device)
    conversation.start()
