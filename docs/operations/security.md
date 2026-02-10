# Security Guide

Security best practices and hardening for KI Asset Management.

---

## 🔐 Security Checklist

### Pre-Deployment

- [ ] `SECRET_KEY` is 32+ random characters
- [ ] `.env` is in `.gitignore` (never committed)
- [ ] Database uses strong password
- [ ] `USE_LOCAL_SQLITE=False` in production
- [ ] HTTPS enabled
- [ ] Debug mode disabled (`DEBUG=False`)

### User Security

- [ ] Strong password policy enforced
- [ ] Admin passwords are complex (12+ chars)
- [ ] Regular password rotation (recommended)
- [ ] Account lockout after failed attempts
- [ ] Session timeout configured

### Application Security

- [ ] CSRF protection enabled (default)
- [ ] Rate limiting configured
- [ ] Input validation on all forms
- [ ] SQL injection prevention (ORM usage)
- [ ] XSS protection (auto-escaping)

---

## 🛡️ Security Measures

### 1. Authentication

**Password Requirements:**
- Minimum 8 characters
- Mix of uppercase, lowercase, numbers
- No common passwords

**Session Security:**
- HttpOnly cookies
- Secure flag in production
- SameSite=Lax
- 24-hour timeout

### 2. Authorization

**Role-Based Access:**
- Public: Landing page, blog
- Analyst: Dashboard, blog posts
- Admin: Full system access

### 3. Data Protection

**In Transit:**
- TLS 1.2+ required
- HSTS headers
- Secure cookies

**At Rest:**
- Database encryption (neon.tech)
- No sensitive data in logs
- Passwords hashed with bcrypt

### 4. Network Security

**Headers Set:**
```
Content-Security-Policy
X-Content-Type-Options: nosniff
X-Frame-Options: SAMEORIGIN
X-XSS-Protection: 1; mode=block
Strict-Transport-Security
Referrer-Policy: strict-origin-when-cross-origin
```

---

## 🔍 Security Monitoring

### Log Review

Watch for:
- Failed login attempts (brute force)
- Unusual access patterns
- Privilege escalation attempts
- SQL injection attempts
- XSS attempts

### Alerts

Set up alerts for:
- Multiple failed logins from same IP
- Admin account changes
- Database errors
- High error rates

---

## 🚨 Incident Response

### Security Breach Response

1. **Immediate (0-15 min)**
   - Isolate affected systems
   - Preserve logs
   - Change admin passwords

2. **Short-term (15 min - 2 hours)**
   - Assess scope of breach
   - Identify compromised data
   - Block malicious IPs

3. **Medium-term (2-24 hours)**
   - Restore from clean backup if needed
   - Patch vulnerabilities
   - Reset all user passwords

4. **Long-term (24+ hours)**
   - Post-incident review
   - Update security measures
   - Document lessons learned

---

## 🔧 Hardening

### Server Hardening

```bash
# Update system
apt update && apt upgrade -y

# Firewall
ufw allow 'Nginx Full'
ufw allow OpenSSH
ufw enable

# Fail2ban (brute force protection)
apt install fail2ban
systemctl enable fail2ban
```

### Application Hardening

1. **Remove default accounts**
   - Delete or rename default admin if any

2. **Limit file uploads**
   - Size restrictions
   - Type validation
   - Virus scanning (if possible)

3. **Disable unused features**
   - Remove debug endpoints
   - Disable unnecessary APIs

---

## 📋 Security Audit

### Quarterly Review

- [ ] Access log review
- [ ] User permission audit
- [ ] Password strength check
- [ ] Dependency vulnerability scan
- [ ] SSL certificate validity
- [ ] Backup encryption

### Tools

```bash
# Dependency vulnerabilities
pip install safety
safety check

# SSL configuration test
nmap --script ssl-enum-ciphers -p 443 your-domain.com

# Security headers check
curl -I https://your-domain.com
```

---

## 🆘 Reporting Security Issues

**Please do NOT open public issues for security vulnerabilities.**

Instead:
1. Review existing security advisories
2. Contact the maintainers privately through available channels
3. Include detailed steps to reproduce
4. Allow time for response before public disclosure

---

<p align="center">
  <strong>Security is everyone's responsibility</strong>
</p>
