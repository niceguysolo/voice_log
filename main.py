"""
Voice Log Backend - Updated with Family Alerts & Free Trial
Features:
- 7-day free trial for all new users
- Each user can add 1 family member
- Family member receives email alerts for new logs
- No encryption (MVP version)
"""

from fastapi import FastAPI, HTTPException, Depends, Header, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr
from typing import Optional, List
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import Column, String, DateTime, Boolean, Integer, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from jose import jwt
import os
import uuid
import time
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import sys
# Workaround for Python 3.13 + SQLAlchemy compatibility
if sys.version_info >= (3, 13):
    import warnings
    warnings.filterwarnings("ignore", category=DeprecationWarning)
    
# Import existing modules
from database import (
    Base, engine, get_db,
    User, VoiceLog, FamilyMember, Subscription, PushSubscription, AIQuery,
    create_user, get_user_by_id, get_user_by_email,
    create_voice_log, get_user_logs, log_ai_query
)

from audio_processing import (
    transcribe_audio_from_base64,
    text_to_speech,
    get_voice_for_user_preference
)

import anthropic

# Initialize FastAPI
app = FastAPI(
    title="Voice Log API - Final Version",
    description="With family alerts and 7-day free trial",
    version="5.0.0"
)

# Check if static directory exists
if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")
    
    @app.get("/")
    async def root():
        """Serve the web frontend"""
        return FileResponse('static/index.html')
    
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

# Email config
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
FROM_EMAIL = os.getenv("FROM_EMAIL", "noreply@voicelog.app")

anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)



# Create tables
Base.metadata.create_all(bind=engine)

# ============================================================================
# MODELS (Pydantic)
# ============================================================================

class VoiceLogCreate(BaseModel):
    audio_base64: str
    timestamp: Optional[datetime] = None

class TextLogCreate(BaseModel):
    text: str
    timestamp: Optional[datetime] = None

class QuestionRequest(BaseModel):
    question: str
    voice_response: bool = True
    voice_preference: str = "female_gentle"

class FamilyMemberCreate(BaseModel):
    email: EmailStr
    name: str
    relationship_type: str

class FamilyMemberUpdate(BaseModel):
    name: Optional[str] = None
    relationship_type: Optional[str] = None
    alert_enabled: Optional[bool] = None
    alert_frequency: Optional[str] = None

# ============================================================================
# AUTHENTICATION
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
# SUBSCRIPTION HELPERS
# ============================================================================

def check_trial_status(subscription: Subscription) -> dict:
    """Check if user's trial is active"""
    if subscription.status == "trial":
        now = datetime.utcnow()
        if now > subscription.trial_end:
            # Trial expired
            subscription.status = "expired"
            subscription.tier = "free"
            return {
                "is_trial": False,
                "trial_expired": True,
                "days_left": 0
            }
        else:
            # Trial active
            days_left = (subscription.trial_end - now).days
            return {
                "is_trial": True,
                "trial_expired": False,
                "days_left": days_left
            }
    
    return {
        "is_trial": False,
        "trial_expired": False,
        "days_left": 0
    }

def check_usage_limits(user_id: str, action: str, db: Session) -> bool:
    """
    Check if user can perform action based on trial/subscription status
    
    Trial (7 days): Unlimited
    Free tier: 20 logs/month, 5 questions/day
    Paid tier: Unlimited
    """
    subscription = db.query(Subscription).filter(
        Subscription.user_id == user_id
    ).first()
    
    if not subscription:
        return False
    
    # Check trial
    trial_status = check_trial_status(subscription)
    
    # During trial: Unlimited
    if trial_status["is_trial"]:
        return True
    
    # Paid subscription: Unlimited
    if subscription.status == "active" and subscription.tier in ["care", "family_care"]:
        return True
    
    # Free tier: Check limits
    now = datetime.utcnow()
    
    # Reset counters if needed
    if subscription.last_reset.month != now.month:
        subscription.logs_this_month = 0
        subscription.last_reset = now
    
    if subscription.last_reset.date() != now.date():
        subscription.questions_today = 0
        subscription.last_reset = now
    
    # Check limits
    if action == "log":
        if subscription.logs_this_month >= 20:
            return False
        subscription.logs_this_month += 1
    elif action == "question":
        if subscription.questions_today >= 5:
            return False
        subscription.questions_today += 1
    
    db.commit()
    return True

