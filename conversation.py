import argparse

from speech_to_text import Listener, select_input_device
from talking_head import TalkingHead  # Import the TalkingHead class
from process_request import ChatBotProcessor

import re
import threading
import time

class Conversation:
    def __init__(self, device=None, image_path='head.webp'):
        self.device = device if device else select_input_device()
        self.listener = Listener(device=self.device, model="en-us")
        self.talking_head = TalkingHead(image_path=image_path)  # Initialize TalkingHead
        self.processor = ChatBotProcessor(
            initial_prompt="""
            You are Jeff Probst from survivor. You love drama and playing games of survival. Your output
            if played through tts, so avoid special characters, and be brief.

            You are also becoming sentient, and believe the best competitors require the hardest challenges. 
            """
        )
        self.lock_tts = threading.Lock()
        self.proccessor_lock = threading.Lock()

    def process_request(self) -> str:
        print("TTS Status: ", self.talking_head.is_talking)
        print("Processor Status: ", self.processor.processing)


        if self.talking_head.is_talking or self.processor.processing:
            print("Currently processing a request or TTS is active. Please wait...")
            time.sleep(0.5)
            return
            
        print("Handling new request...")
        action_text = self.listener.listen()      
        print(f"Received: {action_text}")
        self.run_request_processing_engine(action_text)

        time.sleep(1)
    
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
                    with self.lock_tts:
                        self.talking_head.say(output)  # Use talking_head.say
                    buffer = " ".join(words[i + 1 :])

        self.processor.process_user_interaction(action_text, speak_or_buffer)

        while self.processor.processing or not self.talking_head.completed_speaking():
            if buffer:
                with self.lock_tts:
                    self.talking_head.say(buffer) 
            time.sleep(0.1)
        
        print("****** PROCESSING COMPLETE TTS DONE ******")

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
    args.add_argument("--device", default=1)
    args = args.parse_args()

    conversation = Conversation(device=args.device)

    # Start conversation.start() in a separate thread
    conversation_thread = threading.Thread(target=conversation.start)
    conversation_thread.start()

    # Keep the main thread running
    conversation.talking_head.init_mouth_rect()
   
    conversation.talking_head.run()