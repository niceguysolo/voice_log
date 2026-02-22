"""
Audio Processing Module
Speech-to-Text (Whisper) and Text-to-Speech implementation
"""

import openai
import os
import base64
import uuid
from pathlib import Path
from typing import Optional
import boto3  # For S3 storage (optional)

# Initialize OpenAI client
openai_client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Configure storage
AUDIO_STORAGE_PATH = os.getenv("AUDIO_STORAGE_PATH", "./audio_files")
USE_S3 = os.getenv("USE_S3_STORAGE", "false").lower() == "true"
S3_BUCKET = os.getenv("S3_BUCKET_NAME", "voicelog-audio")

# Create local storage directory if needed
Path(AUDIO_STORAGE_PATH).mkdir(parents=True, exist_ok=True)

# ============================================================================
# SPEECH-TO-TEXT (Whisper)
# ============================================================================

def transcribe_audio_from_base64(audio_base64: str, language: str = "en") -> dict:
    """
    Transcribe audio from base64 encoded data using Whisper
    
    Args:
        audio_base64: Base64 encoded audio data
        language: Language code (default: "en" for English)
    
    Returns:
        dict with transcription and metadata
    """
    try:
        # Decode base64 audio
        audio_bytes = base64.b64decode(audio_base64)
        
        # Save temporarily
        temp_filename = f"temp_audio_{uuid.uuid4().hex}.mp3"
        temp_path = os.path.join(AUDIO_STORAGE_PATH, temp_filename)
        
        with open(temp_path, "wb") as f:
            f.write(audio_bytes)
        
        # Transcribe with Whisper
        with open(temp_path, "rb") as audio_file:
            transcription = openai_client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                language=language,
                response_format="verbose_json"  # Get detailed info
            )
        
        # Clean up temp file
        os.remove(temp_path)
        
        return {
            "text": transcription.text,
            "language": transcription.language,
            "duration": transcription.duration,
            "success": True
        }
        
    except Exception as e:
        return {
            "text": "",
            "error": str(e),
            "success": False
        }


def transcribe_audio_from_file(file_path: str, language: str = "en") -> dict:
    """
    Transcribe audio from a file path using Whisper
    
    Args:
        file_path: Path to audio file
        language: Language code
    
    Returns:
        dict with transcription and metadata
    """
    try:
        with open(file_path, "rb") as audio_file:
            transcription = openai_client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                language=language,
                response_format="verbose_json"
            )
        
        return {
            "text": transcription.text,
            "language": transcription.language,
            "duration": transcription.duration,
            "success": True
        }
        
    except Exception as e:
        return {
            "text": "",
            "error": str(e),
            "success": False
        }


# ============================================================================
# TEXT-TO-SPEECH
# ============================================================================

def text_to_speech(
    text: str,
    voice: str = "nova",  # female voice
    speed: float = 1.0,
    save_locally: bool = True
) -> dict:
    """
    Convert text to speech using OpenAI TTS
    
    Args:
        text: Text to convert
        voice: Voice to use (options: alloy, echo, fable, onyx, nova, shimmer)
               - Female: nova, shimmer, alloy
               - Male: echo, fable, onyx
        speed: Speed of speech (0.25 to 4.0, default 1.0)
        save_locally: Whether to save file locally
    
    Returns:
        dict with audio URL/path and metadata
    """
    try:
        # Generate speech
        response = openai_client.audio.speech.create(
            model="tts-1",  # or "tts-1-hd" for higher quality
            voice=voice,
            input=text,
            speed=speed
        )
        
        # Generate unique filename
        filename = f"tts_{uuid.uuid4().hex}.mp3"
        
        if save_locally:
            # Save to local storage
            file_path = os.path.join(AUDIO_STORAGE_PATH, filename)
            response.stream_to_file(file_path)
            audio_url = f"/audio/{filename}"  # Relative URL
            
        elif USE_S3:
            # Upload to S3
            file_path = f"/tmp/{filename}"
            response.stream_to_file(file_path)
            audio_url = upload_to_s3(file_path, filename)
            os.remove(file_path)  # Clean up
            
        else:
            # Just save locally as fallback
            file_path = os.path.join(AUDIO_STORAGE_PATH, filename)
            response.stream_to_file(file_path)
            audio_url = f"/audio/{filename}"
        
        return {
            "audio_url": audio_url,
            "voice": voice,
            "speed": speed,
            "success": True
        }
        
    except Exception as e:
        return {
            "audio_url": None,
            "error": str(e),
            "success": False
        }


