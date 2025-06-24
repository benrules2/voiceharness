import argparse

from speech_to_text import Listener, select_input_device
from talking_head import TalkingHead  # Import the TalkingHead class
from process_request import ChatBotProcessor
from tts.tts_engine import TTSEngine  
import random

import constants 

import re
import threading
import time

def _prefix_phrase():
    """Returns a prefix phrase to hide latency."""
    return random.choice([
        "Processing your request...",
        "Let me think about that...",
        "Well Well Well...",
        "Hmm, that's an interesting question...",
        "Give me a second to consider that...",
        "Let me ponder that for a moment..."
    ])

class Conversation:
    def __init__(
            self,
            audio_device=None,
            image_path=constants.JEFF_IMAGE,
            use_gpio=True,
            prompt=constants.JEFF_PROMPT,
            tts_type="local"):
        self.listener = Listener(device=audio_device, model="en-us")
        self.tts_engine = TTSEngine(tts_type=tts_type)  # Initialize TTS engine

        # self.talking_head = TalkingHead(image_path=image_path, use_gpio=use_gpio, tts=tts_type)  # Initialize TalkingHead
        self.processor = ChatBotProcessor(
            initial_prompt=prompt
        )
        self.lock_tts = threading.Lock()
        self.proccessor_lock = threading.Lock()

    def process_request(self) -> str:
        print("TTS Speaking Status: ", self.tts_engine.speaking)
        print("Processor Status: ", self.processor.processing)

        if not self.tts_engine.completed_speaking() or self.processor.processing:
            print("Currently processing a request or TTS is active. Please wait...")
            time.sleep(0.1)
            return
            
        print("Handling new request...")
        action_text = self.listener.listen()      
        print(f"Received: {action_text}")
        self.run_request_processing_engine(action_text)

        time.sleep(1)
    
    def run_request_processing_engine(self, action_text: str, preload: bool = True):
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

        if preload:
            ## Hiding Latency with a useless pre-phrase
            speak_or_buffer(_prefix_phrase())

        self.processor.process_user_interaction(action_text, speak_or_buffer)

        while self.processor.processing or not self.tts_engine.completed_speaking():
            if buffer:
                with self.lock_tts:
                    self.talking_head.say(buffer) 
            time.sleep(0.2)
        
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
            self.tts_engine.cleanup()


if __name__ == "__main__":
    args = argparse.ArgumentParser()
    args.add_argument("--device", default=None)
    args.add_argument("--select_device", default=False, action="store_true",)
    args.add_argument("--use_gpio", default=False, action="store_true",)
    args.add_argument("--character", default="jeff")
    args.add_argument("--tts", default="local")

    args = args.parse_args()
    
    if args.character.lower() == "jeff":
        prompt = constants.JEFF_PROMPT
        image = constants.JEFF_IMAGE
    elif args.character.lower() == "lizard":
        prompt = constants.LIZARD_PROMPT
        image = constants.LIZARD_IMAGE

    device = args.device
    if args.select_device:
        device = select_input_device()
    conversation = Conversation(audio_device=device, use_gpio=args.use_gpio, prompt=prompt, image_path=image, tts_type=args.tts)

    # Start conversation.start() in a separate thread
    conversation_thread = threading.Thread(target=conversation.start)
    conversation_thread.start()

    try:
        conversation.talking_head.run()
    finally:
        conversation.talking_head.tts.cleanup()