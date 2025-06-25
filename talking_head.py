import pygame
import time
import os
import re 
import constants
import threading

from speech_to_text import select_input_device
from conversation import Conversation

from enum import StrEnum

from tts.local_tts import TextToSpeech
from tts.eleven_labs import ElevenLabsTTS  # Assuming this is the correct import for ElevenLabs TTS
from robot.pygame_head import PygameHead

from tts.tts_engine import TTSEngine
from robot.sound_device_monitor import OutputMonitor


class TTSType(StrEnum):
    LOCAL = "local"
    ELEVEN_LABS = "eleven_labs"
    F5_TTS = "f5_tts"

class TalkingHead:
    def __init__(self, image_path="head.webp", use_gpio=True, tts_engine=TTSEngine(tts_type=TTSType.LOCAL)):

        self.tts = tts_engine  # Initialize TTS engine
        self.running = True

        self.use_gpio = use_gpio

        if use_gpio:
            print("Using GPIO for head control")
            from robot.gpio_head import RobotHead
            self.head = RobotHead()
        else:
            self.use_pygame = True
            self.head = PygameHead(image_path)
        # self.output_monitor = OutputMonitor()
        # self.output_monitor.start()

    def say(self, text):
        cleaned_text = re.sub(r'[^a-zA-Z0-9\s.,!?\'’\""]', ' ', text)
        self.tts.speak(cleaned_text)

    def is_speaking(self, silence_threshold=0.05):
        """
        Check if the TTS engine is currently speaking.
        """
        # audio_playing = self.output_monitor.sound_level() < silence_threshold

        # if audio_playing:
        #     return True
        
        if not self.tts.completed_speaking():
            return True

        return False

    def run(self):
        clock = pygame.time.Clock() if self.use_pygame else None

        while self.running:
            if self.use_pygame:
                for event in pygame.event.get():
                    if event.type == pygame.QUIT or (event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE):
                        self.running = False

            speaking = not self.tts.completed_speaking()
            self.head.move(speaking)

            if clock:
                clock.tick(30)
            else:
                time.sleep(0.1)  # ~30 FPS fallback pacing for servo control

def start_conversation_thread(character, tts):
    if character.lower() == "jeff":
        prompt = constants.JEFF_PROMPT
        image = constants.JEFF_IMAGE
    elif args.character.lower() == "lizard":
        prompt = constants.LIZARD_PROMPT
        image = constants.LIZARD_IMAGE

    device = args.device
    if args.select_device:
        device = select_input_device()
    conversation = Conversation(audio_device=device, prompt=prompt, tts_type=tts)

        # Start conversation.start() in a separate thread
    conversation_thread = threading.Thread(target=conversation.start)
    conversation_thread.start()

    return conversation_thread 

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--image_path", type=str, default="head.webp")
    parser.add_argument("--tts", type=str, choices=[t.value for t in TTSType], default=TTSType.F5_TTS,
                        help="Select TTS type: local, eleven_labs, f5_tts")
    parser.add_argument("--text", type=str, default=None)
    parser.add_argument("--textfile", type=str, default=None)
    parser.add_argument("--device", default=None)
    parser.add_argument("--select_device", default=False, action="store_true",)
    parser.add_argument("--use_gpio", default=False, action="store_true",)
    parser.add_argument("--character", default="jeff")
    parser.add_argument("--tts", default="local")
    parser.add_argument("--animated", action="store_true", help="Run with pygame head")
    parser.add_argument("--robot", action="store_true", help="Run with pygame head")



    args = parser.parse_args()
 
    convo = start_conversation_thread(character=args.character, prompt=constants.JEFF_PROMPT, tts=args.tts)
    
    tts_engine = TTSEngine(tts_type=TTSType(args.tts))

    if args.robot:
        talking_head = TalkingHead(use_gpio=True, tts_engine=tts_engine)
    


  