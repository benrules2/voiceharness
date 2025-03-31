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
        self.model = "command-r7b-12-2024"
        self.co = cohere.ClientV2(api_key)
        self.chat_history = [{"role": "system", "content": initial_prompt}]
        self.tools = []
        self.actions = {}

    def add_tool(self, tool, action):
        self.tools.append(tool)
        self.actions[tool['function']['name']] = action

    def add_message_to_chat_context(self, message: str, role: str = "user"):
        self.chat_history.append({"role": role, "content": message})

    def process_user_interaction(self, streaming_callback: Callable[[str], None], message: str = None, process_tools: bool = False):
        if message:        
            self.add_message_to_chat_context(message)
        elif not process_tools:
            return 
        
        has_tools = bool(len(self.tools) > 0)

        res = self.co.chat_stream(
            model=self.model,
            messages=self.chat_history,
            tools=self.tools,
            strict_tools=has_tools,
        )

        answer = ""
        tool_plan = ""
        tool_calls = []

        for event in res:
            if event and (event.type == "content-delta"):
                delta = event.delta.message.content.text
                answer += delta
                
                if streaming_callback:
                    streaming_callback(delta)
                    
            if event.type == "content-end":
                self.add_message_to_chat_context(answer, role="assistant")

            if event.type == "tool-call-start":
                if isinstance(event.delta.message.tool_calls, list):
                    tools = event.delta.message.tool_calls 
                elif isinstance(event.delta.message.tool_calls, cohere.ToolCallV2):
                    tools = [event.delta.message.tool_calls]
                else:
                    raise "Tool call is not a list or ToolCallV2 object"

                tool_calls.extend(tools)

            if event.type == "tool-plan-delta":
                tool_plan += event.delta.message.tool_plan

            if event.type == "message-end":
                if event.delta.finish_reason == "TOOL_CALL":
                    if len(tool_plan) == 0:
                        raise ValueError("Tool plan is empty")
                    
                    for tool in tool_calls:
                        if tool.function.arguments == "":
                            tool.function.arguments = "{}"


                    streaming_callback("0:" + tool_plan)
                    self.handle_tool_calls(tool_calls, tool_plan, streaming_callback)



    def handle_tool_calls(self, tool_calls, tool_plan, streaming_callback):
        self.chat_history.append(
            {
                "role": "assistant",
                "tool_plan": tool_plan,
                "tool_calls": tool_calls,
            }
        )

        print(f"Messages: \n {self.chat_history} \n {'--'*20}")
                            
        for tool in tool_calls:
            tool_id = tool.id
            
            args = json.loads(tool.function.arguments) 
            if not args:
                tool_result = self.actions[tool.function.name]()
            else:   
                tool_result = self.actions[tool.function.name](**args)
            tool_content = []

            tool_content.append(
                {
                    "type": "document",
                    "document": {"data": json.dumps(tool_result, default=str)},
                }
            )

            self.chat_history.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_id,
                    "content": tool_content,
                }
            )

        if tool_calls:
            result = self.co.chat(
                model=self.model,
                messages=self.chat_history,
                tools=self.tools,
                strict_tools=True,
            )

            if result.finish_reason == "COMPLETE":
                for content in result.message.content:
                    self.add_message_to_chat_context(
                        content,
                        role="assistant",
                    )
                    streaming_callback("1:" + content.text)

            elif result.finish_reason == "TOOL_CALL":
                self.handle_tool_calls(result.message.tool_calls, result.message.tool_plan, streaming_callback)

    def clear_history(self) -> None:
        """Clear the chat history except for the initial prompt"""
        initial_prompt = self.chat_history[0]
        self.chat_history = [initial_prompt] 

if __name__ == "__main__":

    import skills.home_assistant as home_assistant
    chatbot = ChatBotProcessor("""
    You are a helpful AI assistant who can control smart home devices. 
    Ensure to get all devices before trying to control specific entities.
    You only need to list once, and then you can control the devices.
    Make judgment calls about their location based on the name.
                               
    ALWAYS include entity ids when changing the state. If you do not, you will be punished.
    """)
    home_assistant_client = home_assistant.HomeAssistantClient()
    chatbot.add_tool(home_assistant_client.list_devices_schema(), home_assistant_client.list_devices)
    chatbot.add_tool(home_assistant_client.control_light_schema(), home_assistant_client.set_device_state)
    chatbot.add_tool(home_assistant_client.list_device_types_schema(), home_assistant_client.list_device_types)

    def streaming_callback(text: str):
        print(text)

    # chatbot.process_user_interaction(message="Turn on kitchen light", streaming_callback=streaming_callback)

    print("Chatbot is ready! Type 'exit' to quit.")
    while True:
        user_input = input("You: ")
        if user_input.lower() == "exit":
            break
        chatbot.process_user_interaction(message = user_input, streaming_callback = streaming_callback)

