#!/usr/bin/env python3
import time
import random
import argparse
import pigpio
import threading
from enum import IntEnum

MIN_SERVO_PULSE = 600
MAX_SERVO_PULSE = 2400
MOUTH_PIN = 13
EYES_PIN  = 12
ARM_PIN_0 = 19

class EyePosition(IntEnum):
    OPEN    = 0
    BLINK   = 90
    SHOCKED = 179

class ArmPosition(IntEnum):
    UP = 130
    DOWN = 0

class AnimationComponent(threading.Thread):
    def __init__(self, name, delay_func, step_func, check_interval=0.01):
        super().__init__(name=name)
        self.delay_func     = delay_func
        self.step_func      = step_func
        self.check_interval = check_interval
        self.last_run       = time.time()
        self.stop_event     = threading.Event()
        self.daemon         = True

    def run(self):
        while not self.stop_event.is_set():
            now   = time.time()
            delay = self.delay_func()
            if now - self.last_run >= delay:
                try:
                    self.step_func()
                except Exception as e:
                    print(f"[{self.name}] Error: {e}")
                self.last_run = now
            time.sleep(self.check_interval)

    def stop(self):
        self.stop_event.set()

class RobotHead:
    def __init__(self,
                 mouth_pin=MOUTH_PIN,
                 eye_pin=EYES_PIN,
                 mouth_closed_angle=100,
                 mouth_open_angle=0,
                 arm_down_angle=ArmPosition.DOWN.value,
                 arm_up_angle=ArmPosition.UP.value,
                 arm_delay=5,
                 flap_delay_range=(0.05, 0.2),
                 blink_delay=0.3,
                 opened_delay=2.0,
                 shocked_delay=3.0):
        self.pi = pigpio.pi()
        if not self.pi.connected:
            raise RuntimeError("Could not connect to pigpiod. Start with 'sudo pigpiod'.")

        self.mouth_pin       = mouth_pin
        self.eye_pin         = eye_pin
        self.arm_pin         = ARM_PIN_0
        self.mouth_closed    = mouth_closed_angle
        self.mouth_open      = mouth_open_angle
        self.arm_down        = arm_down_angle
        self.arm_up          = arm_up_angle

        self.flap_delay_range = flap_delay_range
        self.blink_delay       = blink_delay
        self.opened_delay      = opened_delay
        self.shocked_delay     = shocked_delay
        self.arm_delay         = arm_delay

        self.is_mouth_open = False
        self.eye_state     = EyePosition.OPEN
        self.arm_angle     = self.arm_down
        self.speaking      = False

        self._set_servo(self.eye_pin,   EyePosition.OPEN.value, move_delay=0.05)
        self._set_servo(self.mouth_pin, self.mouth_closed,      move_delay=0.05)
        self._move_arm(ArmPosition.DOWN)

        self.mouth_comp = AnimationComponent("Mouth", self._mouth_delay, self._mouth_step)
        self.eyes_comp  = AnimationComponent("Eyes",  self._eyes_delay,  self._eyes_step)
        self.arm_comp   = AnimationComponent("Arm",   self._arm_delay,   self._arm_step)
        for component in (self.mouth_comp, self.eyes_comp, self.arm_comp): 
            component.start()
        

    def angle_to_pulse(self, angle: float) -> float:
        pulse = MIN_SERVO_PULSE + (angle/180.0)*(MAX_SERVO_PULSE-MIN_SERVO_PULSE)
        pulse = max(MIN_SERVO_PULSE, pulse)
        pulse = min(MAX_SERVO_PULSE, pulse)
        return pulse

    def _set_servo(self, pin: int, angle: float, move_delay=0.05):
        self.pi.set_servo_pulsewidth(pin, self.angle_to_pulse(angle))
        time.sleep(move_delay)

    def _mouth_delay(self):
        return random.uniform(*self.flap_delay_range) if self.speaking else (0.05 if self.is_mouth_open else float('inf'))
    
    def _mouth_step(self):
        if self.speaking:
            self._close_mouth() if self.is_mouth_open else self._open_mouth()
        elif self.is_mouth_open:
            self._close_mouth()

    def _open_mouth(self, variable_width=False):
        angle = random.uniform(self.mouth_open, self.mouth_open+15) if variable_width else self.mouth_open
        self._set_servo(self.mouth_pin, angle, move_delay=random.uniform(*self.flap_delay_range))
        self.is_mouth_open=True

    def _close_mouth(self):
        self._set_servo(self.mouth_pin, self.mouth_closed, move_delay=random.uniform(*self.flap_delay_range))
        self.is_mouth_open=False

    def _eyes_delay(self):
        if self.eye_state==EyePosition.BLINK: return self.blink_delay
        if self.eye_state==EyePosition.SHOCKED: return self.shocked_delay
        return self.opened_delay + random.uniform(-0.2,0.5)
    
    def _eyes_step(self):
        if self.eye_state in (EyePosition.BLINK, EyePosition.SHOCKED):
            self._set_eyes(EyePosition.OPEN, self.opened_delay)
        else:
            choice = random.random()
            if choice < 0.4: 
                self._set_eyes(EyePosition.BLINK, self.blink_delay)
            elif self.speaking and choice < 0.6: 
                self._set_eyes(EyePosition.SHOCKED, self.shocked_delay)

    def _set_eyes(self, pos: EyePosition, delay): 
        self.eye_state=pos; self._set_servo(self.eye_pin,pos.value,move_delay=delay)

    def _arm_delay(self): 
        return self.arm_delay * random.uniform(1, 4.5) if self.speaking else self.arm_delay

    def _arm_step(self):
        if self.speaking:
            # The arm_delay randomizes how rapid arm movements are
            self._move_arm(ArmPosition.UP if self.arm_angle==self.arm_down else ArmPosition.DOWN)
        elif not self.speaking and self.arm_angle!=self.arm_down:
            self._move_arm(ArmPosition.DOWN)

    def _move_arm(self, pos: ArmPosition, step_size=30, delay=0.2):
        tgt = self.arm_up if pos==ArmPosition.UP else self.arm_down
        step = step_size if tgt > self.arm_angle else -step_size
        for angle in range(self.arm_angle, tgt + step, step):
            self._set_servo(self.arm_pin, angle, move_delay=delay)
        self._set_servo(self.arm_pin, tgt)    
        self.arm_angle = tgt
        self.last_arm_change = time.time()

    def move(self, speaking_state: bool): 
        # threaded components are watching state of speaking flag 
        # This triggers motion in their respective _step functions 

        self.speaking = speaking_state

    def cleanup(self):
        for c in (self.mouth_comp,self.eyes_comp,self.arm_comp):
            c.stop()
            c.join()

        self._set_servo(self.eye_pin,EyePosition.OPEN.value)
        self._set_servo(self.mouth_pin,self.mouth_closed)
        self._move_arm(ArmPosition.DOWN)

        self.pi.set_servo_pulsewidth(self.mouth_pin,0)
        self.pi.set_servo_pulsewidth(self.eye_pin,0)
        self.pi.stop()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Control the robot's head servos.")
    parser.add_argument('--set-mouth', type=int, help='Set mouth servo angle (0-180)')
    parser.add_argument('--set-eyes',  type=int, help='Set eyes servo angle (0-180)')
    parser.add_argument('--set-arm',   choices=["UP","DOWN"], help='Set arm position (UP or DOWN)')
    parser.add_argument('--run',       action='store_true', help='Run the head animation')
    args = parser.parse_args()

    controller = RobotHead()
    if args.set_mouth is not None:
        controller._set_servo(controller.mouth_pin, args.set_mouth)
        time.sleep(2)
    elif args.set_eyes is not None:
        controller._set_servo(controller.eye_pin, args.set_eyes)
        time.sleep(2)
    elif args.set_arm is not None:
        controller._move_arm(ArmPosition[args.set_arm])
    elif args.run:
        try:
            while True:
                controller.set_speaking((time.time()%4)<2)
                time.sleep(0.05)
        except KeyboardInterrupt:
            print("Stopping...")
            controller.cleanup()
    else:
        parser.print_help()

    controller.cleanup()
