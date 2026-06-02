# Deployment Checklist - Post-Fix Actions

## ⚡ IMMEDIATE (Before Deploy)

### 1. Railway Environment Variables
```bash
# Required - Set in Railway dashboard
ADMIN_TOKEN=<generate-strong-random-token>

# Optional - Override CORS if needed
CORS_ORIGINS=https://polttoaine-notifi.vercel.app,https://yourdomain.com
```

**To generate secure token:**
```bash
openssl rand -base64 32
# or
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

### 2. Deploy to Railway
Railway will auto-deploy on next push to GitHub. The build will:
- Install new dependencies from `requirements.txt`
- Restart with tightened security

**Verify deployment:**
```bash
# Check health
curl https://polttoaine-notifi-production.up.railway.app/api/health

# Verify auth works (should fail without token)
curl -X POST https://polttoaine-notifi-production.up.railway.app/api/notify/test
# Expected: 401 Unauthorized or 503 Service Unavailable
```

### 3. Test with Admin Token
```bash
# Set your token
export ADMIN_TOKEN="your-token-here"

# Test authenticated endpoint
curl -X POST https://polttoaine-notifi-production.up.railway.app/api/notify/test \
  -H "X-Admin-Token: $ADMIN_TOKEN"
# Expected: 200 OK with notification sent
```

## 📋 RECOMMENDED (Within 1 Week)

### 4. Create Minimal CI Requirements File
```bash
cd backend
cat > requirements-ci.txt << 'EOFCI'
requests==2.32.3
beautifulsoup4==4.12.3
EOFCI
```

Then update `.github/workflows/check.yml` line 22:
```yaml
- run: pip install -r requirements-ci.txt  # Changed from requirements.txt
```

### 5. Fix Root Scrapers (if used)
Apply same fixes to root `scrapers/`:
- `scrapers/polttoaine.py`: Change regex to `r"(\d+[.,]\d{2,3})"`
- `scrapers/tankille.py`: Fix freshness parser (move plural check first)

Or simply delete root `scrapers/` if `check_prices.py` isn't critical.

### 6. Reduce CI Frequency (Optional)
`.github/workflows/check.yml` line 6:
```yaml
# Before
- cron: "*/15 * * * *"  # Every 15 min = 96 runs/day

# After (recommended)
- cron: "*/30 * * * *"  # Every 30 min = 48 runs/day
# or
- cron: "0 * * * *"     # Hourly = 24 runs/day
```

## 🧪 POST-DEPLOY TESTING

### Test Suite
```bash
export BACKEND="https://polttoaine-notifi-production.up.railway.app"
export ADMIN_TOKEN="your-token"

# 1. Authentication works
echo "Testing auth..."
curl -X POST "$BACKEND/api/notify/test" | grep -q "401\|503" && echo "✅ Auth required" || echo "❌ Auth bypass!"

# 2. Rate limiting works
echo "Testing rate limits..."
for i in {1..12}; do
  curl -s -o /dev/null -w "%{http_code}\n" -X POST "$BACKEND/api/predict/run" \
    -H "Content-Type: application/json" -d '{"fuel":"95E10","region":"Suomi"}'
done | tail -2 | grep -q 429 && echo "✅ Rate limiting active" || echo "⚠️  Rate limiting may not be working"

# 3. Region validation works
echo "Testing region validation..."
curl -X POST "$BACKEND/api/predict/run" \
  -H "Content-Type: application/json" \
  -d '{"fuel":"95E10","region":"Helsinki"}' 2>&1 | grep -q "only region='Suomi' supported" \
  && echo "✅ Region validation active" || echo "❌ Region validation failed"

# 4. Check logs don't leak credentials
echo "Check Railway logs manually - MONGO_URL should NOT appear"
```

## 📊 MONITORING (First Week)

### Watch For
1. **Railway Logs**: No `MONGO_URL` should appear
2. **Error Rates**: Rate limiting may need tuning if legitimate users hit 429s
3. **Prediction Accuracy**: MAE should improve by 15-25% as data accumulates
4. **ntfy Spam**: Verify no unauthorized notifications

### Quick Health Check
```bash
# Daily for first week
curl -s "$BACKEND/api/health" | jq
curl -s "$BACKEND/api/predict/latest?fuel=95E10" | jq '.methods.fundamental_anchor'
# Should see a value (not null) after first 14:00 or 21:00 capture
```

## 🚨 ROLLBACK PLAN (If Issues)

If critical issues appear post-deploy:

1. **Railway**: Revert to previous deployment in dashboard
2. **Environment**: Remove `ADMIN_TOKEN` temporarily to return endpoints to open (not recommended)
3. **Git**: `git revert <commit-hash>` and push

## ✅ SUCCESS CRITERIA

Deploy is successful when:
- [ ] Railway build completes without errors
- [ ] `/api/health` returns 200
- [ ] `/api/notify/test` requires auth (401/503 without token)
- [ ] Rate limiting triggers after 10-20 requests
- [ ] Region validation rejects non-"Suomi"
- [ ] Logs don't contain `MONGO_URL`
- [ ] First prediction after deploy shows `fundamental_anchor` value
- [ ] No unauthorized notifications sent

## 📞 TROUBLESHOOTING

### Issue: "defusedxml not found"
```bash
# SSH to Railway or check build logs
pip install defusedxml==0.7.1
# Likely cause: Railway didn't read updated requirements.txt
# Solution: Force rebuild or manual install
```

### Issue: "slowapi not found"  
```bash
pip install slowapi==0.1.9
# Same as above
```

### Issue: Rate limits too strict
Edit `backend/server.py` and increase limits:
```python
@limiter.limit("20/minute")  # Increase from 10
async def run_prediction...
```

### Issue: ADMIN_TOKEN not working
Verify in Railway dashboard:
1. Variable is named exactly `ADMIN_TOKEN`
2. No extra spaces in value
3. Redeploy after setting (env changes need restart)

## 📚 REFERENCES

- Full audit: See conversation history
- Fixes applied: FIXES_APPLIED.md
- Railway logs: https://railway.app/project/<your-project>/deployments
- Vercel logs: https://vercel.com/<your-project>/deployments
