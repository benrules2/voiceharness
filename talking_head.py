import pygame
import pygame.gfxdraw
import numpy as np
import time
import os
import json 

from gtts import gTTS
from pygame import mixer
import threading
import queue
from argparse import ArgumentParser

from animate import Animate

class TalkingHead:
    def __init__(self, image_path, width=800, height=600):
        # Initialize pygame
        pygame.init()
        mixer.init()
        
        self.text_queue = queue.Queue()  # Thread-safe queue for receiving text
        self.check_text_thread = threading.Thread(target=self._check_text_queue, daemon=True)
        # Set up display
        self.width = width
        self.height = height
        self.screen = pygame.display.set_mode((width, height))
        pygame.display.set_caption("Talking Photo Head")
        
        # Load the image
        self.image_path = image_path
        self.original_image = pygame.image.load(image_path)
        # Scale the image to fit the screen while maintaining aspect ratio
        self.scale_image()
        
        # Get a copy of the image that we'll modify
        self.image = self.scaled_image.copy()
        self.base_image = self.scaled_image.copy()  # Store an unmodified copy
        
        # Colors
        self.mouth_color = (200, 100, 100)
        
        # Mouth region configuration - ADJUST THESE VALUES FOR YOUR SPECIFIC IMAGE
        # These are normalized coordinates (0-1) that will be scaled to the actual image size
        self.mouth_region = {
            "x": 0.5,        # Center point x (0-1)
            "y": 0.7,        # Center point y (0-1)
            "width": 0.2,    # Width of mouth region (0-1)
            "height": 0.1    # Height of mouth region (0-1)
        }
        
        # State variables
        self.running = True
        self.is_talking = False
        self.mouth_openness = 0
        
        # Audio variables
        self.audio_file = "temp_speech.mp3"

    def _check_text_queue(self):
        while True:
            try:
                text = self.text_queue.get(timeout=0.1)  # Check for new text every 0.1 seconds
                self.speak(text)  # Speak the text
            except queue.Empty:
                time.sleep(0.1)  # Sleep briefly if no text is available
                continue

    def scale_image(self):
        """Scale the image to fit the screen while maintaining aspect ratio"""
        img_width, img_height = self.original_image.get_size()
        
        # Calculate scaling factor
        scale_w = self.width / img_width
        scale_h = self.height / img_height
        scale = min(scale_w, scale_h)
        
        # Scale the image
        new_width = int(img_width * scale)
        new_height = int(img_height * scale)
        self.scaled_image = pygame.transform.scale(self.original_image, (new_width, new_height))
        
        # Calculate position to center the image
        self.image_x = (self.width - new_width) // 2
        self.image_y = (self.height - new_height) // 2
        
    def get_mouth_rect(self):
        """Convert the normalized mouth region to actual pixel coordinates"""
        img_width = self.scaled_image.get_width()
        img_height = self.scaled_image.get_height()
        
        center_x = int(self.image_x + img_width * self.mouth_region["x"])
        center_y = int(self.image_y + img_height * self.mouth_region["y"])
        width = int(img_width * self.mouth_region["width"])
        height = int(img_height * self.mouth_region["height"])
        
        # Return rectangle (left, top, width, height)
        return (center_x - width//2, center_y - height//2, width, height)
        
    def generate_speech(self, text):
        """Generate TTS audio from text"""
        tts = gTTS(text=text, lang='en')
        tts.save(self.audio_file)

    @staticmethod
    def check_audio(self):
        while mixer.music.get_busy():
            time.sleep(0.1)
        self.is_talking = False
            
    def play_speech(self):
        """Play the speech audio"""
        self.is_talking = True
        mixer.music.load(self.audio_file)
        mixer.music.play()
        
        # Monitor when audio stops playing
        def check_audio():
            while mixer.music.get_busy():
                time.sleep(0.5)
            self.is_talking = False

        threading.Thread(target=check_audio).start()
    
    def say(self, text):
        """Generate and play speech"""
        print("Queuing:", text)    
        self.text_queue.put(text)

    def speak(self, text):
        self.generate_speech(text)
        self.play_speech()

        while self.is_talking:
            time.sleep(0.1)
    
    def completed_speaking(self):
        """Check if the speech is over"""
        return not self.is_talking and self.text_queue.empty()
    
    def manipulate_mouth(self):
        """Manipulate the mouth area of the image itself, not just draw over it"""
        # Make a fresh copy of the base image
        self.image = self.base_image.copy()
        
        # Get mouth rectangle
        mouth_rect = self.get_mouth_rect()
        left, top, width, height = mouth_rect
        
        # Ensure coordinates are within image bounds
        img_width = self.scaled_image.get_width()
        img_height = self.scaled_image.get_height()
        rel_left = max(0, left - self.image_x)
        rel_top = max(0, top - self.image_y)
        rel_right = min(img_width, rel_left + width)
        rel_bottom = min(img_height, rel_top + height)
        
        if self.is_talking:
            # Calculate mouth openness with a sine wave
            openness = abs(np.sin(pygame.time.get_ticks() / 100)) * 0.7
            
            try:
                # Define the mouth lip regions (upper and lower halves)
                upper_height = height // 2
                lower_height = height - upper_height
                
                # Extract the entire mouth region first
                mouth_surface = self.base_image.subsurface(pygame.Rect(
                    left, top, width, height
                ))
                
                # Split the mouth into upper and lower parts
                upper_lip = pygame.Surface((width, upper_height), pygame.SRCALPHA)
                upper_lip.blit(mouth_surface, (0, 0), 
                            (0, 0, width, upper_height))
                
                lower_lip = pygame.Surface((width, lower_height), pygame.SRCALPHA)
                lower_lip.blit(mouth_surface, (0, 0), 
                            (0, upper_height, width, lower_height))
                
                # Calculate movement amount based on openness
                move_amount = int(height * openness * 0.3)
                
                # Draw the mouth cavity (dark area behind the lips) FIRST
                cavity_height = move_amount * 2
                cavity_width = int(width * 0.7)
                cavity_left = left + (width - cavity_width) // 2
                cavity_top = top - move_amount
                
                # Draw a dark ellipse for the mouth cavity BEFORE drawing the lips
                pygame.draw.rect(self.image, (10, 0, 0), 
                                (left, cavity_top, width, height + move_amount))
                
                
                # NOW draw the lips on top of the cavity
                # Draw the upper lip (moved up)
                self.image.blit(upper_lip, (left, cavity_top))
                
                # # Draw the lower lip (moved down)
                self.image.blit(lower_lip, (left, top + upper_height + move_amount))
                
            except Exception as e:
                print(f"Error manipulating mouth: {e}")
                print(f"Rect values: left={left}, top={top}, width={width}, height={height}")
                print(f"Image size: {self.base_image.get_size()}")
    
    def draw_mouth_region_editor(self):
        """Draw a rectangle around the mouth region for editing purposes"""
        mouth_rect = self.get_mouth_rect()
        pygame.draw.rect(self.screen, (255, 0, 0), mouth_rect, 2)  # Draw in red
   
    def handle_events(self, event, edit_mode):
        if event.type == pygame.QUIT:
            self.running = False
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self.running = False
            elif event.key == pygame.K_SPACE:
                # Say something when space is pressed
                self.say("Hello there! I am a talking photo animation.")
            elif event.key == pygame.K_1:
                self.say("Survivor is a game of strategy and survival.")
            elif event.key == pygame.K_2:
                self.say("Outwit, outlast, and outplay!")
        elif edit_mode and event.type == pygame.MOUSEBUTTONDOWN:
            # In edit mode, allow repositioning the mouth by clicking
            x, y = event.pos
            img_width = self.scaled_image.get_width()
            img_height = self.scaled_image.get_height()
            
            # Convert to normalized coordinates
            norm_x = (x - self.image_x) / img_width
            norm_y = (y - self.image_y) / img_height
            
            # Update mouth position
            if 0 <= norm_x <= 1 and 0 <= norm_y <= 1:
                self.mouth_region["x"] = norm_x
                self.mouth_region["y"] = norm_y
                print(f"Mouth position updated to x:{norm_x:.2f}, y:{norm_y:.2f}")

        # Adjust mouth size with keyboard in edit mode
        if edit_mode and event.type == pygame.KEYDOWN:
            if event.key == pygame.K_UP:
                self.mouth_region["height"] = min(0.5, self.mouth_region["height"] + 0.01)
            elif event.key == pygame.K_DOWN:
                self.mouth_region["height"] = max(0.01, self.mouth_region["height"] - 0.01)
            elif event.key == pygame.K_RIGHT:
                self.mouth_region["width"] = min(0.5, self.mouth_region["width"] + 0.01)
            elif event.key == pygame.K_LEFT:
                self.mouth_region["width"] = max(0.01, self.mouth_region["width"] - 0.01)        

    def init_mouth_rect(self):
        """Setup step"""
        mouth_box_path = self.image_path.split(".")[0] + '_mouth.json'

        # Load mouth region from file if it exists
        if os.path.exists(mouth_box_path):
            with open(mouth_box_path, 'r') as f:
                self.mouth_region = json.load(f)
            return self.mouth_region

        clock = pygame.time.Clock()

        
        while self.running:
            # Handle events
            for event in pygame.event.get():
                self.handle_events(event, edit_mode=True)
            
            if not self.running:
                break

            # Draw everything
            self.screen.fill((240, 240, 240))  # Background
            
            self.image = self.base_image.copy()
            
            # Draw the image with manipulated mouth
            self.screen.blit(self.image, (self.image_x, self.image_y))
            
            self.draw_mouth_region_editor()
            
            # Display instructions
            font = pygame.font.SysFont(None, 24)
            instructions = [
                "EDIT MODE: Click to position mouth",
                "Arrow keys to resize mouth",
                "Space/1/2 to test speech",
                "ESC to quit"
            ]
            
            for i, text in enumerate(instructions):
                surf = font.render(text, True, (0, 0, 0))
                self.screen.blit(surf, (10, 10 + 25 * i))
            
            # Update the display
            pygame.display.flip()
            
            # Cap at 30 FPS
            clock.tick(30)

            with open(mouth_box_path, 'w') as f:
                json.dump(self.mouth_region, f)

        pygame.quit()
        
        return self.mouth_region

    def run(self, edit_mode=False):
        """Main animation loop"""
        self.check_text_thread.start()
        clock = pygame.time.Clock()
        
        print("running main loop of talking head")

        while self.running:
            try:
                # Handle events
                for event in pygame.event.get():
                    self.handle_events(event, edit_mode)
                
                # Draw everything
                self.screen.fill((240, 240, 240))  # Background
                
                # Update the mouth if talking
                if self.is_talking:
                    self.manipulate_mouth()
                else:
                    # Reset to base image when not talking
                    self.image = self.base_image.copy()
                
                # Draw the image with manipulated mouth
                self.screen.blit(self.image, (self.image_x, self.image_y))
                
                # If in edit mode, draw the mouth region outline
                if edit_mode:
                    self.draw_mouth_region_editor()
                    
                    # Display instructions
                    font = pygame.font.SysFont(None, 24)
                    instructions = [
                        "EDIT MODE: Click to position mouth",
                        "Arrow keys to resize mouth",
                        "Space/1/2 to test speech",
                        "ESC to quit"
                    ]
                    
                    for i, text in enumerate(instructions):
                        surf = font.render(text, True, (0, 0, 0))
                        self.screen.blit(surf, (10, 10 + 25 * i))
                
                # Update the display
                pygame.display.flip()
                
                # Cap at 30 FPS
                clock.tick(30)
            except Exception as e:
                print(f"Error in main loop: {e}")
                
        # Clean up
        if os.path.exists(self.audio_file):
            try:
                os.remove(self.audio_file)
            except:
                pass
        pygame.quit()


def main(image_path):
    # Check if image exists
    if not os.path.exists(image_path):
        print(f"Error: Image file '{image_path}' not found.")
        print("Please provide a valid image path.")
        return
    
    # First run in edit mode to position the mouth
    print("EDIT MODE ACTIVATED")
    print("Click on the image to position the mouth")
    print("Use arrow keys to resize the mouth")
    print("Press Space/1/2 to test speech")
    print("Press ESC when done")
    
    talking_head = TalkingHead(image_path)
    talking_head.init_mouth_rect()
    talking_head.run()

if __name__ == "__main__":
    parser = ArgumentParser(description="Talking Photo Head Animation")
    parser.add_argument("--image_path", type=str, help="Path to the image file", default="head.webp")
    
    args = parser.parse_args()
    image_path = args.image_path
    
    # Run the main function with the provided image path    
    main(image_path=image_path)