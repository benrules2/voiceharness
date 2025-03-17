import cohere
import json
import os
import threading
from typing import List, Dict, Optional, Callable


class ChatBotProcessor:
    
    def __init__(self, initial_prompt: str, api_key: Optional[str] = None):
        if api_key is None:
            api_key = os.getenv('COHERE_API_KEY')
            if not api_key:
                api_key = input("Enter your Cohere API key: ")

        self.co = cohere.ClientV2(api_key)
        self.chat_history = [{"role": "system", "content": initial_prompt}]

    
    def add_message_to_chat_context(self, message: str, role: str = "user"):
        self.chat_history.append({"role": role, "content": message})

    def process_user_interaction(self, message: str, streaming_callback: Callable[[str], None]):
        if message == "":
            return ""
        
        self.add_message_to_chat_context(message)
        
        res = self.co.chat_stream(
            model="command-a-03-2025",
            messages=self.chat_history,
        )

        response = ""
        for event in res:
            if event and (event.type == "content-delta"):
                delta = event.delta.message.content.text
                response += delta
                
                if streaming_callback:
                    streaming_callback(delta)
                    
            if event.type == "content-end":
                self.add_message_to_chat_context(response, role="assistant")
    
    def clear_history(self) -> None:
        """Clear the chat history except for the initial prompt"""
        initial_prompt = self.chat_history[0]
        self.chat_history = [initial_prompt] 

if __name__ == "__main__":
    chatbot = ChatBotProcessor("You are a helpful AI assistant.")

    def streaming_callback(text: str):
        print(text)

    print("Chatbot is ready! Type 'exit' to quit.")
    while True:
        user_input = input("You: ")
        if user_input.lower() == "exit":
            break
        chatbot.process_user_interaction(user_input, streaming_callback)
