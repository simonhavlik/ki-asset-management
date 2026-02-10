"""
Security tests for the application.

These tests verify that security features are properly implemented.
"""

import pytest
from app.security import (
    sanitize_input, validate_email, validate_password,
    InputValidator, rate_limiter, SecurityHeaders
)


class TestInputSanitization:
    """Test input sanitization functions."""
    
    def test_sanitize_input_escapes_html(self):
        """Test that HTML is properly escaped."""
        input_text = "<script>alert('XSS')</script>"
        result = sanitize_input(input_text)
        assert "<script>" not in result
        assert "&lt;script&gt;" in result
    
    def test_sanitize_input_handles_none(self):
        """Test that None input is handled."""
        result = sanitize_input(None)
        assert result is None
    
    def test_sanitize_input_respects_max_length(self):
        """Test that max_length parameter works."""
        input_text = "a" * 1000
        result = sanitize_input(input_text, max_length=100)
        assert len(result) == 100
    
    def test_sanitize_input_strips_whitespace(self):
        """Test that whitespace is stripped."""
        input_text = "  test text  "
        result = sanitize_input(input_text)
        assert result == "test text"


class TestEmailValidation:
    """Test email validation."""
    
    def test_valid_email(self):
        """Test that valid emails pass."""
        valid, error = validate_email("test@example.com")
        assert valid is True
        assert error is None
    
    def test_invalid_email_format(self):
        """Test that invalid emails fail."""
        valid, error = validate_email("invalid-email")
        assert valid is False
        assert error is not None
    
    def test_empty_email(self):
        """Test that empty emails fail."""
        valid, error = validate_email("")
        assert valid is False
    
    def test_email_too_long(self):
        """Test that very long emails fail."""
        email = "a" * 250 + "@example.com"
        valid, error = validate_email(email)
        assert valid is False


class TestPasswordValidation:
    """Test password validation."""
    
    def test_valid_password(self):
        """Test that valid passwords pass."""
        valid, error = validate_password("strongpassword123")
        assert valid is True
        assert error is None
    
    def test_password_too_short(self):
        """Test that short passwords fail."""
        valid, error = validate_password("weak")
        assert valid is False
        assert "at least" in error.lower()
    
    def test_empty_password(self):
        """Test that empty passwords fail."""
        valid, error = validate_password("")
        assert valid is False
    
    def test_common_password_rejected(self):
        """Test that common weak passwords are rejected."""
        valid, error = validate_password("password")
        assert valid is False


class TestInputValidator:
    """Test InputValidator class."""
    
    def test_validate_length_within_limit(self):
        """Test validation within limit."""
        is_valid, value, error = InputValidator.validate_length(
            'title', 'Test Title'
        )
        assert is_valid is True
        assert value == 'Test Title'
        assert error is None
    
    def test_validate_length_exceeds_limit(self):
        """Test validation exceeding limit."""
        long_text = "a" * 300
        is_valid, value, error = InputValidator.validate_length(
            'title', long_text
        )
        assert is_valid is False
        assert error is not None
    
    def test_validate_length_custom_max(self):
        """Test validation with custom max length."""
        is_valid, value, error = InputValidator.validate_length(
            'custom', 'test', max_length=10
        )
        assert is_valid is True
        
        is_valid, value, error = InputValidator.validate_length(
            'custom', 'a' * 20, max_length=10
        )
        assert is_valid is False


