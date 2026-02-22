"""
Database Models and Setup
PostgreSQL integration for Voice Log App
"""

from sqlalchemy import create_engine, Column, String, DateTime, Text, Integer, Boolean, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
import os

# Database URL from environment variable
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://username:password@localhost:5432/voicelog"
)

# Create engine
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# ============================================================================
# DATABASE MODELS
# ============================================================================

class User(Base):
    """User model - stores user information"""
    __tablename__ = "users"
    
    id = Column(String, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=False)
    google_id = Column(String, unique=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    logs = relationship("VoiceLog", back_populates="user", cascade="all, delete-orphan")
    notifications = relationship("NotificationSchedule", back_populates="user", cascade="all, delete-orphan")
    family_members = relationship("FamilyMember", back_populates="user", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<User(id={self.id}, email={self.email}, name={self.name})>"


class VoiceLog(Base):
    """Voice log model - stores user's activity logs"""
    __tablename__ = "voice_logs"
    
    id = Column(String, primary_key=True, index=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    transcription = Column(Text, nullable=False)
    audio_url = Column(String)  # URL to stored audio file (optional)
    timestamp = Column(DateTime, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Categorization (can be auto-filled by AI)
    category = Column(String)  # e.g., "medication", "exercise", "meal", "social"
    sentiment = Column(String)  # e.g., "positive", "neutral", "negative"
    
    # Relationships
    user = relationship("User", back_populates="logs")
    
    def __repr__(self):
        return f"<VoiceLog(id={self.id}, user_id={self.user_id}, timestamp={self.timestamp})>"


class NotificationSchedule(Base):
    """Notification schedule - stores medication reminder times"""
    __tablename__ = "notification_schedules"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    notification_type = Column(String, nullable=False)  # e.g., "medication", "check_in"
    time = Column(String, nullable=False)  # e.g., "08:00"
    message = Column(Text, nullable=False)
    is_active = Column(Boolean, default=True)
    days_of_week = Column(String)  # e.g., "1,2,3,4,5" for weekdays (comma-separated)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="notifications")
    
    def __repr__(self):
        return f"<NotificationSchedule(id={self.id}, user_id={self.user_id}, time={self.time})>"


class FamilyMember(Base):
    """Family member model - stores family connections for sharing"""
    __tablename__ = "family_members"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    family_email = Column(String, nullable=False)
    family_name = Column(String, nullable=False)
    relationship = Column(String)  # e.g., "daughter", "son", "spouse"
    can_view_logs = Column(Boolean, default=True)
    can_receive_alerts = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="family_members")
    
    def __repr__(self):
        return f"<FamilyMember(id={self.id}, family_email={self.family_email})>"


class AIQuery(Base):
    """AI query log - stores questions asked and answers given"""
    __tablename__ = "ai_queries"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    
    # For analytics
    response_time_ms = Column(Integer)  # How long AI took to respond
    voice_output = Column(Boolean, default=False)  # Was answer converted to speech
    
    def __repr__(self):
        return f"<AIQuery(id={self.id}, user_id={self.user_id}, timestamp={self.timestamp})>"


# ============================================================================
# DATABASE FUNCTIONS
# ============================================================================

def get_db():
    """
    Dependency function to get database session
    Use in FastAPI endpoints like: db: Session = Depends(get_db)
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_tables():
    """Create all tables in the database"""
    Base.metadata.create_all(bind=engine)
    print("✓ Database tables created successfully")


def drop_tables():
    """Drop all tables (use carefully!)"""
    Base.metadata.drop_all(bind=engine)
    print("✓ Database tables dropped")


def reset_database():
    """Drop and recreate all tables (DANGEROUS - deletes all data!)"""
    drop_tables()
    create_tables()
    print("✓ Database reset complete")


# ============================================================================
# CRUD OPERATIONS (Create, Read, Update, Delete)
# ============================================================================

def create_user(db, user_id: str, email: str, name: str, google_id: str = None):
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


def get_user_by_id(db, user_id: str):
    """Get user by ID"""
    return db.query(User).filter(User.id == user_id).first()


def get_user_by_email(db, email: str):
    """Get user by email"""
    return db.query(User).filter(User.email == email).first()


def create_voice_log(db, log_id: str, user_id: str, transcription: str, 
                     timestamp: datetime, audio_url: str = None, 
                     category: str = None):
    """Create a new voice log"""
    log = VoiceLog(
        id=log_id,
        user_id=user_id,
        transcription=transcription,
        timestamp=timestamp,
        audio_url=audio_url,
        category=category
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return log


def get_user_logs(db, user_id: str, days: int = 60, limit: int = 1000):
    """Get user's logs from the last N days"""
    from datetime import timedelta
    cutoff_date = datetime.utcnow() - timedelta(days=days)
    
    return db.query(VoiceLog).filter(
        VoiceLog.user_id == user_id,
        VoiceLog.timestamp >= cutoff_date
    ).order_by(VoiceLog.timestamp.desc()).limit(limit).all()


def create_notification_schedule(db, user_id: str, notification_type: str,
                                 time: str, message: str, days_of_week: str = None):
    """Create a notification schedule"""
    schedule = NotificationSchedule(
        user_id=user_id,
        notification_type=notification_type,
        time=time,
        message=message,
        days_of_week=days_of_week
    )
    db.add(schedule)
    db.commit()
    db.refresh(schedule)
    return schedule


def get_user_notification_schedules(db, user_id: str):
    """Get all active notification schedules for a user"""
    return db.query(NotificationSchedule).filter(
        NotificationSchedule.user_id == user_id,
        NotificationSchedule.is_active == True
    ).all()


def add_family_member(db, user_id: str, family_email: str, family_name: str,
                     relationship: str = None):
    """Add a family member"""
    family = FamilyMember(
        user_id=user_id,
        family_email=family_email,
        family_name=family_name,
        relationship=relationship
    )
    db.add(family)
    db.commit()
    db.refresh(family)
    return family


def get_family_members(db, user_id: str):
    """Get all family members for a user"""
    return db.query(FamilyMember).filter(
        FamilyMember.user_id == user_id
    ).all()


def log_ai_query(db, user_id: str, question: str, answer: str,
                response_time_ms: int = None, voice_output: bool = False):
    """Log an AI query for analytics"""
    query = AIQuery(
        user_id=user_id,
        question=question,
        answer=answer,
        response_time_ms=response_time_ms,
        voice_output=voice_output
    )
    db.add(query)
    db.commit()
    db.refresh(query)
    return query


def get_user_query_history(db, user_id: str, limit: int = 50):
    """Get user's recent AI queries"""
    return db.query(AIQuery).filter(
        AIQuery.user_id == user_id
    ).order_by(AIQuery.timestamp.desc()).limit(limit).all()


# ============================================================================
# INITIALIZATION
# ============================================================================

if __name__ == "__main__":
    print("Setting up database...")
    create_tables()
    print("\nDatabase ready!")
    
    # Print connection info
    print(f"\nDatabase URL: {DATABASE_URL}")
    print("\nTo connect using psql:")
    print("  psql postgresql://username:password@localhost:5432/voicelog")
