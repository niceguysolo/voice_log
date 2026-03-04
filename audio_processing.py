"""
audio_processing.py - Audio transcription and text-to-speech
"""

import openai
import os
import base64
import tempfile

# Initialize OpenAI client
openai.api_key = os.getenv("OPENAI_API_KEY")

def transcribe_audio_from_base64(audio_base64: str) -> dict:
    """
    Transcribe audio using OpenAI Whisper
    
    Args:
        audio_base64: Base64 encoded audio file
        
    Returns:
        dict with 'success' (bool) and 'text' (str)
    """
    try:
        # Decode base64 to bytes
        audio_bytes = base64.b64decode(audio_base64)
        
        # Create temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix='.webm') as temp_file:
            temp_file.write(audio_bytes)
            temp_file_path = temp_file.name
        
        # Transcribe using Whisper
        with open(temp_file_path, 'rb') as audio_file:
            transcript = openai.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                response_format="text"
            )
        
        # Clean up temp file
        try:
            os.unlink(temp_file_path)
        except:
            pass
        
        return {
            "success": True,
            "text": transcript if isinstance(transcript, str) else transcript.text
        }
        
    except Exception as e:
        print(f"❌ Transcription error: {e}")
        return {
            "success": False,
            "text": ""
        }


def text_to_speech(text: str, voice: str = "nova") -> dict:
    """
    Convert text to speech using OpenAI TTS
    
    Args:
        text: Text to convert to speech
        voice: Voice to use (nova, alloy, echo, fable, onyx, shimmer)
        
    Returns:
        dict with 'success' (bool) and 'audio_url' (str) or 'audio_base64' (str)
    """
    try:
        # Generate speech
        response = openai.audio.speech.create(
            model="tts-1",
            voice=voice,
            input=text
        )
        
        # Get audio storage path
        audio_dir = os.getenv("AUDIO_STORAGE_PATH", "/tmp/audio_files")
        os.makedirs(audio_dir, exist_ok=True)
        
        # Generate filename
        import hashlib
        text_hash = hashlib.md5(text.encode()).hexdigest()[:12]
        filename = f"tts_{text_hash}.mp3"
        filepath = os.path.join(audio_dir, filename)
        
        # Save audio file
        response.stream_to_file(filepath)
        
        return {
            "success": True,
            "audio_url": f"/audio/{filename}"
        }
        
    except Exception as e:
        print(f"❌ TTS error: {e}")
        return {
            "success": False,
            "audio_url": None
        }


def get_voice_for_user_preference(preference: str) -> str:
    """
    Map user voice preference to OpenAI TTS voice
    
    Args:
        preference: User's voice preference
        
    Returns:
        OpenAI voice name
    """
    voice_map = {
        "female_gentle": "nova",      # Warm, friendly female (default)
        "female_energetic": "shimmer", # Bright, enthusiastic female
        "female_neutral": "alloy",     # Neutral female
        "male_friendly": "echo",       # Friendly male
        "male_storyteller": "fable",   # Storyteller male
        "male_professional": "onyx"    # Professional male
    }
    
    return voice_map.get(preference, "nova")  # Default to nova
