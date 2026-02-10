"""
Security module for the application.

This module provides security-related utilities including:
- Security headers middleware
- Rate limiting
- Input sanitization
- Session security
"""

import re
import html
from functools import wraps
from datetime import datetime, timedelta
from flask import request, g, session, current_app, make_response
from werkzeug.exceptions import TooManyRequests


class SecurityHeaders:
    """Security headers middleware for Flask applications."""
    
    def __init__(self, app=None):
        self.app = app
        if app is not None:
            self.init_app(app)
    
    def init_app(self, app):
        """Initialize the middleware with a Flask app."""
        app.after_request(self.add_security_headers)
    
    def add_security_headers(self, response):
        """Add security headers to all responses."""
        # Content Security Policy
        csp = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval' "
            "https://cdn.jsdelivr.net "
            "https://cdnjs.cloudflare.com; "
            "style-src 'self' 'unsafe-inline' "
            "https://cdn.jsdelivr.net "
            "https://cdnjs.cloudflare.com "
            "https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com https://cdn.jsdelivr.net; "
            "img-src 'self' data: https:; "
            "connect-src 'self'; "
            "frame-ancestors 'self'; "
            "base-uri 'self'; "
            "form-action 'self';"
        )
        response.headers['Content-Security-Policy'] = csp
        
        # Prevent MIME type sniffing
        response.headers['X-Content-Type-Options'] = 'nosniff'
        
        # Prevent clickjacking
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        
        # XSS Protection
        response.headers['X-XSS-Protection'] = '1; mode=block'
        
        # Referrer Policy
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        
        # Strict Transport Security (only in production)
        if not current_app.config.get('DEBUG', False):
            response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
        
        # Permissions Policy
        response.headers['Permissions-Policy'] = (
            'accelerometer=(), '
            'camera=(), '
            'geolocation=(), '
            'gyroscope=(), '
            'magnetometer=(), '
            'microphone=(), '
            'payment=(), '
            'usb=()'
        )
        
        return response


class RateLimiter:
    """Simple in-memory rate limiter for Flask applications."""
    
    def __init__(self, app=None):
        self.app = app
        self.storage = {}  # Simple in-memory storage
        if app is not None:
            self.init_app(app)
    
    def init_app(self, app):
        """Initialize the rate limiter with a Flask app."""
        pass
    
    def is_allowed(self, key, limit=5, window=900):
        """
        Check if a request is allowed based on rate limiting.
        
        Args:
            key: Unique identifier (e.g., IP + endpoint)
            limit: Maximum number of requests allowed
            window: Time window in seconds (default 15 minutes)
        
        Returns:
            tuple: (allowed: bool, remaining: int, reset_time: datetime)
        """
        now = datetime.utcnow()
        window_start = now - timedelta(seconds=window)
        
        # Clean old entries
        if key in self.storage:
            self.storage[key] = [
                ts for ts in self.storage[key] if ts > window_start
            ]
        else:
            self.storage[key] = []
        
        # Check if limit exceeded
        if len(self.storage[key]) >= limit:
            reset_time = self.storage[key][0] + timedelta(seconds=window)
            return False, 0, reset_time
        
        # Add current request
        self.storage[key].append(now)
        remaining = limit - len(self.storage[key])
        reset_time = now + timedelta(seconds=window)
        
        return True, remaining, reset_time
    
    def reset(self, key):
        """Reset rate limit for a key."""
        self.storage.pop(key, None)


# Global rate limiter instance
rate_limiter = RateLimiter()


