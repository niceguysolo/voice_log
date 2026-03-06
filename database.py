"""
database.py - Complete Database Models and Helper Functions
"""

from sqlalchemy import create_engine, Column, String, DateTime, Boolean, Integer, ForeignKey, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session, relationship
from datetime import datetime
import os

# Get DATABASE_URL from environment
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable is not set!")

# Fix postgres:// to postgresql:// for SQLAlchemy 2.0+
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# Create engine
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# ============================================================================
# DATABASE MODELS
# ============================================================================

class User(Base):
    """User accounts"""
    __tablename__ = "users"
    
    id = Column(String, primary_key=True)
    email = Column(String, unique=True, nullable=False)
    name = Column(String, nullable=False)
    google_id = Column(String, unique=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    logs = relationship("VoiceLog", back_populates="user", cascade="all, delete-orphan")
    family_member = relationship("FamilyMember", back_populates="user", uselist=False, cascade="all, delete-orphan")
    subscription = relationship("Subscription", back_populates="user", uselist=False, cascade="all, delete-orphan")
    push_subscriptions = relationship("PushSubscription", back_populates="user", cascade="all, delete-orphan")
    ai_queries = relationship("AIQuery", back_populates="user", cascade="all, delete-orphan")


class VoiceLog(Base):
    """Voice/text activity logs"""
    __tablename__ = "voice_logs"
    
    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    transcription = Column(Text, nullable=False)
    timestamp = Column(DateTime, nullable=False)
    category = Column(String, default="general")  # medication, exercise, meal, medical, social
    input_type = Column(String, default="voice")  # voice or text
    audio_url = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationship
    user = relationship("User", back_populates="logs")


class FamilyMember(Base):
    """Family member for alerts (1 per user)"""
    __tablename__ = "family_members"
    
    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    email = Column(String, nullable=False)
    name = Column(String, nullable=False)
    relationship_type = Column(String)  # daughter, son, spouse, etc.
    passcode = Column(String, nullable=False)  # 4-digit passcode for login
    alert_enabled = Column(Boolean, default=True)
    alert_frequency = Column(String, default="realtime")  # realtime, daily, weekly
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationship
    user = relationship("User", back_populates="family_member")


class Subscription(Base):
    """User subscription and trial tracking"""
    __tablename__ = "subscriptions"
    
    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("users.id"), unique=True, nullable=False)
    status = Column(String, default="trial")  # trial, active, canceled, expired
    tier = Column(String, default="trial")  # free, care, family_care
    
    # Trial tracking
    trial_start = Column(DateTime, default=datetime.utcnow)
    trial_end = Column(DateTime)
    
    # Subscription tracking
    stripe_customer_id = Column(String)
    stripe_subscription_id = Column(String)
    current_period_end = Column(DateTime)
    
    # Usage limits (for free tier after trial)
    logs_this_month = Column(Integer, default=0)
    questions_today = Column(Integer, default=0)
    last_reset = Column(DateTime, default=datetime.utcnow)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationship
    user = relationship("User", back_populates="subscription")


class PushSubscription(Base):
    """Push notification subscriptions"""
    __tablename__ = "push_subscriptions"
    
    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    subscription_json = Column(Text)  # JSON string of subscription data
    device_type = Column(String)  # 'web', 'ios', 'android'
    fcm_token = Column(String)  # For mobile (Firebase Cloud Messaging)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationship
    user = relationship("User", back_populates="push_subscriptions")


class AIQuery(Base):
    """AI query history (for analytics)"""
    __tablename__ = "ai_queries"
    
    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)
    response_time_ms = Column(Integer)
    voice_output = Column(Boolean, default=False)
    
    # Relationship
    user = relationship("User", back_populates="ai_queries")


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_db():
    """Get database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ============================================================================
# USER CRUD OPERATIONS
# ============================================================================

def create_user(db: Session, user_id: str, email: str, name: str, google_id: str = None) -> User:
    """Create a new user"""
    user = User(
        id=user_id,
        email=email,
        name=name,
        google_id=google_id
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def get_user_by_id(db: Session, user_id: str) -> User:
    """Get user by ID"""
    return db.query(User).filter(User.id == user_id).first()


def get_user_by_email(db: Session, email: str) -> User:
    """Get user by email"""
    return db.query(User).filter(User.email == email).first()


def get_user_by_google_id(db: Session, google_id: str) -> User:
    """Get user by Google ID"""
    return db.query(User).filter(User.google_id == google_id).first()


# ============================================================================
# VOICE LOG CRUD OPERATIONS
# ============================================================================

def create_voice_log(
    db: Session,
    log_id: str,
    user_id: str,
    transcription: str,
    timestamp: datetime,
    category: str = "general",
    input_type: str = "voice",
    audio_url: str = None
) -> VoiceLog:
    """Create a new voice log"""
    log = VoiceLog(
        id=log_id,
        user_id=user_id,
        transcription=transcription,
        timestamp=timestamp,
        category=category,
        input_type=input_type,
        audio_url=audio_url
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return log


def get_user_logs(db: Session, user_id: str, days: int = 60, limit: int = 100):
    """Get user's recent logs"""
    from datetime import timedelta
    cutoff_date = datetime.utcnow() - timedelta(days=days)
    
    return db.query(VoiceLog).filter(
        VoiceLog.user_id == user_id,
        VoiceLog.timestamp >= cutoff_date
    ).order_by(
        VoiceLog.timestamp.desc()
    ).limit(limit).all()


def get_log_by_id(db: Session, log_id: str) -> VoiceLog:
    """Get a specific log by ID"""
    return db.query(VoiceLog).filter(VoiceLog.id == log_id).first()


# ============================================================================
# AI QUERY CRUD OPERATIONS
# ============================================================================

def log_ai_query(
    db: Session,
    user_id: str,
    question: str,
    answer: str,
    response_time_ms: int,
    voice_output: bool = False
):
    """Log an AI query for analytics"""
    import uuid
    
    query = AIQuery(
        id=f"query_{uuid.uuid4().hex[:12]}",
        user_id=user_id,
        question=question,
        answer=answer,
        response_time_ms=response_time_ms,
        voice_output=voice_output
    )
    db.add(query)
    db.commit()
    return query


# ============================================================================
# INITIALIZATION
# ============================================================================

def init_db():
    """Initialize database - create all tables"""
    Base.metadata.create_all(bind=engine)
    print("✅ Database tables created successfully")


def drop_all_tables():
    """Drop all tables (use with caution!)"""
    Base.metadata.drop_all(bind=engine)
    print("⚠️ All database tables dropped")


# Auto-create tables on import (for development)
if __name__ != "__main__":
    try:
        Base.metadata.create_all(bind=engine)
        print("✅ Database initialized")
    except Exception as e:
        print(f"⚠️ Database initialization warning: {e}")
        