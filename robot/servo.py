import pigpio
import time

class Servo:
    def __init__(self, pi, pin, min_angle=0, max_angle=180, start_angle=0):
        self.pi = pi
        self.pin = pin
        self.min_angle = min_angle
        self.max_angle = max_angle
        self.move_to(start_angle)

    def angle_to_pulsewidth(self, angle):
        angle = max(self.min_angle, min(self.max_angle, angle))
        min_pw = 500     # Full left (0°)
        max_pw = 2400    # Full right (180°)
        return min_pw + (angle / 180.0) * (max_pw - min_pw)

    def move_to(self, angle):
        pw = self.angle_to_pulsewidth(angle)
        self.pi.set_servo_pulsewidth(self.pin, pw)
        print(f"[{self.pin}] Angle {angle} → pulse {int(pw)}")
        time.sleep(0.5)  # Let servo reach position

    def stop(self):
        pw = self.move_to(self.min_angle)
        self.pi.set_servo_pulsewidth(self.pin, 0)  # Stop signal


# Initialize pigpio
pi = pigpio.pi()
if not pi.connected:
    raise RuntimeError("pigpiod not running. Start with 'sudo pigpiod'")

# Create servo instances
eyes_servo = Servo(pi, pin=12, min_angle=0, max_angle=180, start_angle=0)
mouth_servo = Servo(pi, pin=13, min_angle=0, max_angle=180, start_angle=90)

# Eye animation
def eyes_animation():
    for angle in [0, 45, 90, 135, 180]:
        print(f"Eyes → {angle}°")
        eyes_servo.move_to(angle)
        time.sleep(0.1)

# Mouth animation
def mouth_animation():
    for _ in range(3):
        print("Mouth opening")
        mouth_servo.move_to(180)
        time.sleep(0.1)
        print("Mouth closing")
        mouth_servo.move_to(90)
        time.sleep(0.2)

try:
    while True:
        eyes_animation()
        break

except KeyboardInterrupt:
    print("Exiting...")

finally:
    eyes_servo.stop()
    mouth_servo.stop()
    pi.stop()
