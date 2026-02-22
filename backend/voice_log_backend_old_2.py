"""
Voice Log Backend with Subscription Management
Complete backend with usage limits and payment processing
"""

from fastapi import FastAPI, HTTPException, Depends, Header, Request
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

# Import subscription system
from subscriptions import (
    SubscriptionTier, TIER_LIMITS, PRICING_INFO,
    check_usage_limit, get_user_subscription, has_feature_access,
    create_stripe_customer, create_checkout_session,
    cancel_subscription, create_portal_session,
    handle_stripe_webhook,
    Subscription, Payment
)

import anthropic
import stripe

# Initialize
create_tables()
app = FastAPI(
    title="Voice Log API - With Subscriptions",
    description="Voice logging with subscription management",
    version="4.0.0"
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
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# ============================================================================
# MODELS
# ============================================================================

class VoiceLogCreate(BaseModel):
    audio_base64: str
    timestamp: Optional[datetime] = None

class QuestionRequest(BaseModel):
    question: str
    voice_response: bool = True
    voice_preference: str = "female_gentle"

class SubscriptionUpgrade(BaseModel):
    tier: SubscriptionTier
    billing_period: str = "monthly"  # monthly or yearly

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
        
        # Create free subscription
        subscription = Subscription(
            id=f"sub_{user_id}",
            user_id=user_id,
            tier=SubscriptionTier.FREE,
            status="active"
        )
        db.add(subscription)
        db.commit()
    
    access_token = create_access_token(user.id)
    
    # Get subscription info
    sub_info = get_user_subscription(db, user.id)
    
    return {
        "access_token": access_token,
        "user": {
            "id": user.id,
            "email": user.email,
            "name": user.name
        },
        "subscription": sub_info
    }

# ============================================================================
# ENDPOINTS - VOICE LOGS (with limits)
# ============================================================================

@app.post("/logs")
async def create_log(
    log: VoiceLogCreate,
    user_id: str = Depends(verify_token),
    db: Session = Depends(get_db)
):
    """Create voice log (checks subscription limit)"""
    
    # CHECK USAGE LIMIT
    if not check_usage_limit(db, user_id, "log"):
        sub_info = get_user_subscription(db, user_id)
        limit = sub_info["limits"]["logs_per_month"]
        raise HTTPException(
            status_code=403,
            detail={
                "error": "limit_reached",
                "message": f"You've reached your limit of {limit} logs per month",
                "upgrade_url": "/subscription/upgrade"
            }
        )
    
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
        
        return voice_log
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/logs")
async def get_logs(
    days: int = 60,
    limit: int = 100,
    user_id: str = Depends(verify_token),
    db: Session = Depends(get_db)
):
    """Get logs (respects subscription history limit)"""
    
    # Check history limit
    sub_info = get_user_subscription(db, user_id)
    history_days = sub_info["limits"]["history_days"]
    
    if history_days != -1:  # Not unlimited
        days = min(days, history_days)
    
    logs = get_user_logs(db, user_id, days, limit)
    return logs

# ============================================================================
# ENDPOINTS - AI QUESTIONS (with limits)
# ============================================================================

@app.post("/ask")
async def ask_question(
    question: QuestionRequest,
    user_id: str = Depends(verify_token),
    db: Session = Depends(get_db)
):
    """Answer question (checks subscription limit)"""
    
    # CHECK USAGE LIMIT
    if not check_usage_limit(db, user_id, "question"):
        sub_info = get_user_subscription(db, user_id)
        limit = sub_info["limits"]["questions_per_day"]
        raise HTTPException(
            status_code=403,
            detail={
                "error": "limit_reached",
                "message": f"You've reached your limit of {limit} questions today",
                "upgrade_url": "/subscription/upgrade"
            }
        )
    
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
            system="""You are a helpful assistant for an elderly person.""",
            messages=[{
                "role": "user",
                "content": f"Activity logs:\n{log_text}\n\nQuestion: {question.question}"
            }]
        )
        
        answer_text = message.content[0].text
        response_time_ms = int((time.time() - start_time) * 1000)
        
        # Voice response (check if premium feature)
        answer_audio_url = None
        if question.voice_response:
            if has_feature_access(db, user_id, "unlimited_questions"):
                voice = get_voice_for_user_preference(question.voice_preference)
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
# ENDPOINTS - SUBSCRIPTION MANAGEMENT
# ============================================================================

