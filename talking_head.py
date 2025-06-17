import pygame
import time
import os
import re 
import json
import numpy as np
from text_to_speech import TextToSpeech
from tts.eleven_labs import ElevenLabsTTS  # Assuming this is the correct import for ElevenLabs TTS

class PygameHead:
    def __init__(self, image_path, width=800, height=600):
        pygame.init()
        self.width = width
        self.height = height
        self.screen = pygame.display.set_mode((width, height))
        pygame.display.set_caption("Talking Head")

        self.original_image = pygame.image.load(image_path)
        self.image = self._scale_image(self.original_image)
        self.base_image = self.image.copy()
        self.image_path = image_path

        self.image_x = (width - self.image.get_width()) // 2
        self.image_y = (height - self.image.get_height()) // 2

        self.mouth_region = {
            "x": 0.5, "y": 0.7, "width": 0.2, "height": 0.1
        }
        self._load_mouth_config()

    def _scale_image(self, img):
        scale = min(self.width / img.get_width(), self.height / img.get_height())
        return pygame.transform.scale(img, (int(img.get_width() * scale), int(img.get_height() * scale)))

    def _load_mouth_config(self):
        base_path = self.image_path.rsplit('.', 1)[0]
        config_path = base_path + "_mouth.json"
        if os.path.exists(config_path):
            with open(config_path, 'r') as f:
                self.mouth_region = json.load(f)

    def _get_mouth_rect(self):
        img_w, img_h = self.image.get_width(), self.image.get_height()
        cx = int(self.image_x + img_w * self.mouth_region['x'])
        cy = int(self.image_y + img_h * self.mouth_region['y'])
        w = int(img_w * self.mouth_region['width'])
        h = int(img_h * self.mouth_region['height'])
        return (cx - w//2, cy - h//2, w, h)

    def move(self, speaking):
        self.image = self.base_image.copy()
        left, top, width, height = self._get_mouth_rect()

        if speaking:
            openness = abs(np.sin(pygame.time.get_ticks() / 100)) * 0.7
            try:
                upper_height = height // 2
                lower_height = height - upper_height

                mouth_surface = self.base_image.subsurface(pygame.Rect(
                    left, top, width, height
                ))

                upper_lip = pygame.Surface((width, upper_height), pygame.SRCALPHA)
                upper_lip.blit(mouth_surface, (0, 0), (0, 0, width, upper_height))

                lower_lip = pygame.Surface((width, lower_height), pygame.SRCALPHA)
                lower_lip.blit(mouth_surface, (0, 0), (0, upper_height, width, lower_height))

                move_amount = int(height * openness * 0.3)
                cavity_left = left + (width - int(width * 0.7)) // 2
                cavity_top = top - move_amount

                pygame.draw.rect(self.image, (10, 0, 0), 
                                 (left, cavity_top, width, height + move_amount))

                self.image.blit(upper_lip, (left, cavity_top))
                self.image.blit(lower_lip, (left, top + upper_height + move_amount))
            except Exception as e:
                print(f"Error manipulating mouth: {e}")
            
        self.draw()

    def draw(self):
        self.screen.fill((240, 240, 240))
        self.screen.blit(self.image, (self.image_x, self.image_y))
        pygame.display.flip()


class TalkingHead:
    def __init__(self, image_path, use_gpio=True):
        self.tts = ElevenLabsTTS()
        self.running = True

        self.use_gpio = use_gpio
        if use_gpio:
            print("Using GPIO for head control")
            from robot.mouth_controllers import HeadController
            self.head = HeadController()
        else:
            self.use_pygame = True
            self.head = PygameHead(image_path)

    def say(self, text):
        cleaned_text = re.sub(r'[^a-zA-Z0-9\s.,!?\'’\""]', ' ', text)
        self.tts.speak(cleaned_text)

    def run(self):
        clock = pygame.time.Clock() if self.use_pygame else None

        while self.running:
            if self.use_pygame:
                for event in pygame.event.get():
                    if event.type == pygame.QUIT or (event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE):
                        self.running = False

            
            self.head.move(self.tts.speaking)

            if clock:
                clock.tick(30)
            else:
                time.sleep(0.1)  # ~30 FPS fallback pacing for servo control



if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--image_path", type=str, default="head.webp")
    args = parser.parse_args()

    talking_head = TalkingHead(args.image_path, use_gpio=False)  # Set use_gpio=True if using GPIO
    talking_head.say("Hello there! I'm alive!")
    talking_head.run()
