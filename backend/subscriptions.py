"""
Subscription & Payment Management
Stripe (backend) + RevenueCat (mobile) integration
"""

import stripe
import os
from datetime import datetime, timedelta
from enum import Enum
from sqlalchemy import Column, String, DateTime, Boolean, Integer, Float
from database import Base

# Stripe configuration
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")

# ============================================================================
# SUBSCRIPTION TIERS
# ============================================================================

class SubscriptionTier(str, Enum):
    FREE = "free"
    CARE = "care"           # $14.99/month
    FAMILY_CARE = "family_care"  # $24.99/month

# Tier limits and features
TIER_LIMITS = {
    SubscriptionTier.FREE: {
        "logs_per_month": 20,
        "questions_per_day": 5,
        "history_days": 7,
        "family_members": 0,
        "voice_quality": "standard",
        "features": ["basic_logging", "basic_questions"]
    },
    SubscriptionTier.CARE: {
        "logs_per_month": -1,  # Unlimited
        "questions_per_day": -1,  # Unlimited
        "history_days": -1,  # Unlimited
        "family_members": 3,
        "voice_quality": "premium",
        "features": [
            "unlimited_logging",
            "unlimited_questions",
            "medication_reminders",
            "weekly_reports",
            "export_pdf",
            "priority_support"
        ]
    },
    SubscriptionTier.FAMILY_CARE: {
        "logs_per_month": -1,
        "questions_per_day": -1,
        "history_days": -1,
        "family_members": 5,
        "voice_quality": "premium",
        "features": [
            "unlimited_logging",
            "unlimited_questions",
            "medication_reminders",
            "family_dashboard",
            "location_sharing",
            "fall_detection",
            "monthly_video_summary",
            "export_pdf",
            "dedicated_support"
        ]
    }
}

# Stripe Price IDs (create these in Stripe Dashboard)
STRIPE_PRICES = {
    SubscriptionTier.CARE: {
        "monthly": "price_care_monthly",  # Replace with real Stripe price ID
        "yearly": "price_care_yearly"
    },
    SubscriptionTier.FAMILY_CARE: {
        "monthly": "price_family_monthly",
        "yearly": "price_family_yearly"
    }
}

# ============================================================================
# DATABASE MODELS
# ============================================================================

class Subscription(Base):
    """User subscription model"""
    __tablename__ = "subscriptions"
    
    id = Column(String, primary_key=True)
    user_id = Column(String, nullable=False, index=True)
    
    # Subscription details
    tier = Column(String, default=SubscriptionTier.FREE)
    status = Column(String, default="active")  # active, canceled, past_due, trialing
    
    # Stripe info
    stripe_customer_id = Column(String)
    stripe_subscription_id = Column(String)
    stripe_price_id = Column(String)
    
    # Billing
    current_period_start = Column(DateTime)
    current_period_end = Column(DateTime)
    cancel_at_period_end = Column(Boolean, default=False)
    
    # Trial
    trial_end = Column(DateTime)
    
    # Usage tracking
    logs_this_month = Column(Integer, default=0)
    questions_today = Column(Integer, default=0)
    last_usage_reset = Column(DateTime, default=datetime.utcnow)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Payment(Base):
    """Payment history"""
    __tablename__ = "payments"
    
    id = Column(String, primary_key=True)
    user_id = Column(String, nullable=False, index=True)
    
    amount = Column(Float, nullable=False)
    currency = Column(String, default="usd")
    status = Column(String, nullable=False)  # succeeded, failed, refunded
    
    stripe_payment_intent_id = Column(String)
    stripe_invoice_id = Column(String)
    
    description = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)


# ============================================================================
# STRIPE OPERATIONS
# ============================================================================

def create_stripe_customer(user_id: str, email: str, name: str) -> str:
    """Create Stripe customer"""
    try:
        customer = stripe.Customer.create(
            email=email,
            name=name,
            metadata={"user_id": user_id}
        )
        return customer.id
    except stripe.error.StripeError as e:
        raise Exception(f"Failed to create customer: {str(e)}")


