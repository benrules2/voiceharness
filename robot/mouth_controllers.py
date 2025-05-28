import time
import random
import argparse
import pigpio

MOUTH_PIN = 13
EYES_PIN = 12

class HeadController:
    def __init__(
        self,
        mouth_pin=MOUTH_PIN,
        eye_pin=EYES_PIN,
        mouth_closed_angle=0,
        mouth_open_angle=30,
        eye_positions=(0, 45, 90, 135, 180),
    ):
        self.pi = pigpio.pi()
        if not self.pi.connected:
            raise RuntimeError("Could not connect to pigpiod. Start with 'sudo pigpiod'.")

        self.mouth_pin = mouth_pin
        self.eye_pin = eye_pin
        self.mouth_closed = mouth_closed_angle
        self.mouth_open = mouth_open_angle
        self.eye_positions = eye_positions

        self.is_mouth_open = False
        self.last_mouth_move = 0
        self.eye_index = 0
        self.last_eye_move = time.time()

        self.eye_delay = 0.75  # seconds between eye sweeps

    def angle_to_pulse(self, angle):
        min_pw = 500     # Full left (0°)
        max_pw = 2400    # Full right (180°)
        return min_pw + (angle / 180.0) * (max_pw - min_pw)

    def _set_servo(self, pin, angle):
        pw = self.angle_to_pulse(angle)
        self.pi.set_servo_pulsewidth(pin, pw)
        time.sleep(0.2)
        # print(f"[GPIO {pin}] → angle {angle} → pulse {int(pw)}µs")

    def move(self, speaking: bool):
        now = time.time()

        # -- Mouth animation: flap open/closed while speaking --
        if speaking:
            if now - self.last_mouth_move > random.uniform(0.2, 0.5):
                # Alternate open/close state
                angle = random.randint(self.mouth_closed + 0.5 * self.mouth_open, self.mouth_open) if not self.is_mouth_open else self.mouth_closed
                self._set_servo(self.mouth_pin, angle)
                self.is_mouth_open = not self.is_mouth_open
                self.last_mouth_move = now
        else:
            # If not speaking, ensure mouth is closed
            if self.is_mouth_open:
                self._set_servo(self.mouth_pin, self.mouth_closed)
                self.is_mouth_open = False

        # -- Eyes: occasional idle motion --
        if now - self.last_eye_move > self.eye_delay and random.random() < 0.03:
            angle = self.eye_positions[self.eye_index]
            self._set_servo(self.eye_pin, angle)
            self.eye_index = (self.eye_index + 1) % len(self.eye_positions)
            self.last_eye_move = now

    def cleanup(self):
        self._set_servo(self.eye_pin, self.eye_positions[0])  # Reset eyes to first position
        self._set_servo(self.mouth_pin, self.mouth_closed)
        self.pi.set_servo_pulsewidth(self.mouth_pin, 0)
        self.pi.set_servo_pulsewidth(self.eye_pin, 0)
        self.pi.stop()

def _set_servos(mouth_angle, eye_angle):
    controller = HeadController()
    controller._set_servo(MOUTH_PIN, mouth_angle)
    controller._set_servo(EYES_PIN, eye_angle)

def main():
    parser = argparse.ArgumentParser(description="Control the robot's head servos.")
    parser.add_argument('--set-mouth', type=int, help='Set mouth servo angle (0-180)')
    parser.add_argument('--set-eyes', type=int, help='Set eyes servo angle (0-180)')
    parser.add_argument('--run', action='store_true', help='Run the head animation')

    args = parser.parse_args()

    if args.set_mouth is not None or args.set_eyes is not None:
        mouth_angle = args.set_mouth if args.set_mouth is not None else 0
        eye_angle = args.set_eyes if args.set_eyes is not None else 0
        _set_servos(mouth_angle, eye_angle)
    elif args.run:
        controller = HeadController()
        try:
            while True:
                speaking = (time.time() % 4) < 2
                controller.move(speaking)
                time.sleep(0.1)
        except KeyboardInterrupt:
            print("Stopping...")
        finally:
            controller.cleanup()
    else:
        parser.print_help()

if __name__ == "__main__":
    main()