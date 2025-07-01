#!/usr/bin/env python3
import time
import random
import argparse
import pigpio
from enum import IntEnum

MOUTH_PIN = 13
EYES_PIN = 12
ARM_PIN_0 = 19

class EyePosition(IntEnum):
    OPEN    = 0
    BLINK   = 90
    SHOCKED = 179

class ArmPosition(IntEnum):
    UP   = 0
    DOWN = 180  

class RobotHead:
    def __init__(
        self,
        mouth_pin=MOUTH_PIN,
        eye_pin=EYES_PIN,
        mouth_closed_angle=60,
        mouth_open_angle=0,
        arm_down_angle=0,
        arm_up_angle=180
    ):
        self.pi = pigpio.pi()
        if not self.pi.connected:
            raise RuntimeError("Could not connect to pigpiod. Start with 'sudo pigpiod'.")
        self.mouth_pin = mouth_pin
        self.eye_pin = eye_pin
        self.mouth_closed = mouth_closed_angle
        self.mouth_open = mouth_open_angle

        self.arm_down = arm_down_angle
        self.arm_up = arm_up_angle

        # Mouth state
        self.is_mouth_open = False
        self.last_mouth_move = time.time()
        self.flap_delay_range = (0.05, 0.2)

        # Eye state
        self.eye_state = EyePosition.OPEN
        self.last_eye_state_change = time.time()
        self.blink_delay   = 0.3
        self.opened_delay  = 2.0
        self.shocked_delay = 3.0
        
        self.arm_delay = 3
        self.last_arm_change = time.time()
        self.arm_angle = self.arm_down

        # Initialize servos
        self._set_servo(self.eye_pin,   EyePosition.OPEN.value, move_delay=0.05)
        self._set_servo(self.mouth_pin, self.mouth_closed,      move_delay=0.05)
        self._toggle_arm(ArmPosition.DOWN)


    def angle_to_pulse(self, angle: float) -> float:
        min_pw = 500   # pulse width for 0°
        max_pw = 2400  # pulse width for 180°
        return min_pw + (angle / 180.0) * (max_pw - min_pw)

    def _set_servo(self, pin: int, angle: float, move_delay=0.05):
        pw = self.angle_to_pulse(angle)
        self.pi.set_servo_pulsewidth(pin, pw)
        time.sleep(move_delay)
    
    def _toggle_arm(self, state: ArmPosition):
        """Toggle arm position."""

        current_angle = self.arm_angle 

        if state == ArmPosition.UP:
            new_angle = self.arm_up
        elif state == ArmPosition.DOWN:
            new_angle = self.arm_down
        else:
            raise ValueError("Invalid arm position")

        step_size = 10 

        if new_angle < current_angle:
            step_size = -step_size 
        
        for i in range(current_angle, new_angle, step_size):
            self._set_servo(ARM_PIN_0, i, move_delay=0.05)
        
        self.arm_angle = new_angle
        self.last_arm_change = time.time()

    # ─── MOUTH HELPERS ───────────────────────────────────────────────────────────
    def _toggle_mouth_open(self, variable_width=False):
        delay = random.uniform(*self.flap_delay_range)
        if variable_width:
            angle = random.uniform(self.mouth_open, self.mouth_open + 15)
        else:
            angle = self.mouth_open
        self._set_servo(self.mouth_pin, angle, move_delay=delay)
        self.is_mouth_open = True

    def _toggle_mouth_close(self):
        delay = random.uniform(*self.flap_delay_range)
        self._set_servo(self.mouth_pin, self.mouth_closed, move_delay=delay)
        self.is_mouth_open = False

    # ─── EYE HELPERS ───────────────────────────────────────────────────────────────
    def _toggle_eyes(self, position: EyePosition, move_delay: float):
        self.eye_state = position
        self._set_servo(self.eye_pin, position.value, move_delay=move_delay)

    def _toggle_blink(self):
        self._toggle_eyes(EyePosition.BLINK, self.blink_delay)

    def _toggle_surprised(self):
        self._toggle_eyes(EyePosition.SHOCKED, self.shocked_delay)

    def _toggle_eyes_open(self):
        self._toggle_eyes(EyePosition.OPEN, self.opened_delay)

    def _get_eye_delay(self) -> float:
        if self.eye_state == EyePosition.BLINK:
            return self.blink_delay
        elif self.eye_state == EyePosition.SHOCKED:
            return self.shocked_delay
        else:
            # open-eye hold plus some randomness
            return self.opened_delay + random.uniform(-0.2, 0.5)

    # ─── MAIN ANIMATION LOOP ───────────────────────────────────────────────────────
    def move(self, speaking: bool):
        now = time.time()

        # Mouth logic
        if speaking:
            # reset on start so first flap is immediate
            if now - self.last_mouth_move > 1.0:
                self.last_mouth_move = now

            if now - self.last_mouth_move >= random.uniform(*self.flap_delay_range):
                if self.is_mouth_open:
                    self._toggle_mouth_close()
                else:
                    self._toggle_mouth_open(variable_width=False)
                self.last_mouth_move = now

        else:
            if self.is_mouth_open:
                self._set_servo(self.mouth_pin, self.mouth_closed, move_delay=0.05)
                self.is_mouth_open = False
            self.last_mouth_move = now

        # Eye logic
        if now - self.last_eye_state_change > self._get_eye_delay():
            if self.eye_state in (EyePosition.BLINK, EyePosition.SHOCKED):
                self._toggle_eyes_open()
            else:
                if random.random() < 0.4:
                    self._toggle_blink()
                elif speaking and random.random() < 0.01:
                    self._toggle_surprised()
            self.last_eye_state_change = now
        
        # Arm logic 
        if now - self.last_arm_change > self.arm_delay:
            if random.random() < 0.05 and speaking:
                if self.arm_angle == self.arm_down:
                    self._toggle_arm(ArmPosition.UP)
                else:
                    self._toggle_arm(ArmPosition.DOWN)

    def cleanup(self):
        # reset and stop pulses
        self._set_servo(self.eye_pin,   EyePosition.OPEN.value)
        self._set_servo(self.mouth_pin, self.mouth_closed)
        self.pi.set_servo_pulsewidth(self.mouth_pin, 0)
        self.pi.set_servo_pulsewidth(self.eye_pin,   0)
        self.pi.stop()

def main():
    parser = argparse.ArgumentParser(description="Control the robot's head servos.")
    parser.add_argument('--set-mouth', type=int, help='Set mouth servo angle (0-180)')
    parser.add_argument('--set-eyes',  type=int, help='Set eyes servo angle (0-180)')
    parser.add_argument('--set-arm',  type=int, help='Set arm servo angle (0-180)')

    parser.add_argument('--run',       action='store_true', help='Run the head animation')
    args = parser.parse_args()

    controller = RobotHead()

    if args.set_mouth is not None:
        controller._set_servo(MOUTH_PIN, args.set_mouth)
        controller.cleanup()
    elif args.set_eyes is not None:
        controller._set_servo(EYES_PIN, args.set_eyes)
        controller.cleanup()
    elif args.set_arm is not None:
        controller._set_servo(ARM_PIN_0, args.set_arm)
        controller.cleanup()
    elif args.run:
        try:
            while True:
                # example: speak 2s, silent 2s
                speaking = (time.time() % 4) < 2
                controller.move(speaking)
                time.sleep(0.05)
        except KeyboardInterrupt:
            print("Stopping...")
        finally:
            controller.cleanup()
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
