import re
from enum import StrEnum
from constants import JEFF_REF_AUDIO, JEFF_REF_WAV


class TTSType(StrEnum):
    LOCAL = "local"
    ELEVEN_LABS = "eleven_labs"
    F5_TTS = "f5_tts"

class TTSEngine:
    """
    A unified TTS engine that wraps multiple backends.

    Usage:
        engine = TTSEngine(tts_type=TTSType.LOCAL)
        engine.speak("Hello world")
        while not engine.completed_speaking():
            pass
        engine.cleanup()
    """
    def __init__(
        self,
        tts_type: TTSType = TTSType.LOCAL,
        f5_ref_audio_path: str = None,
        f5_ref_audio_text: str = None,
        f5_quantization_bits: int = 4
    ):
        self._type = tts_type
        if tts_type == TTSType.LOCAL:
            from tts.local_tts import TextToSpeech
            self._engine = TextToSpeech()
        elif tts_type == TTSType.ELEVEN_LABS:
            from tts.eleven_labs import ElevenLabsTTS
            self._engine = ElevenLabsTTS()
        elif tts_type == TTSType.F5_TTS:
            from tts.f5_tts import F5TTSGenerator
            self._engine = F5TTSGenerator(
                quantization_bits=f5_quantization_bits,
                ref_audio_path=f5_ref_audio_path or JEFF_REF_WAV,
                ref_audio_text=f5_ref_audio_text or JEFF_REF_AUDIO
            )
        else:
            raise ValueError(f"Unknown TTSType: {tts_type}")

    def speak(self, text: str, output=None):
        """
        Clean and speak the given text.
        """
        # Remove unsupported characters
        cleaned = re.sub(r"[^a-zA-Z0-9\s\.,!?\'’\"]", ' ', text)
        self._engine.speak(text = cleaned, output = output)

    def completed_speaking(self) -> bool:
        """
        Return True if the current utterance has finished playing.
        """
        return self._engine.completed_speaking()
    
    def speaking(self) -> bool:
        """
        Return True if the TTS engine is currently speaking.
        """
        return not self._engine.completed_speaking()

    def cleanup(self):
        """
        Clean up any resources used by the TTS engine.
        """
        if hasattr(self._engine, 'cleanup'):
            self._engine.cleanup()

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--text", type=str, default="Hello, how are you?")
    parser.add_argument("--tts-type", type=TTSType, choices=list(TTSType), default=TTSType.ELEVEN_LABS)
    args = parser.parse_args()

    print("Initializing TTS Engine...")
    tts_engine = TTSEngine(tts_type=args.tts_type)

    print(f"Speaking: {args.text}")
    tts_engine.speak(args.text)

    while not tts_engine.completed_speaking():
        pass

    print("Done speaking.")
    tts_engine.cleanup()