# ============================================================================
# EMAIL NOTIFICATIONS
# ============================================================================

def send_email(to_email: str, subject: str, html_content: str):
    """Send email notification"""
    if not SMTP_USER or not SMTP_PASSWORD:
        print(f"Email not configured, would send: {subject} to {to_email}")
        return
    
    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = FROM_EMAIL
        msg['To'] = to_email
        
        html_part = MIMEText(html_content, 'html')
        msg.attach(html_part)
        
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)
            
        print(f"Email sent to {to_email}")
    except Exception as e:
        print(f"Failed to send email: {str(e)}")

def send_activity_alert(
    family_email: str,
    family_name: str,
    user_name: str,
    activity: str,
    timestamp: datetime
):
    """Send activity alert to family member"""
    subject = f"Activity Update: {user_name}"
    
    html_content = f"""
    <html>
    <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
        <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 20px; text-align: center;">
            <h1 style="color: white; margin: 0;">🎤 Voice Log</h1>
        </div>
        
        <div style="padding: 30px; background: #f9f9f9;">
            <h2 style="color: #333;">Hi {family_name}!</h2>
            
            <p style="font-size: 16px; color: #666;">
                <strong>{user_name}</strong> logged a new activity:
            </p>
            
            <div style="background: white; padding: 20px; border-radius: 10px; border-left: 4px solid #667eea; margin: 20px 0;">
                <p style="font-size: 16px; color: #333; margin: 0;">
                    "{activity}"
                </p>
                <p style="font-size: 14px; color: #999; margin-top: 10px;">
                    {timestamp.strftime('%B %d, %Y at %I:%M %p')}
                </p>
            </div>
            
            <p style="font-size: 14px; color: #666;">
                You're receiving this because you're listed as a family contact for {user_name}.
            </p>
            
            <div style="text-align: center; margin-top: 30px;">
                <a href="https://voicelog.app/dashboard" 
                   style="background: #667eea; color: white; padding: 12px 30px; 
                          text-decoration: none; border-radius: 8px; display: inline-block;">
                    View Dashboard
                </a>
            </div>
        </div>
        
        <div style="padding: 20px; text-align: center; font-size: 12px; color: #999;">
            <p>Voice Log - Your Daily Memory Assistant</p>
            <p>
                <a href="https://voicelog.app/settings" style="color: #667eea;">Manage Alert Settings</a>
            </p>
        </div>
    </body>
    </html>
    """
    
    send_email(family_email, subject, html_content)

def send_trial_reminder(user_email: str, user_name: str, days_left: int):
    """Send trial ending reminder"""
    subject = f"Your Voice Log trial ends in {days_left} days"
    
    html_content = f"""
    <html>
    <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
        <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 20px; text-align: center;">
            <h1 style="color: white; margin: 0;">🎤 Voice Log</h1>
        </div>
        
        <div style="padding: 30px;">
            <h2 style="color: #333;">Hi {user_name}!</h2>
            
            <p style="font-size: 16px; color: #666;">
                Your 7-day free trial ends in <strong>{days_left} days</strong>.
            </p>
            
            <p style="font-size: 16px; color: #666;">
                We hope Voice Log has been helpful! After your trial ends, you'll have these options:
            </p>
            
            <div style="background: #f9f9f9; padding: 20px; border-radius: 10px; margin: 20px 0;">
                <h3 style="color: #667eea;">Free Plan</h3>
                <ul style="color: #666;">
                    <li>20 logs per month</li>
                    <li>5 questions per day</li>
                    <li>7 days of history</li>
                </ul>
                
                <h3 style="color: #667eea;">Care Plan - $14.99/month</h3>
                <ul style="color: #666;">
                    <li>Unlimited logs & questions</li>
                    <li>Unlimited history</li>
                    <li>Family member alerts</li>
                    <li>Medication reminders</li>
                    <li>Priority support</li>
                </ul>
            </div>
            
            <div style="text-align: center; margin-top: 30px;">
                <a href="https://voicelog.app/subscribe" 
                   style="background: #667eea; color: white; padding: 15px 40px; 
                          text-decoration: none; border-radius: 8px; display: inline-block; font-size: 16px;">
                    Upgrade to Care Plan
                </a>
            </div>
        </div>
    </body>
    </html>
    """
    
    send_email(user_email, subject, html_content)

