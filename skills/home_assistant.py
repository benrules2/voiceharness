import os
from collections import defaultdict
from homeassistant_api import Client, State

class Device:
    def __init__(self, entity_id, attributes, state):
        self.entity_id = entity_id
        self.attributes = attributes
        self.state = state
        if not "friendly_name" in attributes:
            self.attributes["friendly_name"] = entity_id.split(".")[1].replace("_", " ").title()

    def to_dict(self):
        return {
            "entity_id": self.entity_id,
            "attributes": self.attributes,
            "state": self.state,
        }

    def __repr__(self):
        return f"Device(entity_id={self.entity_id}, attributes={self.attributes}, state={self.state})"

class HomeAssistantClient:
    def __init__(self):
        self.client = Client(
            os.getenv("HOME_ASSISTANT_API", "http://homeassistant.local:8123/api/"),
            os.getenv("HOME_ASSISTANT_TOKEN")
        )
        self.device_map = defaultdict(list)
        self.init_known_devices()

    def init_known_devices(self):
        try:
            devices = self.client.get_states()
            for device in devices:
                device_type = device.entity_id.split(".")[0]
                self.device_map[device_type].append(Device(
                    entity_id=device.entity_id,
                    attributes=device.attributes,
                    state=device.state
                ))
        except Exception as e:
            print(f"Error retrieving devices: {e}")

    def get_device(self, entity_id):
        for devices in self.device_map.values():
            for device in devices:
                if device.entity_id == entity_id:
                    return device
        return None  

    def list_device_types(self, max_results=50):
        return list(self.device_map.keys())[:max_results]
    
    def list_devices(self, device_type="light"):
        return [
            {
                'entity_id' : entity.entity_id,
                'friendly_name' : entity.attributes['friendly_name'],
                'attributes' : entity.attributes,
            } for entity in self.device_map.get(device_type, [])]


    def set_device_state(self, entity_id, new_state):
        if new_state not in ["on", "off"]:
            raise ValueError("Invalid state. Must be 'on' or 'off'.")

        self.client.trigger_service("light", f"turn_{new_state}", entity_id=entity_id)
        return f"Successfully set entity_id {entity_id} to {new_state}"

    def list_device_types_schema(self):
        return {
            "type": "function",
            "function": {
                "name": "list_device_types",
                "description": "gets the types of devices known by smarthome hub",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "max_results": {
                            "type": "integer",
                            "description": "Number of device types to return. Default is 50",
                        },
                    },
                "required": ["max_results"],
                }
            },
        }


    def list_devices_schema(self):
        return {
            "type": "function",
            "function": {
                "name": "list_devices",
                "description": "gets the name and state of smarthome. Default type is 'light', but the list_device_types tool gives all valid entries values.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "device_type": {
                            "type": "string",
                            "description": "Type of device group to check.",
                            "enum": ["light", "switch", "sensor", "weather", "media_player", "input_boolean", "group"],
                        },
                    },
                "required": ["device_type"],
                }
            },
        }

    def control_light_schema(self):
        return {
            "type": "function",
            "function": {
                "name": "control_light_state",
                "description": "Changes the state of a smarthome light",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "entity_id": {
                            "type": "string",
                            "description": "The entity ID of the light to control",
                        },
                        "new_state": {
                            "type": "string",
                            "enum": ["on", "off"],
                            "description": "The desired state of the light",
                        }
                    },
                    "required": ["entity_id", "new_state"],
                },
            },
        }


if __name__ == "__main__":
    ha_tool = HomeAssistantClient()
    for light in ha_tool.list_devices("light"):
        print(f"Light: {light.attributes.get('friendly_name', light.entity_id)}, state: {light.state} \n")
