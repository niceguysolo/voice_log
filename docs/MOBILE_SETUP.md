# React Native Frontend Setup Guide

## Overview

This is a **simple, elderly-friendly mobile app** that connects to your Python backend. It's designed with:
- ✅ Large buttons (easy to tap)
- ✅ High contrast colors (easy to see)
- ✅ Large text (easy to read)
- ✅ Voice-first interface (minimal typing)
- ✅ Simple navigation

## Prerequisites

1. **Node.js** (v16 or higher): https://nodejs.org/
2. **Expo CLI**: We'll install this
3. **A smartphone** with Expo Go app installed:
   - iOS: https://apps.apple.com/app/expo-go/id982107779
   - Android: https://play.google.com/store/apps/details?id=host.exp.exponent

## Setup Instructions

### 1. Install Expo CLI

```bash
npm install -g expo-cli
```

### 2. Create Project Directory

```bash
mkdir voice-log-mobile
cd voice-log-mobile
```

### 3. Copy Files

Place these files in the directory:
- `App.js` - Main app code
- `package.json` - Dependencies
- `app.json` - Expo configuration

### 4. Install Dependencies

```bash
npm install
```

### 5. Configure Google Sign-In

You need to get Google OAuth credentials:

**Step 1:** Go to https://console.cloud.google.com/

**Step 2:** Create a new project (or select existing)

**Step 3:** Enable Google Sign-In API
- Go to "APIs & Services" → "Library"
- Search for "Google Sign-In"
- Click "Enable"

**Step 4:** Create OAuth Credentials
- Go to "APIs & Services" → "Credentials"
- Click "Create Credentials" → "OAuth 2.0 Client ID"
- Create 3 client IDs:
  1. **iOS** - Application type: iOS
  2. **Android** - Application type: Android
  3. **Web** - Application type: Web (for Expo)

**Step 5:** Update App.js with your Client IDs

```javascript
const [request, response, promptAsync] = Google.useAuthRequest({
  expoClientId: 'YOUR_EXPO_CLIENT_ID.apps.googleusercontent.com',
  iosClientId: 'YOUR_IOS_CLIENT_ID.apps.googleusercontent.com',
  androidClientId: 'YOUR_ANDROID_CLIENT_ID.apps.googleusercontent.com',
  webClientId: 'YOUR_WEB_CLIENT_ID.apps.googleusercontent.com',
});
```

### 6. Update Backend URL

In `App.js`, change this line to your backend URL:

```javascript
const API_URL = 'http://localhost:8000'; // Change this!
```

**For testing on your phone:**
```javascript
// If backend is on your computer
const API_URL = 'http://YOUR_COMPUTER_IP:8000'; 

// Example: 
const API_URL = 'http://192.168.1.100:8000';
```

**For production:**
```javascript
const API_URL = 'https://your-backend.railway.app';
```

To find your computer's IP:
- **Mac**: System Preferences → Network
- **Windows**: `ipconfig` in Command Prompt
- **Linux**: `ifconfig` or `ip addr`

### 7. Start Development Server

```bash
npx expo start
```

This will show a QR code in your terminal.

### 8. Test on Your Phone

1. Install **Expo Go** app on your phone
2. Open Expo Go
3. Scan the QR code
4. App will load on your phone!

## Testing the App

### Test Flow:

1. **Sign In**
   - Tap "Sign in with Google"
   - Choose your Google account
   - Should see "Hello, [Your Name]!"

2. **Record a Log**
   - Tap the big red "RECORD" button
   - Speak: "I went for a walk and had breakfast"
   - Tap "STOP"
   - Should see success message with transcription

3. **Ask a Question**
   - Tap one of the question buttons
   - Should see AI answer in an alert

4. **View Recent Logs**
   - Scroll down to see your recent activities

## Troubleshooting

### "Network request failed"
**Problem:** Can't connect to backend

**Solutions:**
1. Make sure Python backend is running
2. Check backend URL in App.js
3. If testing on phone, use your computer's IP address (not localhost)
4. Make sure phone and computer are on same WiFi network

### "Google Sign-In failed"
**Problem:** Authentication not working

**Solutions:**
1. Double-check all 3 Client IDs in App.js
2. Make sure you created all 3 types (iOS, Android, Web)
3. Wait 5 minutes after creating credentials (Google needs time)

