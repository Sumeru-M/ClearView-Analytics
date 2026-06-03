# Render Deployment Guide

**Status**: ✅ Ready for Render deployment

---

## Quick Start

### Step 1: Connect GitHub to Render

1. Go to https://render.com
2. Sign in or create account
3. Click **"New +"** → **"Web Service"**
4. Connect your GitHub account
5. Select **ClearView-Analytics** repository
6. Click **Connect**

### Step 2: Configure Service

Fill in the deployment form:

- **Name**: `clearview-analytics`
- **Environment**: `Python 3`
- **Build Command**: `pip install -r requirements.txt`
- **Start Command**: `gunicorn --workers 4 --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000 src.main:app`
- **Instance Type**: Standard

### Step 3: Set Environment Variables

In the **Environment** section, add:

```
AUTH_SECRET = (generate a secure random string, or use default)
CORS_ORIGINS = *
```

### Step 4: Create Service

Click **Create Web Service**

Render will:
1. Clone the repository
2. Install dependencies (pip install -r requirements.txt)
3. Start the application
4. Assign a URL like: `https://clearview-analytics-xxxx.onrender.com`

---

## Automatic Deployment

Once connected, **every push to main will automatically deploy**:

```bash
git push origin main
# Render automatically deploys new commits
```

Check deployment status in Render dashboard.

---

## Alternative: Use render.yaml

If Render detects `render.yaml`, it will use those settings automatically.

Our `render.yaml` includes:
- ✅ Python 3.11
- ✅ gunicorn + uvicorn
- ✅ Auto-deploy enabled
- ✅ Health check configured

---

## Verify Deployment

Once deployed, test these endpoints:

```bash
# Health check
curl https://clearview-analytics-xxxx.onrender.com/api/health

# Should return:
{"status": "ok"}
```

---

## Access the Application

Once deployed:

1. Get your Render URL from dashboard
2. Visit: `https://YOUR-RENDER-URL/`
3. Sign in with test credentials (or register new account)
4. See the **professional institutional design** with navy backgrounds

---

## Frontend Features After Deployment

The UI now includes:

✅ **Professional Navy Palette**: Dark navy backgrounds (#0f1419)
✅ **Typography Hierarchy**: Geist/Inter fonts, 5-level hierarchy
✅ **Semantic Colors**: Green/Red/Orange/Blue for indicators
✅ **Spacing System**: 8px modular spacing throughout
✅ **Responsive Design**: Works on desktop, tablet, mobile
✅ **Institutional Aesthetic**: Inspired by Koyfin/Bloomberg

---

## Troubleshooting

### Build Fails

Check logs in Render dashboard:

1. Click service name
2. Go to **"Logs"** tab
3. Look for error messages

Common issues:
- Missing environment variables
- Python version mismatch
- Missing dependencies

### Application Won't Start

Verify in logs:
- `gunicorn` is installed
- FastAPI imports work
- Database connection succeeds

### CSS Not Showing

1. Hard refresh browser (Ctrl+Shift+R or Cmd+Shift+R)
2. Check browser console for errors
3. Verify HTML is served correctly

---

## Database Setup (if needed)

If using authentication:

1. Auth database is created automatically
2. Users stored in `/tmp/clearview_auth.db` on Render
3. Database persists within service instance

For persistent storage, use Render PostgreSQL (optional):
- Add PostgreSQL database in Render dashboard
- Configure `AUTH_DB_PATH` environment variable

---

## Monitoring

After deployment:

1. **Error Logs**: Check Render dashboard "Logs" tab
2. **Performance**: Monitor in Render dashboard
3. **Health**: `/api/health` endpoint available
4. **Uptime**: Render tracks and displays in dashboard

---

## Custom Domain (Optional)

To use a custom domain:

1. In Render dashboard, go to service settings
2. Add custom domain
3. Update DNS records (Render will provide instructions)

---

## Files Changed

- ✅ `render.yaml` - Render configuration
- ✅ `requirements.txt` - Added gunicorn
- ✅ `.renderignore` - Exclude unnecessary files
- ✅ Removed: `vercel.json`, `.vercel/` directory

---

## Summary

**Your application is now configured for Render deployment!**

### Next Steps:

1. Go to https://render.com/dashboard
2. Create new Web Service
3. Connect GitHub repository
4. Set environment variables
5. Deploy

**Deployment time**: ~2-5 minutes

**Your live URL** will be displayed in Render dashboard after deployment.

---

## Support

For Render deployment issues:
- Render Docs: https://render.com/docs
- Render Support: https://support.render.com

For application issues:
- Check logs in Render dashboard
- Verify environment variables are set
- Test endpoints with curl
