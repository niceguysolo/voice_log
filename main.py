# Add these to your main.py

# ============================================================================
# FAMILY MEMBER AUTHENTICATION
# ============================================================================

class FamilyMemberCreate(BaseModel):
    email: EmailStr
    name: str
    relationship_type: str
    passcode: str  # 4-digit passcode

class FamilyMemberLogin(BaseModel):
    email: EmailStr
    passcode: str


@app.post("/family-member")
async def add_family_member(
    family: FamilyMemberCreate,
    user_id: str = Depends(verify_token),
    db: Session = Depends(get_db)
):
    """Add family member with passcode (limited to 1)"""
    
    # Validate passcode (4 digits)
    if not family.passcode or len(family.passcode) != 4 or not family.passcode.isdigit():
        raise HTTPException(
            status_code=400,
            detail="Passcode must be exactly 4 digits"
        )
    
    # Check if family member already exists
    existing = db.query(FamilyMember).filter(
        FamilyMember.user_id == user_id
    ).first()
    
    if existing:
        raise HTTPException(
            status_code=400,
            detail="You already have a family member added. Please remove them first to add a new one."
        )
    
    # Hash the passcode before storing (for security)
    from passlib.context import CryptContext
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    hashed_passcode = pwd_context.hash(family.passcode)
    
    # Create family member
    family_id = f"family_{uuid.uuid4().hex[:8]}"
    family_member = FamilyMember(
        id=family_id,
        user_id=user_id,
        email=family.email,
        name=family.name,
        relationship_type=family.relationship_type,
        passcode=hashed_passcode,  # Store hashed passcode
        alert_enabled=True,
        alert_frequency="realtime"
    )
    
    db.add(family_member)
    db.commit()
    db.refresh(family_member)
    
    # Get the primary user info
    primary_user = get_user_by_id(db, user_id)
    
    return {
        "id": family_member.id,
        "email": family_member.email,
        "name": family_member.name,
        "relationship_type": family_member.relationship_type,
        "alert_enabled": family_member.alert_enabled,
        "message": f"Family member added! Share this passcode with {family.name}: {family.passcode}",
        "primary_user_name": primary_user.name if primary_user else "User"
    }


@app.post("/auth/family-login")
async def family_member_login(
    login: FamilyMemberLogin,
    db: Session = Depends(get_db)
):
    """
    Family member login with email and passcode
    Returns access token and info about who they're monitoring
    """
    from passlib.context import CryptContext
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    
    # Find family member by email
    family_member = db.query(FamilyMember).filter(
        FamilyMember.email == login.email
    ).first()
    
    if not family_member:
        raise HTTPException(
            status_code=401,
            detail="Invalid email or passcode"
        )
    
    # Verify passcode
    if not pwd_context.verify(login.passcode, family_member.passcode):
        raise HTTPException(
            status_code=401,
            detail="Invalid email or passcode"
        )
    
    # Get or create user account for family member
    user = get_user_by_email(db, login.email)
    
    if not user:
        # Create user account for family member
        user_id = f"user_{uuid.uuid4().hex[:8]}"
        user = create_user(db, user_id, login.email, family_member.name, google_id=None)
        
        # Create free tier subscription (family members don't get trial)
        subscription = Subscription(
            id=f"sub_{user_id}",
            user_id=user_id,
            status="active",
            tier="free",
            trial_start=datetime.utcnow(),
            trial_end=datetime.utcnow()
        )
        db.add(subscription)
        db.commit()
    
    # Create access token
    access_token = create_access_token(user.id)
    
    # Get the primary user they're monitoring
    primary_user = get_user_by_id(db, family_member.user_id)
    
    return {
        "access_token": access_token,
        "user": {
            "id": user.id,
            "email": user.email,
            "name": user.name,
            "is_family_member": True
        },
        "monitoring": {
            "user_id": primary_user.id,
            "user_name": primary_user.name,
            "relationship": family_member.relationship_type
        },
        "message": f"Welcome! You're monitoring {primary_user.name}'s activities."
    }


@app.get("/family-member")
async def get_family_member(
    user_id: str = Depends(verify_token),
    db: Session = Depends(get_db)
):
    """Get family member info (without showing passcode)"""
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
            "alert_frequency": family_member.alert_frequency,
            "has_passcode": True  # Don't show actual passcode
        }
    }


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