def create_checkout_session(
    user_id: str,
    stripe_customer_id: str,
    price_id: str,
    success_url: str,
    cancel_url: str,
    trial_days: int = 0
) -> dict:
    """Create Stripe checkout session for subscription"""
    try:
        params = {
            "customer": stripe_customer_id,
            "payment_method_types": ["card"],
            "line_items": [{
                "price": price_id,
                "quantity": 1
            }],
            "mode": "subscription",
            "success_url": success_url,
            "cancel_url": cancel_url,
            "metadata": {"user_id": user_id}
        }
        
        if trial_days > 0:
            params["subscription_data"] = {
                "trial_period_days": trial_days
            }
        
        session = stripe.checkout.Session.create(**params)
        return {
            "session_id": session.id,
            "url": session.url
        }
    except stripe.error.StripeError as e:
        raise Exception(f"Failed to create checkout: {str(e)}")


def cancel_subscription(stripe_subscription_id: str, immediate: bool = False) -> dict:
    """Cancel Stripe subscription"""
    try:
        if immediate:
            # Cancel immediately
            subscription = stripe.Subscription.delete(stripe_subscription_id)
        else:
            # Cancel at period end
            subscription = stripe.Subscription.modify(
                stripe_subscription_id,
                cancel_at_period_end=True
            )
        return {
            "status": subscription.status,
            "cancel_at_period_end": subscription.cancel_at_period_end
        }
    except stripe.error.StripeError as e:
        raise Exception(f"Failed to cancel subscription: {str(e)}")


def create_portal_session(stripe_customer_id: str, return_url: str) -> str:
    """Create Stripe customer portal session"""
    try:
        session = stripe.billing_portal.Session.create(
            customer=stripe_customer_id,
            return_url=return_url
        )
        return session.url
    except stripe.error.StripeError as e:
        raise Exception(f"Failed to create portal: {str(e)}")


# ============================================================================
# USAGE TRACKING & LIMITS
# ============================================================================

def check_usage_limit(db, user_id: str, action: str) -> bool:
    """
    Check if user can perform action based on their subscription tier
    
    Args:
        db: Database session
        user_id: User ID
        action: "log" or "question"
    
    Returns:
        True if allowed, False if limit reached
    """
    subscription = db.query(Subscription).filter(
        Subscription.user_id == user_id
    ).first()
    
    if not subscription:
        # Create free subscription
        subscription = Subscription(
            id=f"sub_{user_id}",
            user_id=user_id,
            tier=SubscriptionTier.FREE
        )
        db.add(subscription)
        db.commit()
    
    # Reset usage if needed
    now = datetime.utcnow()
    if action == "log":
        # Monthly reset
        if subscription.last_usage_reset.month != now.month:
            subscription.logs_this_month = 0
            subscription.last_usage_reset = now
    elif action == "question":
        # Daily reset
        if subscription.last_usage_reset.date() != now.date():
            subscription.questions_today = 0
            subscription.last_usage_reset = now
    
    # Check limits
    limits = TIER_LIMITS[subscription.tier]
    
    if action == "log":
        limit = limits["logs_per_month"]
        if limit == -1:  # Unlimited
            return True
        if subscription.logs_this_month >= limit:
            return False
        subscription.logs_this_month += 1
    
    elif action == "question":
        limit = limits["questions_per_day"]
        if limit == -1:  # Unlimited
            return True
        if subscription.questions_today >= limit:
            return False
        subscription.questions_today += 1
    
    db.commit()
    return True


def get_user_subscription(db, user_id: str) -> dict:
    """Get user's subscription details"""
    subscription = db.query(Subscription).filter(
        Subscription.user_id == user_id
    ).first()
    
    if not subscription:
        return {
            "tier": SubscriptionTier.FREE,
            "status": "active",
            "limits": TIER_LIMITS[SubscriptionTier.FREE]
        }
    
    return {
        "tier": subscription.tier,
        "status": subscription.status,
        "limits": TIER_LIMITS[subscription.tier],
        "current_period_end": subscription.current_period_end,
        "cancel_at_period_end": subscription.cancel_at_period_end,
        "usage": {
            "logs_this_month": subscription.logs_this_month,
            "questions_today": subscription.questions_today
        }
    }


def has_feature_access(db, user_id: str, feature: str) -> bool:
    """Check if user has access to a feature"""
    subscription = db.query(Subscription).filter(
        Subscription.user_id == user_id
    ).first()
    
    if not subscription:
        tier = SubscriptionTier.FREE
    else:
        tier = subscription.tier
    
    return feature in TIER_LIMITS[tier]["features"]


# ============================================================================
# WEBHOOK HANDLER
# ============================================================================

