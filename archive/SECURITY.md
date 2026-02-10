# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 1.x     | :white_check_mark: |

## Security Measures Implemented

This application implements the following security measures:

### 1. SQL Injection Protection
- All database queries use SQLAlchemy ORM with parameterized queries
- Raw SQL queries have been replaced with safe ORM equivalents
- User input is never directly interpolated into SQL statements

### 2. Cross-Site Scripting (XSS) Protection
- Jinja2 auto-escaping is enabled by default
- Content Security Policy (CSP) headers are set
- User input is sanitized before storage

### 3. Cross-Site Request Forgery (CSRF) Protection
- Flask-WTF CSRF protection is enabled on all forms
- CSRF tokens are required for all state-changing requests

### 4. Session Security
- Secure cookie flags (HttpOnly, Secure in production)
- SameSite cookie attribute set to 'Lax'
- Session timeout after 24 hours of inactivity

### 5. Clickjacking Protection
- X-Frame-Options header set to 'SAMEORIGIN'
- CSP frame-ancestors directive set

### 6. Rate Limiting
- Login attempts are rate-limited (5 attempts per 15 minutes)
- Password reset attempts are rate-limited
- API endpoints have appropriate rate limits

### 7. Input Validation
- All user inputs are validated using WTForms
- Maximum length limits on all text fields
- File upload restrictions (type, size)

### 8. Security Headers
The following security headers are set on all responses:
- `Content-Security-Policy`
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: SAMEORIGIN`
- `X-XSS-Protection: 1; mode=block`
- `Strict-Transport-Security` (in production)
- `Referrer-Policy: strict-origin-when-cross-origin`

## Reporting a Vulnerability

If you discover a security vulnerability, please:

1. **Do not** open a public issue
2. Email security concerns to: security@klubinvestoru.com
3. Include detailed steps to reproduce the issue
4. Allow up to 48 hours for initial response

## Security Best Practices for Deployment

1. **Use HTTPS**: Always deploy with HTTPS in production
2. **Environment Variables**: Keep SECRET_KEY and database credentials in environment variables
3. **Database**: Use PostgreSQL in production, not SQLite
4. **Updates**: Keep dependencies updated regularly
5. **Monitoring**: Monitor logs for suspicious activity
6. **Backups**: Regular database backups

## Security Checklist for Production

- [ ] SECRET_KEY is set to a cryptographically secure random value (32+ bytes)
- [ ] DATABASE_URL uses a strong password
- [ ] USE_LOCAL_SQLITE is set to False
- [ ] HTTPS is enforced
- [ ] Debug mode is disabled (DEBUG=False)
- [ ] Email configuration uses secure SMTP or SendGrid API
- [ ] Server headers don't reveal version information
- [ ] File uploads are scanned for malware
- [ ] Regular security audits are performed
