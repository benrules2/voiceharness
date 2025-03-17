#!/usr/bin/env python3

# prerequisites: as described in https://alphacephei.com/vosk/install and also python module `sounddevice` (simply run command `pip install sounddevice`)
# Example usage using Dutch (nl) recognition model: `python test_microphone.py -m nl`
# For more help run: `python test_microphone.py -h`

import argparse
import queue
import sys
import sounddevice as sd

from json import dumps, loads
from datetime import datetime

from vosk import Model, KaldiRecognizer

def select_input_device():
    devices = sd.query_devices()
    for i, device in enumerate(devices):
        if device["max_input_channels"] > 0:
            print(f"Device {i}: \n" + dumps(device) + "\n ---- \n")

    index = int(input("Enter the index of the device you want to use: "))
    print(f"Using device {index} ")
    return index

class Listener():
    def __init__(self, device=0, model="en-us"):
        #    model_name="vosk-model-en-us-0.22-lgraph" - slower but better model

        self.model = Model(lang=model, model_name="vosk-model-small-en-us-0.15")
        self.device = device
        self.q = queue.Queue()

        device_info = sd.query_devices(self.device, "input")
        self.samplerate = int(device_info["default_samplerate"])
        
    def listen(self, max_duration=20):
        with sd.RawInputStream(samplerate=self.samplerate, blocksize = 8000, device=self.device,
            dtype="int16", channels=1, callback=self.callback):
            print("#" * 80)
            print("Press Ctrl+C to stop the recording")
            print("#" * 80)

            rec = KaldiRecognizer(self.model, self.samplerate)

            start_time = datetime.now()

            while True:
                data = self.q.get()
                if rec.AcceptWaveform(data):
                    output = rec.Result()
                    return loads(output).get("text", None)
                
                if (datetime.now() - start_time).seconds > max_duration:
                    partial = rec.PartialResult()
                    print('partial', partial)
                    return partial

    def callback(self, indata, frames, time, status):
        if status:
            print(status, file=sys.stderr)
        self.q.put(bytes(indata))


if __name__ == "__main__":

    def int_or_str(text):
        """Helper function for argument parsing."""
        try:
            return int(text)
        except ValueError:
            return text


    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument(
        "-l", "--list-devices", action="store_true",
        help="show list of audio devices and exit")
    args, remaining = parser.parse_known_args()
    if args.list_devices:
        print(sd.query_devices())
        parser.exit(0)
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        parents=[parser])
    parser.add_argument(
        "-f", "--filename", type=str, metavar="FILENAME",
        help="audio file to store recording to")
    parser.add_argument(
        "-d", "--device", type=int_or_str,
        help="input device (numeric ID or substring)")
    parser.add_argument(
        "-r", "--samplerate", type=int, help="sampling rate")
    parser.add_argument(
        "-m", "--model", type=str, help="language model; e.g. en-us, fr, nl; default is en-us", default="en-us")
    args = parser.parse_args(remaining)

    try:            
        if args.model is None:
            model = Model(lang="en-us")
        else:
            model = Model(lang=args.model)

        listener = Listener(device=args.device, model=args.model)
        
        while True:
            listener.listen()

    except KeyboardInterrupt:
        print("\nDone")
        parser.exit(0)
    except Exception as e:
        parser.exit(type(e).__name__ + ": " + str(e))