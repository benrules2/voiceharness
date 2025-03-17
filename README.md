# VoiceHarness

VoiceHarness is a real-time voice interaction system that enables natural conversations with an AI assistant through speech. It combines speech-to-text, AI processing, and text-to-speech technologies to create an immersive voice experience.

## Features

- Real-time speech recognition using Vosk ASR
- Natural language processing with Cohere's AI model
- Text-to-speech output using pyttsx3
- Support for multiple audio input devices
- Buffered speech output for natural conversation flow
- Configurable voice selection and speech rate

## Prerequisites

- Python 3.12 or higher
- A microphone or audio input device
- Cohere API key (for AI processing)
- Vosk speech recognition model

## Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/VoiceHarness.git
cd VoiceHarness
```

2. Create and activate a virtual environment:
```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Set up your Cohere API key:
```bash
export COHERE_API_KEY='your-api-key-here'
```

## Usage

1. Run the conversation interface:
```bash
python conversation.py
```

2. Select your audio input device when prompted.

3. Start speaking! The system will:
   - Convert your speech to text
   - Process it through the AI model
   - Convert the response back to speech

4. Press Ctrl+C to end the conversation.

## Project Structure

- `conversation.py`: Main application entry point
- `text_to_speech.py`: Handles text-to-speech conversion
- `capture_audio.py`: Manages audio input and speech recognition
- `process_request.py`: Processes text through the AI model

## Configuration

You can customize various aspects of the system:

- Speech rate: Modify the `rate` parameter in `TextToSpeech` initialization
- Voice selection: Use the `--select-voice` flag to choose different voices
- Audio device: Specify a device index using the `--device` argument
