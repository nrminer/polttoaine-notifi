# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in BensaVahti, please report it by emailing the maintainers. Do not open a public issue.

**Please include:**
- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

We will respond within 48 hours and provide a timeline for a fix.

---

## Admin Token Security

### Current Token
- **Location:** Railway environment variable `ADMIN_TOKEN`
- **Strength:** 48 characters, high entropy (verified)
- **Expiry:** No automatic expiry (manual rotation required)

### Token Rotation Procedure

**When to rotate:**
- Every 90 days (scheduled)
- Immediately if suspected compromise
- After employee departure
- After any security incident

**How to rotate:**

1. **Generate new token:**
   ```bash
   openssl rand -hex 32
   ```

2. **Update Railway:**
   - Go to Railway dashboard → Project → Variables
   - Update `ADMIN_TOKEN` with new value
   - Railway will automatically redeploy

3. **Update admin users:**
   - Notify all admin panel users
   - They must clear localStorage and enter new token
   - Old token becomes invalid immediately after deploy

4. **Verify:**
   ```bash
   curl -X POST "$BACKEND/api/admin/run" \
     -H "X-Admin-Token: $NEW_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"action":"ping"}'
   ```

5. **Document:**
   - Log rotation date
   - Log reason (scheduled / incident)
   - Update team documentation

---

## Incident Response Plan

### Scenario: Admin Token Leaked

**Immediate actions (within 1 hour):**

1. **Rotate token immediately:**
   - Generate new token (see above)
   - Update Railway `ADMIN_TOKEN`
   - Wait for deployment (~2 minutes)

2. **Check audit logs:**
   ```bash
   # Connect to MongoDB Atlas
   # Query audit_log collection for suspicious activity
   db.audit_log.find({
     timestamp: { $gte: ISODate("2026-XX-XXTXX:00:00Z") }
   }).sort({timestamp: -1})
   ```

3. **Check failed auth attempts:**
   ```bash
   db.failed_auth.find({
     timestamp: { $gte: ISODate("2026-XX-XXTXX:00:00Z") }
   }).sort({timestamp: -1})
   ```

4. **Review recent captures:**
   ```bash
   db.daily_tracker.find({
     manually_corrected: true
   }).sort({fixed_at: -1}).limit(10)
   ```

**Investigation (within 24 hours):**

5. **Analyze audit logs:**
   - Look for unauthorized actions
   - Identify IPs of attacker
   - Check what data was accessed/modified

6. **Assess damage:**
   - Were any prices manually corrupted?
   - Were any predictions manipulated?
   - Was sensitive data exported?

7. **Restore from backup if needed:**
   - MongoDB Atlas → Backups → Restore to point-in-time
   - Test in staging environment first

**Communication (within 48 hours):**

8. **Internal notification:**
   - Inform team of incident
   - Share timeline and impact
   - Document lessons learned

9. **External notification (if user data affected):**
   - Draft notification
   - Legal review
   - Public disclosure (if required)

**Prevention (within 1 week):**

10. **Root cause analysis:**
    - How was token leaked?
    - What controls failed?
    - What can prevent recurrence?

11. **Implement fixes:**
    - Add MFA if phishing was the vector
    - Add IP whitelisting if feasible
    - Rotate all other credentials
    - Update security training

---

### Scenario: Database Breach

**Immediate actions:**

1. **Isolate database:**
   - MongoDB Atlas → Network Access → Remove all IPs
   - Add only Railway egress IPs

2. **Change MongoDB credentials:**
   - Atlas → Database Access → Edit user → Generate new password
   - Update Railway `MONGO_URL` immediately

3. **Check for data exfiltration:**
   - Atlas → Metrics → Check for unusual traffic spikes
   - Atlas → Logs → Look for bulk reads

4. **Restore from backup:**
   - If data was modified, restore from last known good backup
   - Verify integrity before switching

**Investigation:**
- Review Atlas access logs
- Check for SQL injection attempts (none in our stack, but verify)
- Verify all data sources (scrapers, API endpoints)

---

### Scenario: Malicious Price Data Injection

**Immediate actions:**

1. **Identify bad data:**
   ```bash
   db.daily_tracker.find({
     $or: [
       {verification_failed: true},
       {verification_override: true},
       {manually_corrected: true}
     ]
   }).sort({captured_at: -1})
   ```

2. **Fix corrupted captures:**
   - Use `/api/admin/fix-capture` to correct prices
   - Reference legitimate source (polttoaine.net archive)

3. **Disable auto-capture temporarily:**
   - Stop Railway backend service
   - Investigate scraper compromise

4. **Check audit logs:**
   - Who made manual corrections?
   - Were captures triggered by admin endpoint?

**Prevention:**
- Review price verification bounds (`price_verification.py`)
- Add anomaly detection alerts
- Require multi-admin approval for manual fixes

---

## Security Contacts

- **Primary:** [Your team contact]
- **Railway support:** https://railway.app/help
- **MongoDB Atlas support:** https://www.mongodb.com/cloud/atlas/support
- **Vercel support:** https://vercel.com/support

---

## Security Checklist (Monthly Review)

- [ ] Review audit logs for anomalies
- [ ] Check failed auth attempts for brute-force patterns
- [ ] Verify MongoDB Atlas IP whitelist is current
- [ ] Run `pip-audit` and `npm audit` for dependency CVEs
- [ ] Test backup restoration procedure
- [ ] Verify CORS origins match production frontend
- [ ] Check Railway logs for errors or suspicious activity
- [ ] Review admin token last rotation date (rotate if >90 days)
- [ ] Verify no secrets in git history: `git log -p | grep -i "admin.*token"`
- [ ] Test health endpoint: `curl $BACKEND/api/health`

---

## Useful Commands

### Check audit logs (MongoDB shell):
```javascript
// Last 24 hours of admin actions
db.audit_log.find({
  timestamp: { $gte: new Date(Date.now() - 24*60*60*1000) }
}).sort({timestamp: -1})

// Failed auth attempts by IP
db.failed_auth.aggregate([
  { $group: { _id: "$client_ip", count: { $sum: 1 } } },
  { $sort: { count: -1 } }
])

// Recent manual fixes
db.daily_tracker.find({
  manually_corrected: true,
  fixed_at: { $exists: true }
}).sort({fixed_at: -1}).limit(10)
```

### Test endpoints:
```bash
# Health check
curl https://polttoaine-notifi-production.up.railway.app/api/health

# Admin auth test
curl -X POST "$BACKEND/api/admin/run" \
  -H "X-Admin-Token: $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"action":"ping"}'
```

### Emergency token rotation:
```bash
# 1. Generate
NEW_TOKEN=$(openssl rand -hex 32)
echo $NEW_TOKEN

# 2. Update Railway (manual via UI)

# 3. Test
curl -X POST "$BACKEND/api/admin/run" \
  -H "X-Admin-Token: $NEW_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"action":"ping"}'
```

---

## Version History

- **2026-06-21:** Initial security policy created
  - Admin panel audit logging added
  - Failed auth tracking implemented
  - Token expiry (24h) added to frontend
  - Health check endpoint enhanced with DB connectivity test
