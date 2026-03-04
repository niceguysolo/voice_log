import openai
import os
import base64

openai.api_key = os.getenv("OPENAI_API_KEY")

def transcribe_audio_from_base64(audio_base64: str) -> dict:
    """Transcribe audio using OpenAI Whisper"""
    try:
        # Decode base64
        audio_bytes = base64.b64decode(audio_base64)
        
        # Save temporarily
        temp_file = "/tmp/audio.webm"
        with open(temp_file, "wb") as f:
            f.write(audio_bytes)
        
        # Transcribe
        with open(temp_file, "rb") as audio_file:
            transcript = openai.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file
            )
        
        return {"success": True, "text": transcript.text}
    except Exception as e:
        print(f"Transcription error: {e}")
        return {"success": False, "text": ""}

def text_to_speech(text: str, voice: str = "nova") -> dict:
    """Convert text to speech using OpenAI TTS"""
    try:
        response = openai.audio.speech.create(
            model="tts-1",
            voice=voice,
            input=text
        )
        
        # Save audio file
        audio_file = f"/tmp/answer_{hash(text)}.mp3"
        response.stream_to_file(audio_file)
        
        return {
            "success": True,
            "audio_url": f"/audio/{os.path.basename(audio_file)}"
        }
    except Exception as e:
        print(f"TTS error: {e}")
        return {"success": False, "audio_url": None}