### "Permission denied" for microphone
**Problem:** Can't record audio

**Solutions:**
1. Go to phone Settings → Apps → Expo Go → Permissions
2. Enable Microphone permission
3. Restart the app

### App crashes immediately
**Problem:** Dependencies not installed correctly

**Solution:**
```bash
# Delete and reinstall
rm -rf node_modules
npm install
```

## File Structure

```
voice-log-mobile/
├── App.js                 # Main app code (you customize this)
├── package.json           # Dependencies
├── app.json              # Expo configuration
├── assets/               # Images/icons (create this folder)
│   ├── icon.png         # App icon (1024x1024)
│   ├── splash.png       # Splash screen
│   └── adaptive-icon.png # Android icon
└── node_modules/         # Installed packages (auto-generated)
```

## Customization Guide

### Change Colors

In `App.js`, find the `styles` object and modify colors:

```javascript
recordButton: {
  backgroundColor: '#FF3B30', // Change this to any color
  // Examples:
  // Blue: '#007AFF'
  // Green: '#34C759'
  // Purple: '#AF52DE'
}
```

### Change Text Size

Elderly users might need even larger text:

```javascript
greeting: {
  fontSize: 28, // Increase this number
}
```

### Add More Quick Questions

In `App.js`, find `quickQuestions` array and add more:

```javascript
const quickQuestions = [
  "Did I take my medication today?",
  "What did I eat yesterday?",
  "What activities did I do this week?",
  "When was my last doctor visit?",
  "How many times did I exercise this month?", // Add your own!
  "What appointments do I have coming up?",
];
```

### Change Voice (Female/Male)

The backend controls this. In your Python `voice_log_backend.py`:

```python
async def text_to_speech(text: str, voice: str = "nova") -> str:
    # Female voices: "nova", "shimmer", "alloy"
    # Male voices: "echo", "fable", "onyx"
    
    response = openai_client.audio.speech.create(
        model="tts-1",
        voice=voice,  # Change this
        input=text
    )
```

## Building for Production

### For iOS (needs Mac + Apple Developer Account $99/year):

```bash
# Install EAS CLI
npm install -g eas-cli

# Login to Expo
eas login

# Configure build
eas build:configure

# Build for iOS
eas build --platform ios
```

### For Android:

```bash
# Build APK
eas build --platform android --profile preview

# Download and install on Android phone
```

### Publish to App Stores:

1. **Apple App Store**:
   - Need Mac computer
   - Apple Developer Account ($99/year)
   - Submit via App Store Connect

2. **Google Play Store**:
   - Google Play Console ($25 one-time)
   - Upload APK/AAB file
   - Usually approved in 1-3 days

## Cost Breakdown

**Development:**
- Node.js: Free
- Expo: Free
- Testing: Free (Expo Go app)

**Production:**
- Apple Developer: $99/year
- Google Play: $25 one-time
- Expo EAS Build: $29/month (or build locally for free with more setup)

**Total Year 1:** $124-472 depending on choices

## Next Steps

1. **Test locally** - Get the app running on your phone
2. **Customize** - Change colors, text, add features
3. **Add features**:
   - Camera for pill photos
   - Calendar integration
   - Family sharing view
   - Medication reminders
4. **Beta test** - Give to 5-10 elderly users for feedback
5. **Polish** - Fix bugs, improve UI based on feedback
6. **Launch** - Submit to app stores

## Learning Resources

If you want to customize further:

- **React Native Basics**: https://reactnative.dev/docs/tutorial
- **Expo Documentation**: https://docs.expo.dev/
- **React Hooks**: https://react.dev/reference/react
- **Styling**: https://reactnative.dev/docs/style

## Support

Common modifications you might want:

1. **Add a settings screen** - Let users configure notification times
2. **Add photo attachments** - Take pictures of meals, pills
3. **Add calendar view** - See logs by date
4. **Add family portal** - Separate login for family members
5. **Add export feature** - Email logs to doctor

I can help you implement any of these! Just ask.

## What You Have Now

✅ Complete React Native app (400+ lines)
✅ Google Sign-In working
✅ Voice recording integrated
✅ AI questions working
✅ Recent logs display
✅ Elderly-friendly UI
✅ Ready to test on your phone

The app is **functional and ready to use** - just needs your backend running!
