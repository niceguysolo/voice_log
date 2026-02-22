# Deployment Guide - Railway.app

Railway.app is the **easiest** way to deploy your Python backend. This guide will take you from local development to production in ~30 minutes.

## Why Railway?

✅ **Easy setup** - Deploy from GitHub in minutes
✅ **Automatic HTTPS** - SSL certificates included
✅ **PostgreSQL included** - One-click database
✅ **Affordable** - $5-20/month for starter apps
✅ **Environment variables** - Easy secrets management
✅ **Auto-deploy** - Push to GitHub → Auto-deploy

## Prerequisites

1. **GitHub account** - https://github.com/
2. **Railway account** - https://railway.app/ (sign in with GitHub)
3. **Your code on GitHub** - We'll set this up

## Step 1: Prepare Your Code for Deployment

### 1.1 Create Required Files

**requirements.txt** (add these to existing):
```
fastapi==0.109.0
uvicorn[standard]==0.27.0
anthropic==0.18.0
openai==1.12.0
sqlalchemy==2.0.25
psycopg2-binary==2.9.9
python-jose[cryptography]==3.3.0
python-multipart==0.0.9
pydantic==2.6.0
httpx==0.26.0
python-dotenv==1.0.0
gunicorn==21.2.0
```

**Procfile** (Railway needs this):
```
web: gunicorn voice_log_backend_db:app --workers 4 --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:$PORT
```

**runtime.txt** (specify Python version):
```
python-3.11.7
```

