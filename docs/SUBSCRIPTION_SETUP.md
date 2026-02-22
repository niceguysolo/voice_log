# Subscription & Payment Setup Guide

Complete guide to implementing the freemium subscription model with Stripe.

## Overview

Your app has 3 tiers:
- **Free**: 20 logs/month, 5 questions/day, 7 days history
- **Care Plan ($14.99/mo)**: Unlimited everything + premium features
- **Family Care ($24.99/mo)**: Everything + family sharing

---

## Part 1: Stripe Setup (Backend Payments)

### 1. Create Stripe Account

1. Go to https://stripe.com/
2. Sign up for account
3. Activate your account (provide business info)

### 2. Get API Keys

1. Go to https://dashboard.stripe.com/apikeys
2. Copy these keys:
   - **Publishable key** (starts with `pk_test_...`)
   - **Secret key** (starts with `sk_test_...`)

### 3. Create Products & Prices

In Stripe Dashboard:

**Care Plan Monthly:**
1. Products → Create product
2. Name: "Care Plan"
3. Description: "Unlimited logging and AI questions"
4. Pricing: $14.99 USD, Recurring monthly
5. Copy the **Price ID** (starts with `price_...`)

**Care Plan Yearly:**
1. Add another price to same product
2. Pricing: $149.00 USD, Recurring yearly
3. Copy the **Price ID**

**Family Care Monthly:**
1. Create new product: "Family Care Plan"
2. Pricing: $24.99 USD, Recurring monthly
3. Copy **Price ID**

**Family Care Yearly:**
1. Add price: $249.00 USD, Recurring yearly
2. Copy **Price ID**

### 4. Configure Webhooks

1. Stripe Dashboard → Developers → Webhooks
2. Add endpoint: `https://your-api.railway.app/webhooks/stripe`
3. Select events:
   - `customer.subscription.created`
   - `customer.subscription.updated`
   - `customer.subscription.deleted`
   - `invoice.payment_succeeded`
   - `invoice.payment_failed`
4. Copy **Webhook signing secret** (starts with `whsec_...`)

### 5. Update Backend Code

In `subscriptions.py`, update STRIPE_PRICES:

```python
STRIPE_PRICES = {
    SubscriptionTier.CARE: {
        "monthly": "price_YOUR_CARE_MONTHLY_ID",
        "yearly": "price_YOUR_CARE_YEARLY_ID"
    },
    SubscriptionTier.FAMILY_CARE: {
        "monthly": "price_YOUR_FAMILY_MONTHLY_ID",
        "yearly": "price_YOUR_FAMILY_YEARLY_ID"
    }
}
```

### 6. Set Environment Variables

```bash
export STRIPE_SECRET_KEY='sk_test_...'
export STRIPE_WEBHOOK_SECRET='whsec_...'
```

---

## Part 2: Mobile App Integration

### Option A: Stripe Checkout (Web-based) - EASIEST

Add to your React Native `App.js`:

```javascript
import { Linking } from 'react-native';

async function upgradeToPremium() {
  // Call your backend to create checkout session
  const response = await fetch(`${API_URL}/subscription/checkout`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${accessToken}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      tier: 'care',
      billing_period: 'monthly'
    })
  });
  
  const data = await response.json();
  
  // Open Stripe checkout in browser
  await Linking.openURL(data.url);
}
```

### Option B: RevenueCat (Native In-App Purchases) - BETTER UX

**1. Create RevenueCat Account:**
- Go to https://www.revenuecat.com/
- Sign up (free up to $10k/month revenue)

**2. Connect to Stripe:**
- RevenueCat Dashboard → Integrations → Stripe
- Enter your Stripe API key
- RevenueCat will sync subscriptions

**3. Configure Products:**
- Projects → Your app → Products
- Create products matching your Stripe products

**4. Install in Mobile App:**

```bash
npm install react-native-purchases
```

**5. Use in App:**

```javascript
import Purchases from 'react-native-purchases';

// Initialize (do this on app start)
await Purchases.configure({
  apiKey: 'your_revenuecat_public_key'
});

// Get available offerings
const offerings = await Purchases.getOfferings();
const carePlan = offerings.current.availablePackages[0];

// Purchase
try {
  const {customerInfo} = await Purchases.purchasePackage(carePlan);
  
  // Check if they have premium access
  if (customerInfo.entitlements.active['premium']) {
    Alert.alert('Success!', 'You now have premium access');
  }
} catch (e) {
  if (!e.userCancelled) {
    Alert.alert('Error', 'Purchase failed');
  }
}

// Check subscription status
const customerInfo = await Purchases.getCustomerInfo();
const isPremium = customerInfo.entitlements.active['premium'] !== undefined;
```

---

## Part 3: Usage Limit Enforcement

The backend automatically enforces limits. Your mobile app just needs to handle the errors:

```javascript
// When creating a log
async function createLog(audioBase64) {
  try {
    const response = await fetch(`${API_URL}/logs`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${accessToken}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ audio_base64: audioBase64 })
    });
    
    if (response.status === 403) {
      // Hit usage limit
      const error = await response.json();
      
      Alert.alert(
        'Upgrade Needed',
        error.detail.message,
        [
          { text: 'Maybe Later', style: 'cancel' },
          { 
            text: 'Upgrade Now', 
            onPress: () => showUpgradeScreen() 
          }
        ]
      );
      return;
    }
    
    const data = await response.json();
    Alert.alert('Success', `Logged: ${data.transcription}`);
    
  } catch (error) {
    Alert.alert('Error', 'Failed to create log');
  }
}
```

