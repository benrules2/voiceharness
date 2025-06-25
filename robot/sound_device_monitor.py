import platform
import time
import sounddevice as sd
import numpy as np
from threading import Thread


class OutputMonitor:
    def __init__(self, blocksize=2048, rate=44100, update_interval=0.2, device=None):
        if not device:
            self.device = self._find_monitor_device()
        else:
            self.device = device 

        self.blocksize = blocksize
        self.rate = rate
        self.update_interval = update_interval
        self.last_level = 0
        self.running = False
        self.stream = None
        self.thread = None

    def _find_monitor_device(self):
        """Find appropriate audio monitoring device based on OS."""
        sys = platform.system()
        devices = sd.query_devices()
        
        print(f"Detected OS: {sys}")
        print("Available audio devices:")
        for idx, dev in enumerate(devices):
            if dev["max_input_channels"] > 0:
                print(f"  {idx}: {dev['name']} (inputs: {dev['max_input_channels']})")
        
        for idx, dev in enumerate(devices):
            name = dev["name"].lower()
            if dev["max_input_channels"] == 0:
                continue
                
            if sys == "Linux" and "monitor" in name:
                print(f"Monitoring Linux monitor device: {dev['name']}")
                return idx
            elif sys == "Darwin" and any(k in name for k in ("blackhole", "soundflower")):
                print(f"Monitoring macOS loopback device: {dev['name']}")
                return idx
            elif sys == "Windows" and any(k in name for k in ("stereo mix", "what u hear", "wave out mix")):
                print(f"Monitoring Windows stereo mix device: {dev['name']}")
                return idx
        
        # Fallback: try default input device
        default_device = sd.default.device[0]
        if default_device is not None:
            print(f"Using default input device: {devices[default_device]['name']}")
            return default_device
            
        raise RuntimeError(
            "No suitable output-monitoring device found.\n"
            "Linux: Install PulseAudio/PipeWire with monitor support\n"
            "macOS: Install BlackHole (`brew install blackhole-2ch`) and set up Multi-Output Device\n"
            "Windows: Enable 'Stereo Mix' in recording devices"
        )

    def _callback(self, indata, frames, time, status):
        """Audio callback function."""
        if status:
            print(f"Audio status: {status}", flush=True)
        
        # Calculate RMS level and convert to 0-100 scale
        if len(indata) > 0:
            # Handle mono or stereo input
            if indata.ndim == 1:
                level = np.sqrt(np.mean(indata**2))
            else:
                # Average across channels for stereo
                level = np.sqrt(np.mean(np.mean(indata**2, axis=1)))
            
            # Scale to 0-100 and apply some gain for visibility
            self.last_level = min(100, int(level * 1000))

    def _monitor_loop(self):
        """Background thread loop for monitoring."""
        try:
            print(f"Starting audio stream on device {self.device}")
            self.stream = sd.InputStream(
                device=self.device,
                channels=2,
                blocksize=self.blocksize,
                samplerate=self.rate,
                callback=self._callback,
                dtype=np.float32
            )
            self.stream.start()
            print("Audio monitoring active...")
            
            while self.running:
                time.sleep(self.update_interval)
                    
        except Exception as e:
            print(f"\nError in monitoring loop: {e}")
            self.running = False
        finally:
            if self.stream:
                self.stream.stop()
                self.stream.close()

    def start(self):
        """Start monitoring in a background thread."""
        if not self.running:
            self.running = True
            self.thread = Thread(target=self._monitor_loop, daemon=True)
            self.thread.start()

    def stop(self):
        """Stop monitoring."""
        if self.running:
            self.running = False
            if self.stream:
                self.stream.stop()
                self.stream.close()
            if self.thread and self.thread.is_alive():
                self.thread.join(timeout=1.0)
            print("Monitoring stopped.")

    def sound_level(self):
        """Get current sound level (0-100)."""
        return self.last_level

    def is_running(self):
        """Check if monitoring is currently active."""
        return self.running

    def display_level(self, show_bar=True):
        """Display current audio level (useful for debugging)."""
        level = self.last_level
        if show_bar:
            bar = "█" * (level // 5) + "░" * (20 - level // 5)
            print(f"Level: [{bar}] {level:3d}%")
        else:
            print(f"Audio level: {level}%")

    def run_blocking(self, seconds=None, show_visual=True):
        """Run monitoring with blocking behavior and optional visual display."""
        self.start()
        
        if seconds:
            start_time = time.time()
            try:
                while time.time() - start_time < seconds and self.running:
                    if show_visual:
                        level = self.last_level
                        bar = "█" * (level // 5) + "░" * (20 - level // 5)
                        print(f"\rLevel: [{bar}] {level:3d}%", end="", flush=True)
                    time.sleep(self.update_interval)
            except KeyboardInterrupt:
                print("\nMonitoring stopped by user.")
            finally:
                self.stop()
        else:
            try:
                while self.running:
                    if show_visual:
                        level = self.last_level
                        bar = "█" * (level // 5) + "░" * (20 - level // 5)
                        print(f"\rLevel: [{bar}] {level:3d}%", end="", flush=True)
                    time.sleep(self.update_interval)
            except KeyboardInterrupt:
                print("\nMonitoring stopped by user.")
                self.stop()
                
def test_devices():
    """Test function to list available audio devices."""
    print("Available audio devices:")
    devices = sd.query_devices()
    for idx, device in enumerate(devices):
        device_type = []
        if device['max_input_channels'] > 0:
            device_type.append(f"input({device['max_input_channels']})")
        if device['max_output_channels'] > 0:
            device_type.append(f"output({device['max_output_channels']})")
        
        print(f"{idx:2d}: {device['name']} - {', '.join(device_type)}")
    
    print(f"\nDefault input device: {sd.default.device[0]}")
    print(f"Default output device: {sd.default.device[1]}")


if __name__ == "__main__":
    print("🔊 Audio Output Monitor")
    print("=" * 50)
    
    # Uncomment to see all available devices
    # test_devices()
    # print()
    
    try:
        monitor = OutputMonitor()
        print("Press Ctrl-C to stop monitoring")
        
        # Use the blocking version for command-line usage
        monitor.run_blocking()
        
    except Exception as e:
        print(f"Error: {e}")
        print("\nTry running test_devices() to see available audio devices.")


