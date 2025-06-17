import argparse
import threading
import queue
import time
import os
from elevenlabs import ElevenLabs, play


class ElevenLabsTTS:
    """Modern ElevenLabs TTS implementation using the official client and play function."""
    
    def __init__(self, voice_id=None, api_key=None, model_id="eleven_multilingual_v2"):
        self.text_queue = queue.Queue()
        self.speaking = False
        self.voice_id = voice_id or "d7uOsH3lh7mAnKEC7eqD"  # Default voice
        self.model_id = model_id
        
        # Initialize ElevenLabs client
        api_key = api_key or os.getenv("ELEVENLABS_API_KEY")
        if not api_key:
            raise ValueError("ElevenLabs API key is required. Set ELEVENLABS_API_KEY environment variable.")
        
        self.client = ElevenLabs(api_key=api_key)
        
        # Thread management
        self.worker_ready = threading.Event()
        self.shutdown_event = threading.Event()
        
        # Start worker thread
        self.worker_thread = threading.Thread(target=self._worker, daemon=True)
        self.worker_thread.start()
        self.worker_ready.wait()
        print("[ElevenLabs TTS] Ready")

    def _generate_and_play_audio(self, text):
        """Generate and play audio using ElevenLabs client."""
        try:
            audio = self.client.text_to_speech.convert(
                text=text,
                voice_id=self.voice_id,
                model_id=self.model_id,
                output_format="mp3_44100_128"
            )
            play(audio)
            return True
            
        except Exception as e:
            print(f"TTS error: {e}")
            return False

    def _worker(self):
        """Worker thread for processing TTS queue."""
        self.worker_ready.set()
        
        while not self.shutdown_event.is_set():
            try:
                text = self.text_queue.get(timeout=0.1)
                if text is None:  # Shutdown signal
                    break
                    
                self.speaking = True
                print(f"[Speaking] {text}")
                
                self._generate_and_play_audio(text)
                
                self.speaking = False
                self.text_queue.task_done()
                
            except queue.Empty:
                continue
            except Exception as e:
                print(f"Worker error: {e}")
                self.speaking = False

    def speak(self, text):
        """Add text to speaking queue."""
        if text and text.strip():
            self.text_queue.put(text.strip())

    def speak_and_wait(self, text):
        """Speak text and wait for completion."""
        self.speak(text)
        self.wait_for_completion()

    def wait_for_completion(self):
        """Wait for all queued speech to complete."""
        self.text_queue.join()
        while self.speaking:
            time.sleep(0.1)

    def completed_speaking(self):
        """Check if currently speaking."""
        speaking =  self.speaking or self.text_queue.qsize() > 0
        return not speaking
    
    def queue_size(self):
        """Get current queue size."""
        return self.text_queue.qsize()

    def clear_queue(self):
        """Clear the speech queue."""
        while not self.text_queue.empty():
            try:
                self.text_queue.get_nowait()
                self.text_queue.task_done()
            except queue.Empty:
                break

    def set_voice(self, voice_id):
        """Change the voice ID."""
        self.voice_id = voice_id
        print(f"Voice changed to: {voice_id}")

    def set_model(self, model_id):
        """Change the model ID."""
        self.model_id = model_id
        print(f"Model changed to: {model_id}")

    def get_voices(self):
        """Get available voices."""
        try:
            voices = self.client.voices.get_all()
            return voices.voices
        except Exception as e:
            print(f"Error getting voices: {e}")
            return []

    def list_voices(self):
        """Print available voices."""
        try:
            voices = self.get_voices()
            if voices:
                print("\nAvailable ElevenLabs voices:")
                print("-" * 60)
                for voice in voices:
                    print(f"Name: {voice.name}")
                    print(f"ID: {voice.voice_id}")
                    print(f"Category: {voice.category}")
                    if hasattr(voice, 'description') and voice.description:
                        print(f"Description: {voice.description}")
                    print("-" * 30)
            else:
                print("No voices available or error occurred.")
        except Exception as e:
            print(f"Error listing voices: {e}")

    def shutdown(self):
        """Shutdown the TTS system."""
        self.shutdown_event.set()
        self.text_queue.put(None)  # Signal worker to stop
        if self.worker_thread.is_alive():
            self.worker_thread.join(timeout=5)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.shutdown()


def main():
    """Command line interface for ElevenLabs TTS."""
    parser = argparse.ArgumentParser(description="ElevenLabs Text-to-Speech")
    parser.add_argument("--text", type=str, default="Hello, how are you?", 
                       help="Text to speak")
    parser.add_argument("--list-voices", action="store_true", 
                       help="List available voices")
    parser.add_argument("--voice-id", type=str, 
                       help="ElevenLabs voice ID")
    parser.add_argument("--model-id", type=str, default="eleven_multilingual_v2",
                       help="Model ID to use")
    parser.add_argument("--api-key", type=str, 
                       help="ElevenLabs API key")
    parser.add_argument("--repeat", type=int, default=1,
                       help="Number of times to repeat the text")
    parser.add_argument("--interactive", action="store_true",
                       help="Interactive mode")
    
    args = parser.parse_args()
    
    try:
        with ElevenLabsTTS(
            voice_id=args.voice_id,
            api_key=args.api_key,
            model_id=args.model_id
        ) as tts:
            
            if args.list_voices:
                tts.list_voices()
                return
            
            if args.interactive:
                print("Interactive mode. Type 'quit' to exit.")
                while True:
                    text = input("\nEnter text to speak: ").strip()
                    if text.lower() in ['quit', 'exit', 'q']:
                        break
                    if text:
                        tts.speak_and_wait(text)
            else:
                print(f"Speaking: {args.text}")
                for i in range(args.repeat):
                    text = args.text
                    if args.repeat > 1:
                        text += f" (iteration {i + 1})"
                    tts.speak(text)
                
                print("Waiting for speech to complete...")
                tts.wait_for_completion()
                print("Completed!")
    
    except KeyboardInterrupt:
        print("\nInterrupted by user")
    except Exception as e:
        print(f"Error: {e}")
        print("\nMake sure you have:")
        print("1. ElevenLabs API key set as ELEVENLABS_API_KEY environment variable")
        print("2. Required package installed: pip install elevenlabs")


if __name__ == "__main__":
    main()