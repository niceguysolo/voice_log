"""
Voice Log App - Complete Backend
Integrated version with PostgreSQL, Whisper, and TTS
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

# Import database models and functions
from database import (
    get_db, create_tables,
    User, VoiceLog,
    create_user, get_user_by_id, get_user_by_email,
    create_voice_log, get_user_logs,
    create_notification_schedule, get_user_notification_schedules,
    log_ai_query
)

# Import audio processing
from audio_processing import (
    transcribe_audio_from_base64,
    text_to_speech,
    get_voice_for_user_preference
)

import anthropic

# Initialize database
create_tables()

# Initialize FastAPI
app = FastAPI(
    title="Voice Log API - Complete",
    description="Voice logging app for elderly users with AI assistance",
    version="3.0.0"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify your domains
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve audio files
audio_dir = os.getenv("AUDIO_STORAGE_PATH", "./audio_files")
os.makedirs(audio_dir, exist_ok=True)
app.mount("/audio", StaticFiles(directory=audio_dir), name="audio")

# Configuration
PORT = int(os.getenv("PORT", 8000))
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "your-secret-key-change-in-production")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

# Initialize AI client
anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# ============================================================================
# MODELS
# ============================================================================

class GoogleSignIn(BaseModel):
    token: str

class VoiceLogCreate(BaseModel):
    audio_base64: str
    timestamp: Optional[datetime] = None

class VoiceLogResponse(BaseModel):
    id: str
    user_id: str
    transcription: str
    timestamp: datetime
    category: Optional[str] = None
    audio_url: Optional[str] = None
    
    class Config:
        from_attributes = True

class QuestionRequest(BaseModel):
    question: str
    voice_response: bool = True
    voice_preference: str = "female_gentle"

class QuestionResponse(BaseModel):
    answer_text: str
    answer_audio_url: Optional[str] = None
    response_time_ms: int

class NotificationScheduleCreate(BaseModel):
    times: List[str]
    message: str = "Time to take your medication"
    notification_type: str = "medication"

class UserPreferences(BaseModel):
    voice_preference: str = "female_gentle"
    notification_sound: bool = True
    
# ============================================================================
# AUTHENTICATION
# ============================================================================

def create_access_token(user_id: str) -> str:
    expire = datetime.utcnow() + timedelta(days=30)
    to_encode = {"sub": user_id, "exp": expire}
    return jwt.encode(to_encode, SECRET_KEY, algorithm="HS256")

def verify_token(authorization: str = Header(None)) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid token")
    
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
# ENDPOINTS
# ============================================================================

@app.post("/auth/google")
async def google_sign_in(signin: GoogleSignIn, db: Session = Depends(get_db)):
    """Sign in with Google"""
    # TODO: Verify Google token properly
    google_id = "google_123456"
    email = "user@example.com"
    name = "Test User"
    
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

@app.post("/logs", response_model=VoiceLogResponse)
async def create_log(
    log: VoiceLogCreate,
    user_id: str = Depends(verify_token),
    db: Session = Depends(get_db)
):
    """Create voice log with Whisper transcription"""
    try:
        user = get_user_by_id(db, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Transcribe audio
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
        
        return voice_log
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating log: {str(e)}")

@app.get("/logs", response_model=List[VoiceLogResponse])
async def get_logs(
    days: int = 60,
    limit: int = 100,
    user_id: str = Depends(verify_token),
    db: Session = Depends(get_db)
):
    """Get user's logs"""
    logs = get_user_logs(db, user_id, days, limit)
    return logs

@app.post("/ask", response_model=QuestionResponse)
async def ask_question(
    question: QuestionRequest,
    user_id: str = Depends(verify_token),
    db: Session = Depends(get_db)
):
    """Answer question with Claude and optionally convert to speech"""
    try:
        start_time = time.time()
        
        # Get logs
        logs = get_user_logs(db, user_id, days=60, limit=500)
        
        if not logs:
            answer_text = "You don't have any logged activities yet."
            return QuestionResponse(
                answer_text=answer_text,
                answer_audio_url=None,
                response_time_ms=0
            )
        
        # Format logs
        log_text = "\n".join([
            f"{log.timestamp.strftime('%Y-%m-%d %H:%M')}: {log.transcription}"
            for log in sorted(logs, key=lambda x: x.timestamp)
        ])
        
        # Query Claude
        message = anthropic_client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=2000,
            system="""You are a helpful assistant for an elderly person. 
            Answer questions about their daily activities based on their log entries.
            Be warm, friendly, and specific. Use dates and details from their logs.
            Keep answers concise but informative.""",
            messages=[{
                "role": "user",
                "content": f"""Activity logs:

{log_text}

Question: {question.question}"""
            }]
        )
        
        answer_text = message.content[0].text
        response_time_ms = int((time.time() - start_time) * 1000)
        
        # Convert to speech if requested
        answer_audio_url = None
        if question.voice_response:
            voice = get_voice_for_user_preference(question.voice_preference)
            tts_result = text_to_speech(answer_text, voice=voice)
            
            if tts_result["success"]:
                answer_audio_url = tts_result["audio_url"]
        
        # Log query
        log_ai_query(
            db, user_id, question.question, answer_text,
            response_time_ms, question.voice_response
        )
        
        return QuestionResponse(
            answer_text=answer_text,
            answer_audio_url=answer_audio_url,
            response_time_ms=response_time_ms
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/notifications/medication")
async def schedule_reminders(
    schedule: NotificationScheduleCreate,
    user_id: str = Depends(verify_token),
    db: Session = Depends(get_db)
):
    """Schedule medication reminders"""
    try:
        user = get_user_by_id(db, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        created_schedules = []
        for time_str in schedule.times:
            notification = create_notification_schedule(
                db, user_id, schedule.notification_type,
                time_str, schedule.message
            )
            created_schedules.append(notification)
        
        return {
            "status": "success",
            "message": f"Scheduled {len(schedule.times)} reminders",
            "schedules": created_schedules
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/")
async def root():
    return {
        "service": "Voice Log API",
        "version": "3.0.0",
        "status": "healthy",
        "features": ["PostgreSQL", "Whisper", "Claude AI", "TTS"]
    }

@app.get("/health")
async def health_check(db: Session = Depends(get_db)):
    try:
        user_count = db.query(User).count()
        log_count = db.query(VoiceLog).count()
        
        return {
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "database": "connected",
            "users": user_count,
            "logs": log_count
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e)
        }

# ============================================================================
# HELPERS
# ============================================================================

def categorize_log(transcription: str) -> str:
    """Categorize log based on keywords"""
    text = transcription.lower()
    
    keywords = {
        'medication': ['medication', 'pill', 'medicine', 'took', 'dose'],
        'exercise': ['walk', 'exercise', 'gym', 'run', 'bike', 'workout'],
        'meal': ['breakfast', 'lunch', 'dinner', 'ate', 'meal', 'food', 'snack'],
        'medical': ['doctor', 'appointment', 'hospital', 'clinic', 'checkup'],
        'social': ['friend', 'family', 'visit', 'called', 'talked', 'met']
    }
    
    for category, words in keywords.items():
        if any(word in text for word in words):
            return category
    
    return 'general'

# ============================================================================
# RUN
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