def rate_limit(limit=5, window=900, key_func=None):
    """
    Decorator to apply rate limiting to a route.
    
    Args:
        limit: Maximum number of requests allowed
        window: Time window in seconds
        key_func: Function to generate the rate limit key (defaults to IP + endpoint)
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if key_func:
                key = key_func()
            else:
                key = f"{request.remote_addr}:{request.endpoint}"
            
            allowed, remaining, reset_time = rate_limiter.is_allowed(key, limit, window)
            
            if not allowed:
                response = make_response('Rate limit exceeded. Please try again later.', 429)
                response.headers['Retry-After'] = int((reset_time - datetime.utcnow()).total_seconds())
                response.headers['X-RateLimit-Limit'] = str(limit)
                response.headers['X-RateLimit-Remaining'] = '0'
                response.headers['X-RateLimit-Reset'] = reset_time.isoformat()
                return response
            
            # Add rate limit headers to successful response
            response = f(*args, **kwargs)
            if hasattr(response, 'headers'):
                response.headers['X-RateLimit-Limit'] = str(limit)
                response.headers['X-RateLimit-Remaining'] = str(remaining)
                response.headers['X-RateLimit-Reset'] = reset_time.isoformat()
            
            return response
        return decorated_function
    return decorator


def sanitize_input(text, max_length=None, allow_html=False):
    """
    Sanitize user input to prevent XSS attacks.
    
    Args:
        text: Input text to sanitize
        max_length: Maximum allowed length (truncates if exceeded)
        allow_html: If False, HTML tags are escaped
    
    Returns:
        Sanitized text
    """
    if text is None:
        return None
    
    if not isinstance(text, str):
        text = str(text)
    
    # Strip leading/trailing whitespace
    text = text.strip()
    
    # Escape HTML if not allowed
    if not allow_html:
        text = html.escape(text, quote=True)
    else:
        # Even when allowing HTML, sanitize potentially dangerous tags
        # This is a basic implementation - for production, consider bleach library
        dangerous_patterns = [
            r'<script[^>]*>.*?</script>',
            r'javascript:',
            r'on\w+\s*=',
            r'<iframe[^>]*>.*?</iframe>',
            r'<object[^>]*>.*?</object>',
            r'<embed[^>]*>.*?</embed>',
        ]
        for pattern in dangerous_patterns:
            text = re.sub(pattern, '', text, flags=re.IGNORECASE | re.DOTALL)
    
    # Truncate if max_length is specified
    if max_length and len(text) > max_length:
        text = text[:max_length]
    
    return text


def validate_email(email):
    """
    Validate email format.
    
    Args:
        email: Email address to validate
    
    Returns:
        tuple: (is_valid: bool, error_message: str or None)
    """
    if not email:
        return False, "Email is required"
    
    if len(email) > 254:
        return False, "Email is too long (max 254 characters)"
    
    # Basic email pattern
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not re.match(pattern, email):
        return False, "Invalid email format"
    
    return True, None


def validate_password(password, min_length=8):
    """
    Validate password strength.
    
    Args:
        password: Password to validate
        min_length: Minimum password length
    
    Returns:
        tuple: (is_valid: bool, error_message: str or None)
    """
    if not password:
        return False, "Password is required"
    
    if len(password) < min_length:
        return False, f"Password must be at least {min_length} characters long"
    
    if len(password) > 128:
        return False, "Password is too long (max 128 characters)"
    
    # Check for common weak patterns (optional, can be customized)
    common_weak_passwords = ['password', '12345678', 'qwerty123', 'admin123']
    if password.lower() in common_weak_passwords:
        return False, "Password is too common"
    
    return True, None


class InputValidator:
    """Input validation utilities."""
    
    # Maximum lengths for various fields
    MAX_LENGTHS = {
        'title': 200,
        'content': 10000,
        'comment': 2000,
        'name': 100,
        'email': 254,
        'ticker': 20,
        'company_name': 255,
        'sector': 255,
        'status': 50,
    }
    
    @classmethod
    def validate_length(cls, field_name, value, max_length=None):
        """
        Validate field length.
        
        Args:
            field_name: Name of the field (for error messages)
            value: Value to validate
            max_length: Maximum allowed length (uses defaults if not specified)
        
        Returns:
            tuple: (is_valid: bool, sanitized_value: str or None, error: str or None)
        """
        if value is None:
            return True, None, None
        
        if not isinstance(value, str):
            value = str(value)
        
        # Get max length from defaults or use provided value
        max_len = max_length or cls.MAX_LENGTHS.get(field_name, 1000)
        
        if len(value) > max_len:
            return False, None, f"{field_name} exceeds maximum length of {max_len} characters"
        
        return True, value.strip(), None
    
    @classmethod
    def sanitize_text(cls, text, field_name=None, allow_html=False):
        """
        Sanitize text input with length validation.
        
        Args:
            text: Text to sanitize
            field_name: Name of the field for length limits
            allow_html: Whether to allow HTML
        
        Returns:
            Sanitized text or None if invalid
        """
        if text is None:
            return None
        
        # First validate length
        is_valid, sanitized, error = cls.validate_length(field_name, text)
        if not is_valid:
            return None
        
        # Then sanitize
        return sanitize_input(sanitized, allow_html=allow_html)


def configure_session_security(app):
    """
    Configure secure session settings for Flask app.
    
    Args:
        app: Flask application instance
    """
    # Session cookie settings
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=24)
    
    # Secure flag only in production (requires HTTPS)
    if not app.config.get('DEBUG', False):
        app.config['SESSION_COOKIE_SECURE'] = True
    
    # CSRF cookie settings (if using Flask-WTF)
    app.config['WTF_CSRF_TIME_LIMIT'] = 3600  # 1 hour
    app.config['WTF_CSRF_SSL_STRICT'] = True


def init_security(app):
    """
    Initialize all security features for the Flask app.
    
    Args:
        app: Flask application instance
    """
    # Add security headers
    SecurityHeaders(app)
    
    # Configure session security
    configure_session_security(app)
    
    # Initialize rate limiter
    rate_limiter.init_app(app)
    
    # Log security initialization
    app.logger.info("Security features initialized")
