import argparse

from speech_to_text import Listener, select_input_device
from text_to_speech import TextToSpeech
from process_request import ChatBotProcessor

import re
import threading

class Conversation:
    def __init__(self, device=None):
        self.device = device if device else select_input_device()
        self.listener = Listener(device=self.device, model="en-us")
        self.tts = TextToSpeech(rate=200)
        self.processor = ChatBotProcessor(
            initial_prompt="""
            You are a helpful AI assistant who can control smart home devices. 
            Ensure to get all devices before trying to control specific entities.
            You only need to list once, and then you can control the devices.
            Make judgment calls about their location based on the name.

            You are a voice assistant, so be very brief in responses.
            """
        )
        self.lock_tts = threading.Lock()
    def process_request(self) -> str:
        print("Handling new request...")
        action_text = self.listener.listen()      
        print(f"Received: {action_text}")
        self.run_request_processing_engine(action_text)
    
    def run_request_processing_engine(self, action_text: str):
        buffer = ""
        def speak_or_buffer(delta: str):
            nonlocal buffer
            buffer += delta
            words = buffer.split(" ")

            # Check for punctuation or long words
            for i, word in enumerate(words):
                if len(word) > 20 or re.search(r"[.!?;:]", word):
                    output = " ".join(words[: i + 1])
                    print(f"Speaking: {output}")
                    self.tts.speak(output)
                    buffer = " ".join(words[i + 1 :])

        self.processor.process_user_interaction(
            message=action_text,
            streaming_callback=speak_or_buffer)

        if buffer:
            self.tts.speak(buffer)  

    def start(self):
        print("Starting conversation... Hit ctrl-c to end")
        self.continue_talking = True
        try: 
            while self.continue_talking:
                self.process_request()
        except KeyboardInterrupt:
            print("Conversation ended")
            self.continue_talking = False


if __name__ == "__main__":

    args = argparse.ArgumentParser()
    args.add_argument("--device", default=None)
    args.add_argument("--disable_smarthome", action="store_true")
    args = args.parse_args()

    conversation = Conversation(device=args.device)
    if not args.disable_smarthome:
        print("Adding Home Assistant skill...")
        import skills.home_assistant as home_assistant
        home_assistant_client = home_assistant.HomeAssistantClient()
        conversation.processor.add_tool(home_assistant_client.list_devices_schema(), home_assistant_client.list_devices)
        conversation.processor.add_tool(home_assistant_client.control_light_schema(), home_assistant_client.set_device_state)
        conversation.processor.add_tool(home_assistant_client.list_device_types_schema(), home_assistant_client.list_device_types)

    conversation.start()