# ============================================================================
# ENDPOINTS - AUTH
# ============================================================================


@app.post("/auth/google")
async def google_sign_in(signin: dict, db: Session = Depends(get_db)):
    """Sign in with Google - creates 7-day trial for new users"""
    # TODO: Verify Google token
    google_id = "google_123"
    email = signin.get("email", "user@example.com")
    name = signin.get("name", "Test User")
    
    user = get_user_by_email(db, email)
    
    if not user:
        # New user - create account with 7-day trial
        user_id = f"user_{uuid.uuid4().hex[:8]}"
        user = create_user(db, user_id, email, name, google_id)
        
        # Create subscription with trial
        trial_end = datetime.utcnow() + timedelta(days=7)
        subscription = Subscription(
            id=f"sub_{user_id}",
            user_id=user_id,
            status="trial",
            tier="trial",
            trial_start=datetime.utcnow(),
            trial_end=trial_end
        )
        db.add(subscription)
        db.commit()
        
        # Send welcome email
        send_email(
            email,
            "Welcome to Voice Log - Your 7-Day Trial Starts Now!",
            f"""
            <h1>Welcome {name}!</h1>
            <p>Your 7-day free trial has started. Enjoy unlimited access to all features!</p>
            <p>Trial ends: {trial_end.strftime('%B %d, %Y')}</p>
            """
        )
    
    access_token = create_access_token(user.id)
    
    # Get subscription info
    subscription = db.query(Subscription).filter(
        Subscription.user_id == user.id
    ).first()
    
    trial_status = check_trial_status(subscription) if subscription else None
    
    return {
        "access_token": access_token,
        "user": {
            "id": user.id,
            "email": user.email,
            "name": user.name
        },
        "subscription": {
            "status": subscription.status if subscription else "none",
            "tier": subscription.tier if subscription else "none",
            "trial_days_left": trial_status["days_left"] if trial_status else 0,
            "is_trial": trial_status["is_trial"] if trial_status else False
        }
    }

# ============================================================================
# ENDPOINTS - LOGS
# ============================================================================

