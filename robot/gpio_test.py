import time
import argparse
import pigpio

MIN_PULSE = 600    # corresponds to 0°
MAX_PULSE = 2400   # corresponds to 180°

def angle_to_pulse(angle: float) -> float:
    """Convert 0–180° to MIN_PULSE–MAX_PULSE."""
    return MIN_PULSE + (angle / 180.0) * (MAX_PULSE - MIN_PULSE)

def main():
    parser = argparse.ArgumentParser(description="Move a servo to a given angle")
    parser.add_argument('--pin',   type=int, required=True, help="GPIO pin number")
    parser.add_argument('--angle', type=float, required=True, help="Target angle (0–180°)")
    parser.add_argument('--hold',  type=float, default=2.0, help="Seconds to hold position")
    args = parser.parse_args()

    if not 0 <= args.angle <= 180:
        parser.error("Angle must be between 0 and 180°")

    pi = pigpio.pi()
    if not pi.connected:
        raise RuntimeError("Could not connect to pigpiod. Run `sudo pigpiod` first.")

    try:
        pulse = angle_to_pulse(args.angle)
        pi.set_servo_pulsewidth(args.pin, pulse)
        print(f"Moved pin {args.pin} to {args.angle}° (pulse {pulse:.0f}µs)")
        time.sleep(args.hold)
    finally:
        pi.set_servo_pulsewidth(args.pin, 0)
        pi.stop()

if __name__ == "__main__":
    main()
