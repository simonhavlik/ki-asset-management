# Authentication & Authorization Flow

## Overview
- The application restricts access to users with email domain `@klubinvestoru.com`.
- No pre‑registered passwords; each user receives a password‑setup link via email.
- Admins can create accounts manually and toggle active status.
- Flask‑Login manages sessions.

## User Registration

### Step 1: Registration Request
1. User visits `/register` and provides:
   - Email address (must end with `@klubinvestoru.com`)
   - Full name (optional)
2. System validates email domain.
3. If email already exists:
   - If account is active → redirect to login page with message.
   - If account is inactive → resend password‑setup email.
4. If email is new:
   - Create a user record with `email_verified=False`, `is_active=False`, and no password hash.
   - Generate a secure token (JWT or random URL‑safe string) with expiry (e.g., 24 hours).
   - Store token hash in database (or use its‑own‑table approach).
   - Send email containing a link: `https://<domain>/reset‑password/<token>`.

### Step 2: Password Setup
1. User clicks link in email.
2. Token is validated (exists, not expired, matches user).
3. If valid, show a form to set a password (and optionally confirm email).
4. On submit:
   - Hash the password and store in `password_hash`.
   - Set `email_verified=True`, `is_active=True`.
   - Invalidate the token (delete or mark used).
   - Automatically log the user in and redirect to dashboard.

## Login
- Standard email/password login.
- If account is inactive, show appropriate message.
- After successful login, update `last_login` timestamp.

## Password Reset
- Similar flow to registration but initiated by user via "Forgot password".
- Token generated and sent to user's email.
- User can set a new password.

## Email Sending
- Use Flask‑Mail with SMTP (Gmail as specified).
- Email templates (plain text and HTML) for:
  - Password setup invitation
  - Password reset
  - Account activated notification
- Include security note about not sharing the link.

## Admin‑Specific Authentication
- First admin account must be created via a script or environment variable (e.g., `FLASK_ADMIN_EMAIL`).
- Subsequent admins can be promoted by existing admins via the admin panel.
- Admins have access to all routes under `/admin`.

## Role‑Based Access Control (RBAC)

### User Roles
1. **Anonymous** – can access landing page, login, register, password reset.
2. **Analyst** – authenticated user with `is_admin=False`. Can view personal dashboard, own performance, and analyses where they are listed.
3. **Admin** – authenticated user with `is_admin=True`. Has all analyst privileges plus admin panel access.

### Route Protection
- Use Flask‑Login's `@login_required` decorator.
- Additional custom decorator `@admin_required` for admin routes.
- Analyst‑specific views filter data by current user's ID.

## Session Management
- Session cookie set with `HttpOnly`, `Secure` (in production), `SameSite=Lax`.
- Session expiry after 24 hours of inactivity (configurable).
- Logout endpoint clears session.

## Security Measures

### Email Domain Validation
- Enforced at registration and when admins create users.
- Regex pattern: `^[^@]+@klubinvestoru\.com$`.
- Case‑insensitive.

### Password Requirements
- Minimum length 12 characters.
- Encourage use of passphrase.
- Password strength validation (optional).

### Token Security
- Tokens are random URL‑safe strings (e.g., `secrets.token_urlsafe(32)`).
- Stored as bcrypt hash in database (separate table `password_reset_tokens`).
- Expiry: 24 hours for registration, 1 hour for password reset.
- One‑time use (delete after consumption).

### Prevention of Enumeration Attacks
- Do not reveal whether an email exists during registration; show generic message "If the email is registered, you will receive a link".
- Rate limiting on login and registration endpoints (e.g., 5 attempts per minute).

## Database Schema Extensions

### Table `password_reset_tokens`
- `id` INTEGER PRIMARY KEY
- `user_id` INTEGER NOT NULL REFERENCES users(id)
- `token_hash` TEXT NOT NULL
- `token_type` TEXT NOT NULL  -- 'registration' or 'reset'
- `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP
- `expires_at` TIMESTAMP NOT NULL
- `used` BOOLEAN DEFAULT 0

### Table `activity_logs` (already defined)
- Log authentication events: login success/failure, password change, account activation.

## Implementation Steps

1. Set up Flask‑Mail configuration.
2. Create token generation and validation utilities.
3. Implement registration, login, password‑reset views.
4. Create email templates.
5. Add decorators for role‑based access.
6. Write tests for authentication flows.

## Mermaid Sequence Diagram (Registration)

```mermaid
sequenceDiagram
    participant User
    participant Browser
    participant Server
    participant MailServer
    participant DB

    User->>Browser: Navigate to /register
    Browser->>Server: GET /register
    Server-->>Browser: Registration form
    User->>Browser: Fill email, submit
    Browser->>Server: POST /register
    Server->>DB: Check email domain & existence
    DB-->>Server: User not found
    Server->>DB: Create inactive user
    Server->>Server: Generate token
    Server->>DB: Store token hash
    Server->>MailServer: Send password‑setup email
    MailServer->>User: Email with link
    User->>Browser: Click link
    Browser->>Server: GET /reset‑password/<token>
    Server->>DB: Validate token
    DB-->>Server: Token valid
    Server-->>Browser: Password setup form
    User->>Browser: Enter password, submit
    Browser->>Server: POST /reset‑password/<token>
    Server->>DB: Update password, activate user, delete token
    Server-->>Browser: Redirect to dashboard