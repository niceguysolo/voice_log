"""
Voice Log Backend - Updated with Text Input Support
Supports both voice and text for recording activities and asking questions
Pleasant feminine voice for TTS responses
"""

from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
import jwt
import os
import uuid
import time

# Import existing modules
from database import (
    get_db, create_tables,
    User, VoiceLog,
    create_user, get_user_by_id, get_user_by_email,
    create_voice_log, get_user_logs,
    create_notification_schedule, get_user_notification_schedules,
    log_ai_query
)
from audio_processing import (
    transcribe_audio_from_base64,
    text_to_speech,
    get_voice_for_user_preference
)

import anthropic

# Initialize
create_tables()
app = FastAPI(
    title="Voice Log API - Updated",
    description="Voice & text logging with pleasant feminine voice responses",
    version="4.5.0"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve audio files
audio_dir = os.getenv("AUDIO_STORAGE_PATH", "./audio_files")
os.makedirs(audio_dir, exist_ok=True)
app.mount("/audio", StaticFiles(directory=audio_dir), name="audio")

# Config
PORT = int(os.getenv("PORT", 8000))
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "your-secret-key")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# Default pleasant feminine voice
DEFAULT_VOICE = "nova"  # OpenAI's pleasant feminine voice

# ============================================================================
# MODELS
# ============================================================================

class VoiceLogCreate(BaseModel):
    audio_base64: str
    timestamp: Optional[datetime] = None

class TextLogCreate(BaseModel):
    text: str
    timestamp: Optional[datetime] = None

class TranscribeRequest(BaseModel):
    audio_base64: str

class QuestionRequest(BaseModel):
    question: str
    voice_response: bool = True
    voice_preference: str = "female_gentle"  # female_gentle, female_energetic

# ============================================================================
# AUTH
# ============================================================================

def create_access_token(user_id: str) -> str:
    expire = datetime.utcnow() + timedelta(days=30)
    to_encode = {"sub": user_id, "exp": expire}
    return jwt.encode(to_encode, SECRET_KEY, algorithm="HS256")

def verify_token(authorization: str = Header(None)) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    
    token = authorization.replace("Bearer ", "")
    
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
        return user_id
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

# ============================================================================
# ENDPOINTS - AUTH
# ============================================================================

@app.post("/auth/google")
async def google_sign_in(signin: dict, db: Session = Depends(get_db)):
    """Sign in with Google"""
    # TODO: Verify token
    google_id = "google_123"
    email = signin.get("email", "user@example.com")
    name = signin.get("name", "Test User")
    
    user = get_user_by_email(db, email)
    
    if not user:
        user_id = f"user_{uuid.uuid4().hex[:8]}"
        user = create_user(db, user_id, email, name, google_id)
    
    access_token = create_access_token(user.id)
    
    return {
        "access_token": access_token,
        "user": {
            "id": user.id,
            "email": user.email,
            "name": user.name
        }
    }

# ============================================================================
# ENDPOINTS - VOICE LOGS
# ============================================================================

