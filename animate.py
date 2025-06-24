import pygame
import numpy as np

class Animate:
    def __init__(self, head):
        self.head = head

    def get_mouth_rect(self):
        img_width = self.head.scaled_image.get_width()
        img_height = self.head.scaled_image.get_height()

        center_x = int(self.head.image_x + img_width * self.head.mouth_region["x"])
        center_y = int(self.head.image_y + img_height * self.head.mouth_region["y"])
        width = int(img_width * self.head.mouth_region["width"])
        height = int(img_height * self.head.mouth_region["height"])
        return (center_x - width // 2, center_y - height // 2, width, height)

    def manipulate_mouth(self):
        self.head.image = self.head.base_image.copy()
        left, top, width, height = self.get_mouth_rect()

        img_width = self.head.scaled_image.get_width()
        img_height = self.head.scaled_image.get_height()
        rel_left = max(0, left - self.head.image_x)
        rel_top = max(0, top - self.head.image_y)
        rel_right = min(img_width, rel_left + width)
        rel_bottom = min(img_height, rel_top + height)

        if not self.tts.completed_speaking():
            openness = abs(np.sin(pygame.time.get_ticks() / 100)) * 0.7
            try:
                upper_height = height // 2
                lower_height = height - upper_height

                mouth_surface = self.head.base_image.subsurface(pygame.Rect(
                    left, top, width, height
                ))

                upper_lip = pygame.Surface((width, upper_height), pygame.SRCALPHA)
                upper_lip.blit(mouth_surface, (0, 0), (0, 0, width, upper_height))

                lower_lip = pygame.Surface((width, lower_height), pygame.SRCALPHA)
                lower_lip.blit(mouth_surface, (0, 0), (0, upper_height, width, lower_height))

                move_amount = int(height * openness * 0.3)
                cavity_left = left + (width - int(width * 0.7)) // 2
                cavity_top = top - move_amount

                pygame.draw.rect(self.head.image, (10, 0, 0), 
                                 (left, cavity_top, width, height + move_amount))

                self.head.image.blit(upper_lip, (left, cavity_top))
                self.head.image.blit(lower_lip, (left, top + upper_height + move_amount))
            except Exception as e:
                print(f"Error manipulating mouth: {e}")

    def draw_mouth_region_editor(self, screen):
        rect = self.get_mouth_rect()
        pygame.draw.rect(screen, (255, 0, 0), rect, 2)
