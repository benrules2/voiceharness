import pygame
import time
import os
import re 
import json
import numpy as np
from text_to_speech import TextToSpeech
from robot.mouth_controllers import HeadController

class PygameHeadAnimation:
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
        config_path = self.image_path.replace(".webp", "_mouth.json")
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

    def move_mouth(self, speaking):
        self.image = self.base_image.copy()
        if not speaking:
            return

        left, top, width, height = self._get_mouth_rect()
        openness = abs(np.sin(pygame.time.get_ticks() / 100)) * 0.7
        upper_height = height // 2
        lower_height = height - upper_height
        move_amt = int(height * openness * 0.3)

        mouth_surface = self.base_image.subsurface(pygame.Rect(left, top, width, height))
        upper_lip = pygame.Surface((width, upper_height), pygame.SRCALPHA)
        lower_lip = pygame.Surface((width, lower_height), pygame.SRCALPHA)
        upper_lip.blit(mouth_surface, (0, 0), (0, 0, width, upper_height))
        lower_lip.blit(mouth_surface, (0, 0), (0, upper_height, width, lower_height))

        pygame.draw.rect(self.image, (10, 0, 0), (left, top - move_amt, width, height + move_amt))
        self.image.blit(upper_lip, (left, top - move_amt))
        self.image.blit(lower_lip, (left, top + upper_height + move_amt))

    def draw(self):
        self.screen.fill((240, 240, 240))
        self.screen.blit(self.image, (self.image_x, self.image_y))
        pygame.display.flip()


class TalkingHead:
    def __init__(self, image_path, use_gpio=True):
        self.tts = TextToSpeech(rate=200)
        self.running = True

        if use_gpio:
            self.head = HeadController()
        else:
            self.head = PygameHeadAnimation(image_path)

    def say(self, text):
        cleaned_text = re.sub(r'[^a-zA-Z0-9\s.,!?\'’\""]', ' ', text)
        self.tts.speak(cleaned_text)

    def run(self):
        is_pygame = isinstance(self.head, PygameHeadAnimation)
        clock = pygame.time.Clock() if is_pygame else None

        while self.running:
            if is_pygame:
                for event in pygame.event.get():
                    if event.type == pygame.QUIT or (event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE):
                        self.running = False

            
            self.head.move(self.tts.speaking)

            if clock:
                clock.tick(30)
            else:
                time.sleep(0.03)  # ~30 FPS fallback pacing for servo control



if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--image_path", type=str, default="head.webp")
    args = parser.parse_args()

    talking_head = TalkingHead(args.image_path)
    talking_head.say("Hello there! I'm alive!")
    talking_head.run()
