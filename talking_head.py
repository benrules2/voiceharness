import pygame
import time
import os
import re 
from enum import StrEnum

from tts.local_tts import TextToSpeech
from tts.eleven_labs import ElevenLabsTTS  # Assuming this is the correct import for ElevenLabs TTS
from robot.pygame_head import PygameHead

from tts.tts_engine import TTSEngine
from tts.sound_device_monitor import OutputMonitor


class TTSType(StrEnum):
    LOCAL = "local"
    ELEVEN_LABS = "eleven_labs"
    F5_TTS = "f5_tts"

class TalkingHead:
    def __init__(self, image_path, use_gpio=True, tts=TTSType.LOCAL):

        self.tts = TTSEngine(tts_type=tts)  # Initialize TTS engine
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


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--image_path", type=str, default="head.webp")
    parser.add_argument("--use_gpio", action="store_true", help="Use GPIO for head control")
    parser.add_argument("--tts", type=str, choices=[t.value for t in TTSType], default=TTSType.F5_TTS,
                        help="Select TTS type: local, eleven_labs, f5_tts")
    parser.add_argument("--text", type=str, default=None)
    parser.add_argument("--textfile", type=str, default=None)
    args = parser.parse_args()

    talking_head = TalkingHead(args.image_path, use_gpio=args.use_gpio, tts=args.tts)  # Set use_gpio=True if using GPIO
    if args.text:
        talking_head.say(args.text)

    if args.textfile:
        if os.path.exists(args.textfile):
            with open(args.textfile, 'r') as f:
                text = f.read().strip()
                talking_head.say(text)
        else:
            print(f"Text file {args.textfile} does not exist. Using default text.")

    if not args.text and not args.textfile:
        talking_head.say("You didn't tell me what to say!")

    talking_head.run()

    while True:
        try:
            if talking_head.tts.completed_speaking():
                print("Speaking completed, exiting...")
                talking_head.running = False
                break
            time.sleep(1)
        except KeyboardInterrupt:
            print("Exiting...")
            talking_head.running = False
            break