**.gitignore** (don't commit secrets):
```
__pycache__/
*.pyc
.env
*.db
venv/
.DS_Store
audio_files/
```

### 1.2 Update Your Code

Add this to the top of `voice_log_backend_db.py`:

```python
import os

# Get PORT from environment (Railway provides this)
PORT = int(os.getenv("PORT", 8000))

# At the bottom of file, change:
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
```

## Step 2: Push Code to GitHub

### 2.1 Initialize Git Repository

```bash
cd your-project-directory

# Initialize git
git init

# Add all files
git add .

# Commit
git commit -m "Initial commit - Voice Log API"
```

### 2.2 Create GitHub Repository

1. Go to https://github.com/new
2. Repository name: `voice-log-api`
3. Make it **Private** (recommended)
4. Click "Create repository"

### 2.3 Push to GitHub

```bash
# Add remote
git remote add origin https://github.com/YOUR_USERNAME/voice-log-api.git

# Push
git branch -M main
git push -u origin main
```

## Step 3: Deploy to Railway

### 3.1 Create Railway Project

1. Go to https://railway.app/
2. Click "Start a New Project"
3. Click "Deploy from GitHub repo"
4. Select your `voice-log-api` repository
5. Click "Deploy Now"

Railway will automatically:
- Detect it's a Python app
- Install dependencies from requirements.txt
- Run using your Procfile
- Assign a public URL

### 3.2 Add PostgreSQL Database

1. In your Railway project dashboard
2. Click "New" → "Database" → "Add PostgreSQL"
3. Railway creates database and sets DATABASE_URL automatically

### 3.3 Set Environment Variables

Click on your service → "Variables" tab → Add:

```
ANTHROPIC_API_KEY=sk-ant-your-key-here
OPENAI_API_KEY=sk-your-openai-key-here
JWT_SECRET_KEY=generate-random-secret-key-here
DATABASE_URL=postgresql://... (Railway sets this automatically)
```

To generate a secure JWT secret:
```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

### 3.4 Get Your URL

1. Go to "Settings" tab
2. Find "Domains" section
3. Click "Generate Domain"
4. Your URL: `https://your-app-name.up.railway.app`

## Step 4: Initialize Database

Railway provides a PostgreSQL terminal. Use it to create tables:

1. Click on PostgreSQL service
2. Click "Connect"
3. Run:
```sql
-- Railway will show connection details
-- Your tables will be created automatically on first request
```

Or run this from your local machine:

```bash
# Set DATABASE_URL from Railway
export DATABASE_URL="postgresql://..."

# Run database setup
python database.py
```

## Step 5: Test Your Deployment

### 5.1 Check Health Endpoint

```bash
curl https://your-app-name.up.railway.app/health
```

Should return:
```json
{
  "status": "healthy",
  "database": "connected",
  "users": 0,
  "logs": 0
}
```

### 5.2 Test API Docs

Visit: `https://your-app-name.up.railway.app/docs`

You'll see interactive API documentation!

### 5.3 Update Mobile App

In your React Native app's `App.js`:

```javascript
const API_URL = 'https://your-app-name.up.railway.app';
```

## Step 6: Set Up Auto-Deploy

Railway automatically deploys when you push to main branch:

```bash
# Make a change
vim voice_log_backend_db.py

# Commit and push
git add .
git commit -m "Updated feature X"
git push

# Railway automatically deploys! (check dashboard)
```

## Costs

Railway pricing (as of 2024):

**Free Tier:**
- $5 free credit per month
- Good for testing
- Limited to 500 hours

**Hobby Plan ($5/month):**
- $5 included usage
- $0.000231/GB-hour for memory
- $0.000463/vCPU-hour
- ~500 requests/month free

**Estimated costs for production:**
- API server: $10-15/month
- PostgreSQL: $5-10/month
- **Total: $15-25/month**

## Environment Variables Reference

Required:
```
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
JWT_SECRET_KEY=random-secret-32-chars
DATABASE_URL=postgresql://... (auto-set by Railway)
```

Optional:
```
USE_S3_STORAGE=false
S3_BUCKET_NAME=your-bucket
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_REGION=us-east-1
```

## Monitoring & Logs

### View Logs

1. Railway dashboard → Your service
2. Click "Deployments" tab
3. Click latest deployment
4. See real-time logs

### Monitor Usage

1. Click "Metrics" tab
2. See CPU, Memory, Network usage

### Set Up Alerts

1. Railway dashboard → Project Settings
2. "Notifications" → Add email/Slack
3. Get notified of deploy failures

## Custom Domain (Optional)

### Add Your Own Domain

1. Buy domain (Namecheap, Google Domains, etc.)
2. Railway Settings → Domains → "Custom Domain"
3. Add your domain: `api.yourdomain.com`
4. Update DNS records as shown by Railway
5. Railway auto-provisions SSL certificate

## Troubleshooting

### "Application failed to respond"

**Problem:** App isn't starting

**Solution:**
1. Check logs in Railway dashboard
2. Verify PORT is read from environment:
   ```python
   PORT = int(os.getenv("PORT", 8000))
   ```
3. Check all dependencies in requirements.txt

### "Database connection failed"

**Problem:** Can't connect to PostgreSQL

**Solution:**
1. Verify DATABASE_URL is set in environment variables
2. Make sure PostgreSQL service is running
3. Check database.py uses DATABASE_URL from env

### "502 Bad Gateway"

**Problem:** App crashed

**Solution:**
1. Check logs for Python errors
2. Test locally first: `python voice_log_backend_db.py`
3. Verify all environment variables are set

## Maintenance

### Update Dependencies

```bash
# Update requirements.txt
pip install --upgrade anthropic openai fastapi

# Freeze new versions
pip freeze > requirements.txt

# Push to GitHub
git add requirements.txt
git commit -m "Updated dependencies"
git push

# Railway auto-deploys
```

### Database Backups

1. Railway PostgreSQL → Settings
2. "Backups" tab
3. Download backup or enable automated backups

### Monitor API Usage

Check your Anthropic/OpenAI dashboard for API usage:
- Anthropic: https://console.anthropic.com/
- OpenAI: https://platform.openai.com/usage

## Production Checklist

Before launching to users:

- [ ] All environment variables set
- [ ] Database initialized
- [ ] API health check passes
- [ ] Test all endpoints with real data
- [ ] Set up monitoring alerts
- [ ] Configure database backups
- [ ] Update mobile app with production URL
- [ ] Test on real devices (iOS and Android)
- [ ] Monitor API costs for first week
- [ ] Set up error tracking (optional: Sentry)

## What You Get

After following this guide:

✅ **Production API** - Running 24/7
✅ **PostgreSQL database** - Persistent storage
✅ **HTTPS** - Secure connections
✅ **Auto-deploy** - Push to deploy
✅ **Monitoring** - Logs and metrics
✅ **Scalable** - Handle thousands of users

Total setup time: **30-45 minutes**

## Next Steps

1. **Deploy backend** using this guide
2. **Update mobile app** with production URL
3. **Test end-to-end** with real users
4. **Monitor costs** - Make sure API usage is as expected
5. **Add features** - Push updates via GitHub

Your app is now production-ready! 🚀
