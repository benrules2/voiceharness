import time
import random
import argparse
import pigpio
from enum import Enum

MOUTH_PIN = 13
EYES_PIN = 12

class EyePosition(int, Enum):
    OPEN = 0
    BLINK = 90
    SHOCKED = 179

class RobotHead:
    def __init__(
        self,
        mouth_pin=MOUTH_PIN,
        eye_pin=EYES_PIN,
        mouth_closed_angle=0,
        mouth_open_angle=18,
        eye_positions=(EyePosition.OPEN.value, EyePosition.BLINK.value, EyePosition.SHOCKED.value),
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
        self.blink_delay = 0.3  # seconds between blinks
        self.shocked_delay = 5.0  # seconds for shocked state
        self.opened_delay = 3.0
        self.eye_state = 0  # 0: open, 1: blink, 2: shocked
        self.last_eye_state_change = time.time()
        self.dialog_started = False

    def angle_to_pulse(self, angle):
        min_pw = 500  # Full left (0°)
        max_pw = 2400  # Full right (180°)
        return min_pw + (angle / 180.0) * (max_pw - min_pw)

    def _set_servo(self, pin, angle, move_delay=0.2):
        pw = self.angle_to_pulse(angle)
        self.pi.set_servo_pulsewidth(pin, pw)
        time.sleep(move_delay)


    def _toggle_mouth(self, target_angle, delay_range, now):
        delay = random.uniform(*delay_range)
        self._set_servo(self.mouth_pin, target_angle, move_delay=delay)
        self.is_mouth_open = not self.is_mouth_open
        self.last_mouth_move = now
        
    def move(self, speaking: bool):
        now = time.time()
        # -- Mouth animation: flap open/closed while speaking --

        if speaking:
            if not self.dialog_started:
                time.sleep(0.3)  # Initial delay before starting dialog
                self.dialog_started = True

            if self.is_mouth_open:
                self._toggle_mouth(self.mouth_closed, (0.1, 0.3), now)
            else:
                self._toggle_mouth(self.mouth_open, (0.01, 0.08), now)

        else:
            # If not speaking, ensure mouth is closed
            if self.is_mouth_open:
                self._set_servo(self.mouth_pin, self.mouth_closed)
                self.is_mouth_open = False
                self.dialog_started = False

        # -- Eyes: handle different eye states (open, blink, shocked) --
        if now - self.last_eye_state_change > self._get_eye_delay():
            if self.eye_state != EyePosition.BLINK:  # If shocked or 
                if random.random() < 0.03:
                    self.eye_state = 1  # Transition to blink
                    self._set_servo(self.eye_pin, EyePosition.BLINK.value)
                    self.last_eye_state_change = now
            elif self.eye_state == EyePosition.BLINK:  # Blink
                self.eye_state = 0  # Return to open eyes
                self._set_servo(self.eye_pin, EyePosition.OPEN.value)
                self.last_eye_state_change = now
            elif self.eye_state == EyePosition.SHOCKED:  # Shocked state
                self.eye_state = 0  # Return to open eyes
                self._set_servo(self.eye_pin, EyePosition.OPEN.value)
                self.last_eye_state_change = now

            # Occasionally trigger shocked state
            if random.random() < 0.01 and speaking:
                self.eye_state = EyePosition.SHOCKED  # Transition to shocked
                self._set_servo(self.eye_pin, EyePosition.SHOCKED.value)
                self.last_eye_state_change = now

    def _get_eye_delay(self):
        if self.eye_state == 1:  # Blink
            return self.blink_delay
        elif self.eye_state == 2:  # Shocked
            return self.shocked_delay
        else:  # Open eyes
            return self.opened_delay + random.uniform(-0.1 * self.opened_delay, 0.5 * self.opened_delay)
          # Use blink delay for open eyes

    def cleanup(self):
        self._set_servo(self.eye_pin, EyePosition.OPEN.value)  # Reset eyes to open
        self._set_servo(self.mouth_pin, self.mouth_closed)
        self.pi.set_servo_pulsewidth(self.mouth_pin, 0)
        self.pi.set_servo_pulsewidth(self.eye_pin, 0)
        self.pi.stop()

def _set_servos(mouth_angle, eye_angle):
    controller = RobotHead()
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
        controller = RobotHead()
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