def handle_stripe_webhook(payload: bytes, sig_header: str) -> dict:
    """
    Handle Stripe webhook events
    
    Important events:
    - customer.subscription.created
    - customer.subscription.updated
    - customer.subscription.deleted
    - invoice.payment_succeeded
    - invoice.payment_failed
    """
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, STRIPE_WEBHOOK_SECRET
        )
    except ValueError:
        raise Exception("Invalid payload")
    except stripe.error.SignatureVerificationError:
        raise Exception("Invalid signature")
    
    # Handle the event
    if event.type == "customer.subscription.created":
        subscription = event.data.object
        return {
            "action": "subscription_created",
            "subscription_id": subscription.id,
            "customer_id": subscription.customer,
            "status": subscription.status
        }
    
    elif event.type == "customer.subscription.updated":
        subscription = event.data.object
        return {
            "action": "subscription_updated",
            "subscription_id": subscription.id,
            "status": subscription.status,
            "cancel_at_period_end": subscription.cancel_at_period_end
        }
    
    elif event.type == "customer.subscription.deleted":
        subscription = event.data.object
        return {
            "action": "subscription_canceled",
            "subscription_id": subscription.id
        }
    
    elif event.type == "invoice.payment_succeeded":
        invoice = event.data.object
        return {
            "action": "payment_succeeded",
            "invoice_id": invoice.id,
            "amount": invoice.amount_paid / 100,  # Convert cents to dollars
            "customer_id": invoice.customer
        }
    
    elif event.type == "invoice.payment_failed":
        invoice = event.data.object
        return {
            "action": "payment_failed",
            "invoice_id": invoice.id,
            "customer_id": invoice.customer
        }
    
    return {"action": "unhandled", "type": event.type}


# ============================================================================
# REVENUCAT INTEGRATION (for mobile apps)
# ============================================================================

"""
RevenueCat handles in-app purchases for iOS and Android.
It syncs with Stripe on the backend.

Mobile app setup:
1. Install RevenueCat SDK
2. Configure products in RevenueCat dashboard
3. Link to Stripe
4. Mobile app calls RevenueCat API
5. RevenueCat webhook notifies your backend
6. Backend updates subscription in database

Example mobile integration (React Native):

import Purchases from 'react-native-purchases';

// Initialize
Purchases.configure({apiKey: 'revenuecat_public_key'});

// Get offerings
const offerings = await Purchases.getOfferings();
const carePackage = offerings.current.availablePackages[0];

// Purchase
const {customerInfo} = await Purchases.purchasePackage(carePackage);

// Check entitlements
const isPro = customerInfo.entitlements.active['pro'] !== undefined;
"""

# ============================================================================
# PRICING DISPLAY
# ============================================================================

PRICING_INFO = {
    "tiers": [
        {
            "id": SubscriptionTier.FREE,
            "name": "Free",
            "price": 0,
            "billing": "forever",
            "features": [
                "20 voice logs per month",
                "5 questions per day",
                "7 days of history",
                "Basic voice quality"
            ]
        },
        {
            "id": SubscriptionTier.CARE,
            "name": "Care Plan",
            "price": 14.99,
            "yearly_price": 149.00,
            "billing": "monthly",
            "popular": True,
            "features": [
                "Unlimited voice logs",
                "Unlimited questions",
                "Unlimited history",
                "Premium voice quality",
                "Medication reminders",
                "3 family members",
                "Weekly reports",
                "Export to PDF",
                "Priority support"
            ]
        },
        {
            "id": SubscriptionTier.FAMILY_CARE,
            "name": "Family Care Plan",
            "price": 24.99,
            "yearly_price": 249.00,
            "billing": "monthly",
            "features": [
                "Everything in Care Plan",
                "5 family members",
                "Real-time location sharing",
                "Fall detection alerts",
                "Family dashboard",
                "Monthly video summary",
                "Dedicated support line"
            ]
        }
    ]
}


# ============================================================================
# TESTING
# ============================================================================

if __name__ == "__main__":
    print("Subscription System - Configuration")
    print("=" * 50)
    print("\nTiers and Limits:")
    for tier, limits in TIER_LIMITS.items():
        print(f"\n{tier.upper()}:")
        print(f"  Logs/month: {limits['logs_per_month'] if limits['logs_per_month'] != -1 else 'Unlimited'}")
        print(f"  Questions/day: {limits['questions_per_day'] if limits['questions_per_day'] != -1 else 'Unlimited'}")
        print(f"  Family members: {limits['family_members']}")
        print(f"  Features: {len(limits['features'])}")