@app.post("/logs")
async def create_voice_log(
    log: VoiceLogCreate,
    user_id: str = Depends(verify_token),
    db: Session = Depends(get_db)
):
    """Create voice log (transcribes with Whisper)"""
    try:
        user = get_user_by_id(db, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Transcribe
        transcription_result = transcribe_audio_from_base64(log.audio_base64)
        
        if not transcription_result["success"]:
            raise HTTPException(status_code=400, detail="Transcription failed")
        
        transcription = transcription_result["text"]
        
        # Create log
        log_id = f"log_{uuid.uuid4().hex[:12]}"
        timestamp = log.timestamp or datetime.utcnow()
        category = categorize_log(transcription)
        
        voice_log = create_voice_log(
            db, log_id, user_id, transcription, timestamp, category=category
        )
        
        # Add input_type field
        return {
            **voice_log.__dict__,
            "input_type": "voice"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# ENDPOINTS - TEXT LOGS (NEW!)
# ============================================================================

@app.post("/logs/text")
async def create_text_log(
    log: TextLogCreate,
    user_id: str = Depends(verify_token),
    db: Session = Depends(get_db)
):
    """Create log from text (no transcription needed)"""
    try:
        user = get_user_by_id(db, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        if not log.text or len(log.text.strip()) < 3:
            raise HTTPException(status_code=400, detail="Text too short")
        
        # Create log directly from text
        log_id = f"log_{uuid.uuid4().hex[:12]}"
        timestamp = log.timestamp or datetime.utcnow()
        category = categorize_log(log.text)
        
        voice_log = create_voice_log(
            db, log_id, user_id, log.text, timestamp, category=category
        )
        
        # Add input_type field
        return {
            **voice_log.__dict__,
            "input_type": "text"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# ENDPOINTS - TRANSCRIBE (NEW!)
# ============================================================================

@app.post("/transcribe")
async def transcribe_audio(
    request: TranscribeRequest,
    user_id: str = Depends(verify_token)
):
    """
    Transcribe audio to text (for voice questions)
    Does NOT save as a log, just returns the text
    """
    try:
        transcription_result = transcribe_audio_from_base64(request.audio_base64)
        
        if not transcription_result["success"]:
            raise HTTPException(status_code=400, detail="Transcription failed")
        
        return {
            "text": transcription_result["text"],
            "language": transcription_result.get("language", "en"),
            "duration": transcription_result.get("duration", 0)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# ENDPOINTS - QUESTIONS
# ============================================================================

@app.get("/logs")
async def get_logs(
    days: int = 60,
    limit: int = 100,
    user_id: str = Depends(verify_token),
    db: Session = Depends(get_db)
):
    """Get user's logs"""
    logs = get_user_logs(db, user_id, days, limit)
    
    # Add input_type to each log (default to voice if not set)
    return [
        {
            **log.__dict__,
            "input_type": getattr(log, "input_type", "voice")
        }
        for log in logs
    ]

@app.post("/ask")
async def ask_question(
    question: QuestionRequest,
    user_id: str = Depends(verify_token),
    db: Session = Depends(get_db)
):
    """Answer question with pleasant feminine voice"""
    try:
        start_time = time.time()
        
        logs = get_user_logs(db, user_id, days=60, limit=500)
        
        if not logs:
            answer_text = "You don't have any logged activities yet."
            return {
                "answer_text": answer_text,
                "answer_audio_url": None,
                "response_time_ms": 0
            }
        
        log_text = "\n".join([
            f"{log.timestamp.strftime('%Y-%m-%d %H:%M')}: {log.transcription}"
            for log in sorted(logs, key=lambda x: x.timestamp)
        ])
        
        message = anthropic_client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=2000,
            system="""You are a helpful, warm, and friendly assistant for an elderly person.
            Answer questions about their daily activities based on their log entries.
            Be specific, caring, and conversational. Speak as if you're a kind companion.""",
            messages=[{
                "role": "user",
                "content": f"Activity logs:\n{log_text}\n\nQuestion: {question.question}"
            }]
        )
        
        answer_text = message.content[0].text
        response_time_ms = int((time.time() - start_time) * 1000)
        
        # Voice response with pleasant feminine voice
        answer_audio_url = None
        if question.voice_response:
            # Map preference to specific voice
            voice_map = {
                "female_gentle": "nova",      # Warm, friendly female
                "female_energetic": "shimmer", # Bright, enthusiastic female
                "male_warm": "echo",           # Friendly male (if requested)
            }
            
            voice = voice_map.get(question.voice_preference, DEFAULT_VOICE)
            
            tts_result = text_to_speech(answer_text, voice=voice)
            
            if tts_result["success"]:
                answer_audio_url = tts_result["audio_url"]
        
        log_ai_query(db, user_id, question.question, answer_text, response_time_ms, question.voice_response)
        
        return {
            "answer_text": answer_text,
            "answer_audio_url": answer_audio_url,
            "response_time_ms": response_time_ms,
            "voice_used": voice if question.voice_response else None
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# HELPERS
# ============================================================================

def categorize_log(transcription: str) -> str:
    text = transcription.lower()
    keywords = {
        'medication': ['medication', 'pill', 'medicine'],
        'exercise': ['walk', 'exercise', 'gym'],
        'meal': ['breakfast', 'lunch', 'dinner', 'ate'],
        'medical': ['doctor', 'appointment'],
        'social': ['friend', 'family', 'visit']
    }
    
    for category, words in keywords.items():
        if any(word in text for word in words):
            return category
    return 'general'

@app.get("/")
async def root():
    return {
        "service": "Voice Log API",
        "version": "4.5.0",
        "features": [
            "Voice recording with Whisper",
            "Text input support",
            "Pleasant feminine voice (nova)",
            "Dual-mode questions (voice + text)",
            "Activity categorization"
        ]
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