@app.post("/logs")
async def create_voice_log_endpoint(
    log: VoiceLogCreate,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(verify_token),
    db: Session = Depends(get_db)
):
    """Create voice log with family alert"""
    
    # Check usage limits
    if not check_usage_limits(user_id, "log", db):
        subscription = db.query(Subscription).filter(
            Subscription.user_id == user_id
        ).first()
        
        return {
            "error": "limit_reached",
            "message": "You've reached your free tier limit. Upgrade to continue.",
            "limit": 20,
            "used": subscription.logs_this_month
        }, 403
    
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
        
        voice_log = VoiceLog(
            id=log_id,
            user_id=user_id,
            transcription=transcription,
            timestamp=timestamp,
            category=category,
            input_type="voice"
        )
        
        db.add(voice_log)
        db.commit()
        db.refresh(voice_log)
        
        # Send alert to family member (in background)
        family_member = db.query(FamilyMember).filter(
            FamilyMember.user_id == user_id,
            FamilyMember.alert_enabled == True
        ).first()
        
        if family_member and family_member.alert_frequency == "realtime":
            background_tasks.add_task(
                send_activity_alert,
                family_member.email,
                family_member.name,
                user.name,
                transcription,
                timestamp
            )
        
        return {
            "id": voice_log.id,
            "transcription": voice_log.transcription,
            "timestamp": voice_log.timestamp,
            "category": voice_log.category,
            "input_type": voice_log.input_type,
            "family_notified": family_member is not None
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/logs/text")
async def create_text_log_endpoint(
    log: TextLogCreate,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(verify_token),
    db: Session = Depends(get_db)
):
    """Create text log with family alert"""
    
    # Check usage limits
    if not check_usage_limits(user_id, "log", db):
        return {
            "error": "limit_reached",
            "message": "You've reached your free tier limit. Upgrade to continue."
        }, 403
    
    try:
        user = get_user_by_id(db, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        if not log.text or len(log.text.strip()) < 3:
            raise HTTPException(status_code=400, detail="Text too short")
        
        # Create log
        log_id = f"log_{uuid.uuid4().hex[:12]}"
        timestamp = log.timestamp or datetime.utcnow()
        category = categorize_log(log.text)
        
        voice_log = VoiceLog(
            id=log_id,
            user_id=user_id,
            transcription=log.text,
            timestamp=timestamp,
            category=category,
            input_type="text"
        )
        
        db.add(voice_log)
        db.commit()
        db.refresh(voice_log)
        
        # Send alert to family member
        family_member = db.query(FamilyMember).filter(
            FamilyMember.user_id == user_id,
            FamilyMember.alert_enabled == True
        ).first()
        
        if family_member and family_member.alert_frequency == "realtime":
            background_tasks.add_task(
                send_activity_alert,
                family_member.email,
                family_member.name,
                user.name,
                log.text,
                timestamp
            )
        
        return {
            "id": voice_log.id,
            "transcription": voice_log.transcription,
            "timestamp": voice_log.timestamp,
            "category": voice_log.category,
            "input_type": voice_log.input_type,
            "family_notified": family_member is not None
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/logs")
async def get_logs_endpoint(
    days: int = 60,
    limit: int = 100,
    user_id: str = Depends(verify_token),
    db: Session = Depends(get_db)
):
    """Get user's logs"""
    subscription = db.query(Subscription).filter(
        Subscription.user_id == user_id
    ).first()
    
    # Free tier: only 7 days of history
    if subscription and subscription.tier == "free" and subscription.status != "trial":
        days = min(days, 7)
    
    logs = get_user_logs(db, user_id, days, limit)
    return logs

# ============================================================================
# ENDPOINTS - QUESTIONS
# ============================================================================

@app.post("/transcribe")
async def transcribe_audio_endpoint(
    audio: dict,
    user_id: str = Depends(verify_token),
    db: Session = Depends(get_db)
):
    """
    Transcribe audio to text (for voice questions)
    Does not save as a log, just returns transcription
    """
    try:
        # Transcribe
        transcription_result = transcribe_audio_from_base64(audio.get("audio_base64"))
        
        if not transcription_result["success"]:
            raise HTTPException(status_code=400, detail="Transcription failed")
        
        return {
            "text": transcription_result["text"],
            "success": True
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/ask")
async def ask_question_endpoint(
    question: QuestionRequest,
    user_id: str = Depends(verify_token),
    db: Session = Depends(get_db)
):
    """Answer question"""
    
    # Check usage limits
    if not check_usage_limits(user_id, "question", db):
        return {
            "error": "limit_reached",
            "message": "You've reached your daily question limit. Upgrade for unlimited questions."
        }, 403
    
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
            system="""You are a helpful, warm, and friendly assistant.""",
            messages=[{
                "role": "user",
                "content": f"Activity logs:\n{log_text}\n\nQuestion: {question.question}"
            }]
        )
        
        answer_text = message.content[0].text
        response_time_ms = int((time.time() - start_time) * 1000)
        
        # Voice response
        answer_audio_url = None
        if question.voice_response:
            voice_map = {
                "female_gentle": "nova",
                "female_energetic": "shimmer",
            }
            
            voice = voice_map.get(question.voice_preference, "nova")
            tts_result = text_to_speech(answer_text, voice=voice)
            
            if tts_result["success"]:
                answer_audio_url = tts_result["audio_url"]
        
        log_ai_query(db, user_id, question.question, answer_text, response_time_ms, question.voice_response)
        
        return {
            "answer_text": answer_text,
            "answer_audio_url": answer_audio_url,
            "response_time_ms": response_time_ms
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# ENDPOINTS - FAMILY MEMBER
# ============================================================================

@app.post("/family-member")
async def add_family_member(
    family: FamilyMemberCreate,
    user_id: str = Depends(verify_token),
    db: Session = Depends(get_db)
):
    """Add family member (limited to 1)"""
    
    # Check if family member already exists
    existing = db.query(FamilyMember).filter(
        FamilyMember.user_id == user_id
    ).first()
    
    if existing:
        raise HTTPException(
            status_code=400,
            detail="You already have a family member added. Please remove them first to add a new one."
        )
    
    # Create family member
    family_id = f"family_{uuid.uuid4().hex[:8]}"
    family_member = FamilyMember(
        id=family_id,
        user_id=user_id,
        email=family.email,
        name=family.name,
        relationship_type=family.relationship_type,
        alert_enabled=True,
        alert_frequency="realtime"
    )
    
    db.add(family_member)
    db.commit()
    db.refresh(family_member)
    
    # Send welcome email to family member
    user = get_user_by_id(db, user_id)
    send_email(
        family.email,
        f"{user.name} added you as a family contact on Voice Log",
        f"""
        <h1>Hi {family.name}!</h1>
        <p>{user.name} has added you as a family contact on Voice Log.</p>
        <p>You'll receive email alerts when they log activities.</p>
        <p><a href="https://voicelog.app/family/{family_id}">View their activity dashboard</a></p>
        """
    )
    
    return {
        "id": family_member.id,
        "email": family_member.email,
        "name": family_member.name,
        "relationship_type": family_member.relationship_type,
        "alert_enabled": family_member.alert_enabled
    }

@app.get("/family-member")
async def get_family_member(
    user_id: str = Depends(verify_token),
    db: Session = Depends(get_db)
):
    """Get family member info"""
    family_member = db.query(FamilyMember).filter(
        FamilyMember.user_id == user_id
    ).first()
    
    if not family_member:
        return {"family_member": None}
    
    return {
        "family_member": {
            "id": family_member.id,
            "email": family_member.email,
            "name": family_member.name,
            "relationship_type": family_member.relationship_type,
            "alert_enabled": family_member.alert_enabled,
            "alert_frequency": family_member.alert_frequency
        }
    }

@app.put("/family-member")
async def update_family_member(
    updates: FamilyMemberUpdate,
    user_id: str = Depends(verify_token),
    db: Session = Depends(get_db)
):
    """Update family member settings"""
    family_member = db.query(FamilyMember).filter(
        FamilyMember.user_id == user_id
    ).first()
    
    if not family_member:
        raise HTTPException(status_code=404, detail="No family member found")
    
    if updates.name:
        family_member.name = updates.name
    if updates.relationship_type:
        family_member.relationship_type = updates.relationship_type
    if updates.alert_enabled is not None:
        family_member.alert_enabled = updates.alert_enabled
    if updates.alert_frequency:
        family_member.alert_frequency = updates.alert_frequency
    
    db.commit()
    db.refresh(family_member)
    
    return {"status": "updated"}

@app.delete("/family-member")
async def remove_family_member(
    user_id: str = Depends(verify_token),
    db: Session = Depends(get_db)
):
    """Remove family member"""
    family_member = db.query(FamilyMember).filter(
        FamilyMember.user_id == user_id
    ).first()
    
    if not family_member:
        raise HTTPException(status_code=404, detail="No family member found")
    
    db.delete(family_member)
    db.commit()
    
    return {"status": "deleted"}

# ============================================================================
# ENDPOINTS - SUBSCRIPTION
# ============================================================================

@app.get("/subscription")
async def get_subscription_info(
    user_id: str = Depends(verify_token),
    db: Session = Depends(get_db)
):
    """Get subscription status"""
    subscription = db.query(Subscription).filter(
        Subscription.user_id == user_id
    ).first()
    
    if not subscription:
        return {"status": "none"}
    
    trial_status = check_trial_status(subscription)
    
    return {
        "status": subscription.status,
        "tier": subscription.tier,
        "trial": trial_status,
        "usage": {
            "logs_this_month": subscription.logs_this_month,
            "questions_today": subscription.questions_today
        }
    }

# ============================================================================
# HELPERS
# ============================================================================

def categorize_log(transcription: str) -> str:
    text = transcription.lower()
    keywords = {
        'medication': ['medication', 'pill', 'medicine', 'took', 'dose'],
        'exercise': ['walk', 'exercise', 'gym', 'jog', 'run'],
        'meal': ['breakfast', 'lunch', 'dinner', 'ate', 'food', 'meal'],
        'medical': ['doctor', 'appointment', 'hospital', 'checkup'],
        'social': ['friend', 'family', 'visit', 'called', 'talked']
    }
    
    for category, words in keywords.items():
        if any(word in text for word in words):
            return category
    return 'general'

@app.get("/")
async def root():
    return {
        "service": "Voice Log API",
        "version": "5.0.0",
        "features": [
            "7-day free trial",
            "Family member alerts (1 per user)",
            "Voice + text logging",
            "AI questions with pleasant voice",
            "Usage limits (free tier)"
        ]
    }