@app.get("/subscription")
async def get_subscription(
    user_id: str = Depends(verify_token),
    db: Session = Depends(get_db)
):
    """Get user's subscription details"""
    return get_user_subscription(db, user_id)

@app.get("/subscription/pricing")
async def get_pricing():
    """Get pricing information"""
    return PRICING_INFO

@app.post("/subscription/checkout")
async def create_subscription_checkout(
    upgrade: SubscriptionUpgrade,
    user_id: str = Depends(verify_token),
    db: Session = Depends(get_db)
):
    """Create Stripe checkout session"""
    try:
        user = get_user_by_id(db, user_id)
        subscription = db.query(Subscription).filter(
            Subscription.user_id == user_id
        ).first()
        
        # Create Stripe customer if needed
        if not subscription or not subscription.stripe_customer_id:
            stripe_customer_id = create_stripe_customer(
                user_id, user.email, user.name
            )
            
            if subscription:
                subscription.stripe_customer_id = stripe_customer_id
                db.commit()
        else:
            stripe_customer_id = subscription.stripe_customer_id
        
        # Get price ID
        from subscriptions import STRIPE_PRICES
        price_id = STRIPE_PRICES[upgrade.tier][upgrade.billing_period]
        
        # Create checkout session
        session = create_checkout_session(
            user_id=user_id,
            stripe_customer_id=stripe_customer_id,
            price_id=price_id,
            success_url=f"{os.getenv('FRONTEND_URL')}/subscription/success",
            cancel_url=f"{os.getenv('FRONTEND_URL')}/subscription/cancel",
            trial_days=7  # 7-day trial
        )
        
        return session
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/subscription/cancel")
async def cancel_user_subscription(
    immediate: bool = False,
    user_id: str = Depends(verify_token),
    db: Session = Depends(get_db)
):
    """Cancel subscription"""
    try:
        subscription = db.query(Subscription).filter(
            Subscription.user_id == user_id
        ).first()
        
        if not subscription or not subscription.stripe_subscription_id:
            raise HTTPException(status_code=404, detail="No active subscription")
        
        result = cancel_subscription(subscription.stripe_subscription_id, immediate)
        
        subscription.cancel_at_period_end = result["cancel_at_period_end"]
        if immediate:
            subscription.status = "canceled"
        db.commit()
        
        return {
            "status": "success",
            "cancel_at_period_end": result["cancel_at_period_end"]
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/subscription/portal")
async def get_billing_portal(
    user_id: str = Depends(verify_token),
    db: Session = Depends(get_db)
):
    """Get Stripe billing portal URL"""
    try:
        subscription = db.query(Subscription).filter(
            Subscription.user_id == user_id
        ).first()
        
        if not subscription or not subscription.stripe_customer_id:
            raise HTTPException(status_code=404, detail="No subscription found")
        
        portal_url = create_portal_session(
            subscription.stripe_customer_id,
            f"{os.getenv('FRONTEND_URL')}/settings"
        )
        
        return {"url": portal_url}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/webhooks/stripe")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    """Handle Stripe webhooks"""
    try:
        payload = await request.body()
        sig_header = request.headers.get("stripe-signature")
        
        event_data = handle_stripe_webhook(payload, sig_header)
        
        # Update subscription in database based on event
        # This is simplified - you'd handle each event type properly
        
        return {"status": "success"}
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

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
        "version": "4.0.0",
        "features": ["Subscriptions", "Stripe", "Usage Limits"]
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