def text_to_speech_streaming(text: str, voice: str = "nova") -> bytes:
    """
    Convert text to speech and return raw audio bytes for streaming
    
    Args:
        text: Text to convert
        voice: Voice to use
    
    Returns:
        Audio bytes
    """
    response = openai_client.audio.speech.create(
        model="tts-1",
        voice=voice,
        input=text
    )
    
    return response.content


# ============================================================================
# STORAGE FUNCTIONS
# ============================================================================

def upload_to_s3(file_path: str, filename: str) -> str:
    """
    Upload audio file to S3
    
    Args:
        file_path: Local path to file
        filename: Name to use in S3
    
    Returns:
        Public URL to file
    """
    try:
        s3_client = boto3.client(
            's3',
            aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
            region_name=os.getenv("AWS_REGION", "us-east-1")
        )
        
        # Upload file
        s3_client.upload_file(
            file_path,
            S3_BUCKET,
            filename,
            ExtraArgs={'ContentType': 'audio/mpeg', 'ACL': 'public-read'}
        )
        
        # Return public URL
        url = f"https://{S3_BUCKET}.s3.amazonaws.com/{filename}"
        return url
        
    except Exception as e:
        print(f"S3 upload error: {e}")
        return None


def save_audio_from_base64(audio_base64: str, filename: str = None) -> str:
    """
    Save base64 audio to file
    
    Args:
        audio_base64: Base64 encoded audio
        filename: Optional custom filename
    
    Returns:
        Path to saved file
    """
    if not filename:
        filename = f"audio_{uuid.uuid4().hex}.mp3"
    
    audio_bytes = base64.b64decode(audio_base64)
    file_path = os.path.join(AUDIO_STORAGE_PATH, filename)
    
    with open(file_path, "wb") as f:
        f.write(audio_bytes)
    
    return file_path


# ============================================================================
# VOICE OPTIONS
# ============================================================================

VOICE_OPTIONS = {
    "female": {
        "gentle": "nova",      # Friendly, warm female voice
        "energetic": "shimmer", # Bright, enthusiastic female voice
        "neutral": "alloy"      # Balanced, clear female voice
    },
    "male": {
        "warm": "echo",        # Friendly male voice
        "storyteller": "fable", # Expressive male voice
        "professional": "onyx"  # Clear, authoritative male voice
    }
}


def get_voice_for_user_preference(preference: str = "female_gentle") -> str:
    """
    Get voice based on user preference
    
    Args:
        preference: String like "female_gentle", "male_warm", etc.
    
    Returns:
        Voice name for OpenAI TTS
    """
    parts = preference.lower().split("_")
    
    if len(parts) == 2:
        gender, style = parts
        return VOICE_OPTIONS.get(gender, {}).get(style, "nova")
    
    return "nova"  # Default


# ============================================================================
# TESTING / EXAMPLES
# ============================================================================

if __name__ == "__main__":
    print("Audio Processing Module - Test")
    print("=" * 50)
    
    # Test Text-to-Speech
    print("\n1. Testing Text-to-Speech...")
    test_text = "Hello! I'm your voice assistant. I can help you remember your daily activities."
    
    result = text_to_speech(test_text, voice="nova")
    
    if result["success"]:
        print(f"✓ TTS Success! Audio saved to: {result['audio_url']}")
    else:
        print(f"✗ TTS Failed: {result['error']}")
    
    # Test different voices
    print("\n2. Testing different voices...")
    voices_to_test = ["nova", "echo", "shimmer"]
    
    for voice in voices_to_test:
        result = text_to_speech(f"This is the {voice} voice.", voice=voice)
        if result["success"]:
            print(f"✓ {voice}: {result['audio_url']}")
    
    print("\n" + "=" * 50)
    print("Tests complete!")
    print(f"Audio files saved to: {AUDIO_STORAGE_PATH}")
