import argparse

from speech_to_text import Listener, select_input_device
from robot.head_controller import HeadController  # Import the TalkingHead class
from process_request import ChatBotProcessor
from tts.tts_engine import TTSEngine  
from robot.sound_device_monitor import OutputMonitor
from survivor.process_games import SurvivorGames
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
        "Let me ponder that for a moment...",
        "thinking, thinking....",
        "I hear you. Let's see...",
    ])

class Conversation:
    def __init__(
            self,
            audio_device=None,
            prompt=constants.JEFF_PROMPT,
            tts_type="local",
            asr_engine="whisper",
            tts_engine=None
        ):
        self.listener = Listener(device=audio_device, model="en-us", engine=asr_engine)  # Initialize listener with ASR engine

        self.tts_engine = tts_engine
        if tts_engine is None:
            self.tts_engine = TTSEngine(tts_type=tts_type)  # Initialize TTS engine

        self.processor = ChatBotProcessor(
            initial_prompt=prompt
        )
        self.lock_tts = threading.Lock()
        self.proccessor_lock = threading.Lock()


    def process_request(self, callback_fn=None, debug=False) -> str:
        if debug:
            print("TTS Speaking Status: ", self.tts_engine.speaking)
            print("Processor Status: ", self.processor.processing)

        if not self.tts_engine.completed_speaking() or self.processor.processing:
            if debug:
                print("Currently processing a request or TTS is active. Please wait...")
            time.sleep(1.0)
            return
            
        print("Handling new request... \n")
        action_text = self.listener.listen()      
        print(f"Received: \n {action_text}")

        if not action_text:
            if debug:
                print("No input received, skipping processing.")
            return
    
        print(f"\n {'*'* 20} \n")
        
        if callback_fn:
            cb_text = callback_fn(action_text)
            if cb_text:
                action_text + f"/[cb action taken: {cb_text}/]"

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
                        self.tts_engine.speak(output)  # Use talking_head.say
                    buffer = " ".join(words[i + 1 :])

        if preload:
            ## Hiding Latency with a useless pre-phrase
            speak_or_buffer(_prefix_phrase())

        self.processor.process_user_interaction(action_text, speak_or_buffer)

        while self.processor.processing or not self.tts_engine.completed_speaking():
            if buffer:
                with self.lock_tts:
                    self.tts_engine.speak(buffer) 
            time.sleep(0.2)
        
        print("****** PROCESSING COMPLETE TTS DONE ******")

    def start(self, callback_fn=None):
        print("Starting conversation... Hit ctrl-c to end")
        self.continue_talking = True
        try: 
            while self.continue_talking:
                self.process_request(callback_fn=callback_fn)
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
    args.add_argument("--headless", default=False, action="store_true", help="Run without GUI (no talking head)")
    args.add_argument("--text", default=None, help="Text to process instead of listening to audio")
    args.add_argument("--say", default=None, help="Text to say immediately without processing")
    args.add_argument("--asr", default="whisper", choices=["whisper", "vosk"], help="ASR model to use")

    args = args.parse_args()
    
    tts_engine = None 
    cb = None #No callback on process request unless overridden

    if args.character.lower() == "jeff":
        prompt = constants.JEFF_PROMPT
        image = constants.JEFF_IMAGE

        print("Setting Survivor Callback func")
        game_class = SurvivorGames()
        cb = game_class.request_cb

    elif args.character.lower() == "lizard":
        prompt = constants.LIZARD_PROMPT
        image = constants.LIZARD_IMAGE
    elif args.character.lower() == "ben":
        prompt = constants.BEN_PROMPT
        ref_audio = constants.BEN_REF_WAV
        ref_audio_text = constants.BEN_REF_TEXT
        image = constants.BEN_IMAGE
        tts_engine = TTSEngine(
            tts_type="f5_tts",
            f5_ref_audio_path=constants.BEN_REF_WAV,
            f5_ref_audio_text=constants.BEN_REF_TEXT
        )

    device = args.device
    if args.select_device:
        device = select_input_device()
    conversation = Conversation(
        audio_device=device,
        prompt=prompt,
        tts_type=args.tts,
        tts_engine=tts_engine)
    
    if args.say:
        print(f"Saying: {args.say}")
        with conversation.lock_tts:
            conversation.tts_engine.speak(args.say)
            while not conversation.tts_engine.completed_speaking():
                time.sleep(10)

            print("Done speaking.")
            conversation.tts_engine.cleanup()

    elif args.text:
        print(f"Processing text: {args.text}")
        conversation.run_request_processing_engine(args.text, preload=False)
    else:
        print("Starting conversation thread...")
        conversation_thread = threading.Thread(target=conversation.start, args=(cb,))
        conversation_thread.start()
    
    if not args.headless:
        talking_head = HeadController(gpio=args.use_gpio, image_path=image)
        try:
            talking_head.run()
        except KeyboardInterrupt:
            print("Stopping head controller...")
            talking_head.cleanup()