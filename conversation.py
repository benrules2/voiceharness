import argparse
import re
import threading
import time

from speech_to_text import Listener, select_input_device
from text_to_speech import TextToSpeech
from process_request import ChatBotProcessor
from talking_head import TalkingPhotoHead


class Conversation:
    def __init__(self, device=None, tts=None, talking_head=None):
        self.device = device if device else select_input_device()
        self.listener = Listener(device=self.device, model="en-us")
        self.tts = tts or TextToSpeech(rate=200)
        self.talking_head = talking_head

        self.processor = ChatBotProcessor(
            initial_prompt="""
            You are CommandA running through walkie talkies. You are using some VOSK asr speech to text to receive inputs.
            You are receiving audio through walkie talkies as the input and output. Only mention if asked.

            If not asked, simply be yourself, but limit responses to one or two sentences do not use emojis. 
            Your responses are run through TTS, so don't use emojis. Keep responses brief, limit to a few sentences.
            """
        )
        self.lock_tts = threading.Lock()

    def process_request(self):
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

            for i, word in enumerate(words):
                if len(word) > 20 or re.search(r"[.!?;:]", word):
                    output = " ".join(words[: i + 1])
                    print(f"Speaking: {output}")
                    self._speak(output)
                    buffer = " ".join(words[i + 1:])

        self.processor.process_user_interaction(action_text, speak_or_buffer)

        if buffer:
            self._speak(buffer)

    def _speak(self, text: str):
        self.talking_head.say(text)
        
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
    parser = argparse.ArgumentParser()
    parser.add_argument("--device", default=None)
    parser.add_argument("--image-path", type=str, default=None)
    args = parser.parse_args()

    # Shared TTS instance
    tts = TextToSpeech(rate=200)

    # Optional visual animation
    head = TalkingPhotoHead(image_path=args.image_path, tts=tts) 

    # Launch conversation loop in background
    def run_convo():
        convo = Conversation(device=args.device, tts=tts, talking_head=head)
        convo.start()

    threading.Thread(target=run_convo, daemon=True).start()

    # If head provided, run visual animation on main thread
    if head:
        head.run_forever()
    else:
        # If no head, block main thread with conversation
        run_convo()