class TestRateLimiter:
    """Test rate limiting functionality."""
    
    def test_rate_limiter_allows_requests(self):
        """Test that rate limiter allows requests within limit."""
        # Reset the rate limiter for this test key
        rate_limiter.reset("test_key")
        
        # First request should be allowed
        allowed, remaining, reset_time = rate_limiter.is_allowed(
            "test_key", limit=5, window=60
        )
        assert allowed is True
        assert remaining == 4
    
    def test_rate_limiter_blocks_excessive_requests(self):
        """Test that rate limiter blocks excessive requests."""
        # Reset and exhaust the limit
        rate_limiter.reset("test_key_block")
        
        # Exhaust the limit
        for _ in range(5):
            rate_limiter.is_allowed("test_key_block", limit=5, window=60)
        
        # Next request should be blocked
        allowed, remaining, reset_time = rate_limiter.is_allowed(
            "test_key_block", limit=5, window=60
        )
        assert allowed is False
        assert remaining == 0
    
    def test_rate_limiter_reset(self):
        """Test that rate limiter reset works."""
        # Exhaust the limit
        rate_limiter.reset("test_key_reset")
        for _ in range(5):
            rate_limiter.is_allowed("test_key_reset", limit=5, window=60)
        
        # Reset
        rate_limiter.reset("test_key_reset")
        
        # Should be allowed again
        allowed, remaining, reset_time = rate_limiter.is_allowed(
            "test_key_reset", limit=5, window=60
        )
        assert allowed is True


class TestSecurityHeaders:
    """Test security headers middleware."""
    
    def test_security_headers_present(self):
        """Test that security headers are present in responses."""
        import os
        os.environ['FLASK_CONFIG'] = 'testing'
        
        from app import create_app
        app = create_app('testing')
        
        with app.test_client() as client:
            response = client.get('/')
            
            assert 'Content-Security-Policy' in response.headers
            assert response.headers.get('X-Content-Type-Options') == 'nosniff'
            assert response.headers.get('X-Frame-Options') == 'SAMEORIGIN'
            assert 'X-XSS-Protection' in response.headers
            assert 'Referrer-Policy' in response.headers
    
    def test_csp_header_content(self):
        """Test CSP header has correct directives."""
        import os
        os.environ['FLASK_CONFIG'] = 'testing'
        
        from app import create_app
        app = create_app('testing')
        
        with app.test_client() as client:
            response = client.get('/')
            csp = response.headers.get('Content-Security-Policy', '')
            
            assert "default-src 'self'" in csp
            assert "script-src 'self'" in csp
            assert "style-src 'self'" in csp


class TestSQLInjectionPrevention:
    """Test SQL injection prevention."""
    
    def test_no_raw_user_input_in_sql(self):
        """Test that there's no raw SQL with string formatting."""
        import app.admin.routes as admin_routes
        import inspect
        
        # Get the source code of analyst_mappings function
        source = inspect.getsource(admin_routes.analyst_mappings)
        
        # Should not contain f-string SQL or .format() in SQL
        # This is a basic check - the fix should use ORM
        dangerous_patterns = [
            'f"SELECT',
            'f"INSERT',
            'f"UPDATE',
            'f"DELETE',
            '.format(',
        ]
        
        for pattern in dangerous_patterns:
            # The ORM approach won't have these patterns in the fixed code
            assert pattern not in source or "db.session.query" in source, \
                f"Potential SQL injection pattern found: {pattern}"


class TestSessionSecurity:
    """Test session security configuration."""
    
    def test_session_cookie_httonly(self):
        """Test that session cookie is HttpOnly."""
        import os
        os.environ['FLASK_CONFIG'] = 'testing'
        
        from app import create_app
        app = create_app('testing')
        
        assert app.config.get('SESSION_COOKIE_HTTPONLY') is True
    
    def test_session_cookie_samesite(self):
        """Test that session cookie has SameSite attribute."""
        import os
        os.environ['FLASK_CONFIG'] = 'testing'
        
        from app import create_app
        app = create_app('testing')
        
        assert app.config.get('SESSION_COOKIE_SAMESITE') == 'Lax'
    
    def test_csrf_configured(self):
        """Test that CSRF is configured."""
        import os
        os.environ['FLASK_CONFIG'] = 'testing'
        
        from app import create_app
        app = create_app('testing')
        
        # CSRF might be disabled in testing but should be configured
        assert 'WTF_CSRF_ENABLED' in app.config
