from robot.sound_device_monitor import OutputMonitor
import argparse
import pygame


class HeadController:
    def __init__(self, gpio=False, threshold=0.05, image_path="head.webp", loopback_device=None):
        self.gpio = gpio
        if not gpio:
            self.use_pygame = True
            from robot.pygame_head import PygameHead
            head = PygameHead(image_path)
        else:
            self.use_pygame = False
            from robot.gpio_head import RobotHead
            head = RobotHead()
        self.head = head
        self.threshold = threshold
        self.output_monitor = OutputMonitor(device=loopback_device)
        self.running = False

    def run(self):
        self.running = True
        self.output_monitor.start()
        while self.running:
            if not self.gpio:
                for event in pygame.event.get():
                    if event.type == pygame.QUIT or (event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE):
                        pygame.quit()
                        exit()

            volume_level = self.output_monitor.sound_level()

            speaking = volume_level > self.threshold  # Adjust threshold as needed

            self.head.move(speaking)

            if self.use_pygame:
                pygame.time.delay(100)

    def cleanup(self):
        self.running = False
        self.head.cleanup()
        self.output_monitor.stop()
        if self.use_pygame:
            pygame.quit()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Control the robot's head.")
    parser.add_argument("--use_gpio", action="store_true", help="Use GPIO for head control")
    parser.add_argument("--use_pygame", action="store_true", help="Use Pygame for head control")
    parser.add_argument("--image_path", type=str, default="head.webp", help="Path to the head image (if using Pygame)")
    parser.add_argument("--threshold", type=float, default=0.05, help="Sound level threshold to determine if speaking")
    parser.add_argument("--loopback_device", type=int, default=None, help="Device to monitor loopback")


    args = parser.parse_args()

    head_controller = HeadController(gpio=args.use_gpio, threshold=args.threshold, loopback_device=args.loopback_device)
    head_controller.run()



    