---

## Part 4: Display Subscription Status

Add subscription info to your app:

```javascript
// Get subscription info
async function loadSubscription() {
  const response = await fetch(`${API_URL}/subscription`, {
    headers: {
      'Authorization': `Bearer ${accessToken}`
    }
  });
  
  const subscription = await response.json();
  
  return {
    tier: subscription.tier,
    logsRemaining: subscription.limits.logs_per_month === -1 
      ? 'Unlimited' 
      : subscription.limits.logs_per_month - subscription.usage.logs_this_month,
    questionsRemaining: subscription.limits.questions_per_day === -1
      ? 'Unlimited'
      : subscription.limits.questions_per_day - subscription.usage.questions_today
  };
}

// Display in UI
function SubscriptionBanner({subscription}) {
  if (subscription.tier === 'free') {
    return (
      <View style={styles.banner}>
        <Text style={styles.bannerText}>
          Free Plan: {subscription.logsRemaining} logs remaining this month
        </Text>
        <TouchableOpacity onPress={showUpgradeScreen}>
          <Text style={styles.upgradeButton}>Upgrade</Text>
        </TouchableOpacity>
      </View>
    );
  }
  
  return (
    <View style={styles.premiumBanner}>
      <Text>✨ {subscription.tier === 'care' ? 'Care' : 'Family Care'} Plan</Text>
    </View>
  );
}
```

---

## Part 5: Pricing Screen

Create an upgrade screen in your app:

```javascript
function PricingScreen() {
  return (
    <ScrollView>
      <Text style={styles.title}>Choose Your Plan</Text>
      
      {/* Free Tier */}
      <View style={styles.tierCard}>
        <Text style={styles.tierName}>Free</Text>
        <Text style={styles.tierPrice}>$0</Text>
        <Text>20 logs per month</Text>
        <Text>5 questions per day</Text>
        <Text>7 days of history</Text>
      </View>
      
      {/* Care Plan - MOST POPULAR */}
      <View style={[styles.tierCard, styles.popular]}>
        <Text style={styles.popularBadge}>MOST POPULAR</Text>
        <Text style={styles.tierName}>Care Plan</Text>
        <Text style={styles.tierPrice}>$14.99/month</Text>
        <Text>✓ Unlimited logs</Text>
        <Text>✓ Unlimited questions</Text>
        <Text>✓ Unlimited history</Text>
        <Text>✓ Premium voice</Text>
        <Text>✓ Medication reminders</Text>
        <TouchableOpacity 
          style={styles.subscribeButton}
          onPress={() => subscribe('care', 'monthly')}
        >
          <Text style={styles.buttonText}>Start 7-Day Free Trial</Text>
        </TouchableOpacity>
      </View>
      
      {/* Family Care */}
      <View style={styles.tierCard}>
        <Text style={styles.tierName}>Family Care</Text>
        <Text style={styles.tierPrice}>$24.99/month</Text>
        <Text>✓ Everything in Care Plan</Text>
        <Text>✓ 5 family members</Text>
        <Text>✓ Family dashboard</Text>
        <Text>✓ Location sharing</Text>
        <TouchableOpacity 
          style={styles.subscribeButton}
          onPress={() => subscribe('family_care', 'monthly')}
        >
          <Text style={styles.buttonText}>Start 7-Day Free Trial</Text>
        </TouchableOpacity>
      </View>
    </ScrollView>
  );
}
```

---

## Part 6: Testing

### Test Mode (Stripe)

Use test credit cards:
- **Success**: `4242 4242 4242 4242`
- **Decline**: `4000 0000 0000 0002`
- Use any future expiry date
- Use any 3-digit CVC

### Testing Flow

1. Sign in to app
2. Try to create 21st log (should hit limit)
3. Click "Upgrade"
4. Complete checkout with test card
5. Verify unlimited access
6. Test cancellation

---

## Part 7: Production Checklist

Before going live:

- [ ] Switch Stripe to live mode (get live API keys)
- [ ] Update webhook URL to production
- [ ] Test with real credit card
- [ ] Set up Stripe tax collection (if required)
- [ ] Configure email receipts in Stripe
- [ ] Add refund policy to app
- [ ] Test subscription cancellation
- [ ] Test webhook handling
- [ ] Set up monitoring for failed payments

---

## Cost Breakdown

**Stripe Fees:**
- 2.9% + $0.30 per successful charge
- No monthly fees
- Example: $14.99 subscription = $0.73 fee = $14.26 revenue

**RevenueCat (optional):**
- Free up to $10,000/month revenue
- 1% of revenue above that
- Saves development time on mobile

**Your margins:**
- $14.99 subscription
- - $0.73 Stripe fee
- - $3.00 API costs (Claude + Whisper + TTS)
- = $11.26 profit (75% margin)

---

## Troubleshooting

### "Webhook signature verification failed"
**Solution:** Check STRIPE_WEBHOOK_SECRET matches Stripe dashboard

### "Customer not found"
**Solution:** Make sure you're creating Stripe customer on signup

### "Price not found"
**Solution:** Verify price IDs in subscriptions.py match Stripe

### "Payment requires authentication"
**Solution:** Normal for 3D Secure cards - Stripe handles this

---

## What You Have Now

✅ **Complete subscription system**
✅ **Usage limits enforced**
✅ **Stripe integration**
✅ **7-day free trial**
✅ **Upgrade prompts**
✅ **Billing portal**
✅ **Webhook handling**

**Total setup time:** 2-3 hours

**Ready to monetize!** 💰
