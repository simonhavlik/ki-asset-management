"""
WebFlow Integration Module

This module provides utilities for integrating Flask content with WebFlow-designed
site shells. It allows serving page body content separately from the WebFlow header/footer.

Usage:
1. Set WEBFLOW_SHELL_URL in environment to your WebFlow export URL
2. Use ?_embed=body query param to get only the body content for AJAX injection
3. Or set X-WebFlow-Mode header to 'body' for API-style access

WebFlow Integration Flow:
1. WebFlow hosts the main site shell (header, footer, navigation)
2. Flask serves page body content via AJAX or iframe injection
3. JavaScript on the WebFlow shell injects Flask content into the content area
"""

import os
import re
import hashlib
import hmac
import requests
from functools import wraps
from flask import request, jsonify, Response, current_app, g

WEBFLOW_SIGNATURE_HEADER = 'X-Webflow-Signature'
WEBFLOW_MODE_HEADER = 'X-Webflow-Mode'


def get_webflow_config():
    """Get WebFlow configuration from environment."""
    return {
        'shell_url': os.environ.get('WEBFLOW_SHELL_URL', '').rstrip('/'),
        'api_key': os.environ.get('WEBFLOW_API_KEY', ''),
        'site_id': os.environ.get('WEBFLOW_SITE_ID', ''),
        'signature_secret': os.environ.get('WEBFLOW_SIGNATURE_SECRET', ''),
        'cache_ttl': int(os.environ.get('WEBFLOW_CACHE_TTL', '3600')),
    }


def is_webflow_request():
    """
    Check if the current request is from WebFlow integration.

    Detection methods:
    1. Query parameter: ?_embed=body
    2. Header: X-Webflow-Mode: body
    3. Accept header containing 'text/html+webflow'
    """
    return (
        request.args.get('_embed') == 'body'
        or request.headers.get(WEBFLOW_MODE_HEADER) == 'body'
        or 'text/html+webflow' in request.headers.get('Accept', '')
    )


def should_serve_body_only():
    """
    Determine if we should serve body content only (for WebFlow integration).
    """
    config = get_webflow_config()

    if not config['shell_url']:
        return False

    return is_webflow_request()


def serve_body_only(content, status_code=200):
    """
    Wrap body content with minimal HTML for WebFlow iframe injection.

    Args:
        content: HTML string of the body content
        status_code: HTTP status code

    Returns:
        Flask Response with body-only HTML
    """
    wrapped = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Flask Body Content</title>
    <style>
        body {{ margin: 0; padding: 0; overflow-x: hidden; }}
        .flask-body-content {{ min-height: 100vh; }}
    </style>
</head>
<body class="flask-body-content">
{content}
</body>
</html>'''

    return Response(wrapped, status=status_code, mimetype='text/html')


def generate_csrf_token_for_webflow():
    """
    Generate a CSRF token for WebFlow requests.
    This allows WebFlow to make authenticated requests to Flask.
    """
    from flask_wtf.csrf import generate_csrf
    return generate_csrf()


def verify_webhook_signature(payload, signature, secret):
    """
    Verify WebFlow webhook signature for security.

    Args:
        payload: Raw request body
        signature: Signature from WebFlow header
        secret: Signature secret from environment

    Returns:
        bool: True if signature is valid
    """
    if not secret:
        return False

    expected = hmac.new(
        secret.encode('utf-8'),
        payload,
        hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(signature, expected)


def get_webflow_pages():
    """
    Fetch list of pages from WebFlow API.

    Requires WEBFLOW_API_KEY and WEBFLOW_SITE_ID to be set.

    Returns:
        list: List of WebFlow pages with their URLs
    """
    config = get_webflow_config()

    if not config['api_key'] or not config['site_id']:
        current_app.logger.warning('WebFlow API credentials not configured')
        return []

    try:
        response = requests.get(
            f'https://api.webflow.com/sites/{config["site_id"]}/pages',
            headers={
                'Authorization': f'Bearer {config["api_key"]}',
                'Accept': 'application/json',
            },
            timeout=10
        )
        response.raise_for_status()
        return response.json().get('items', [])
    except Exception as e:
        current_app.logger.error(f'Failed to fetch WebFlow pages: {e}')
        return []


def sync_webflow_pages():
    """
    Sync WebFlow page URLs to Flask routes for mapping.

    This creates a mapping between WebFlow URLs and Flask endpoints
    to enable proper content injection.

    Returns:
        dict: URL mapping for WebFlow pages
    """
    pages = get_webflow_pages()
    mapping = {}

    for page in pages:
        url = page.get('url', '')
        slug = page.get('slug', '')
        if url:
            mapping[url] = slug
            mapping[f'/{slug}'] = slug

    return mapping


class WebFlowIntegrator:
    """
    Main class for WebFlow integration functionality.
    """

    def __init__(self, app=None):
        self.app = app
        if app is not None:
            self.init_app(app)

    def init_app(self, app):
        """Initialize WebFlow integration with Flask app."""
        app.context_processor(self.inject_webflow_config)

    def inject_webflow_config(self):
        """Inject WebFlow configuration into template context."""
        config = get_webflow_config()
        return {
            'webflow_shell_url': config['shell_url'],
            'webflow_integration_enabled': bool(config['shell_url']),
        }

    def body_only_decorator(self, f):
        """
        Decorator to serve body content only for WebFlow integration.

        Usage:
            @app.route('/page')
            @webflow.body_only_decorator
            def page():
                return render_template('page.html')
        """
        @wraps(f)
        def decorated(*args, **kwargs):
            if should_serve_body_only():
                response = f(*args, **kwargs)
                if isinstance(response, Response):
                    return response
                return serve_body_only(response.get_data(as_text=True))
            return f(*args, **kwargs)
        return decorated

    def get_injection_script(self, endpoint_url):
        """
        Generate JavaScript for injecting Flask content into WebFlow shell.

        Args:
            endpoint_url: URL to fetch body content from

        Returns:
            str: HTML script tag with injection code
        """
        config = get_webflow_config()

        script = f'''
<script>
(function() {{
    const WEBFLOW_ENDPOINT = '{endpoint_url}';
    const WEBFLOW_SHELL_URL = '{config["shell_url"]}';
    const INJECTION_SELECTOR = '#flask-content-injection-point';
    const LOADING_CLASS = 'flask-loading';
    const ERROR_CLASS = 'flask-error';

    async function injectFlaskContent() {{
        try {{
            const response = await fetch(WEBFLOW_ENDPOINT + '?_embed=body');
            if (!response.ok) throw new Error('Failed to fetch content');

            const html = await response.text();
            const target = document.querySelector(INJECTION_SELECTOR);

            if (target) {{
                target.innerHTML = html;
                target.classList.remove(LOADING_CLASS);
                console.log('[WebFlow] Flask content injected successfully');
            }} else {{
                console.warn('[WebFlow] Injection point not found:', INJECTION_SELECTOR);
            }}
        }} catch (error) {{
            console.error('[WebFlow] Injection failed:', error);
            const target = document.querySelector(INJECTION_SELECTOR);
            if (target) {{
                target.classList.add(ERROR_CLASS);
            }}
        }}
    }}

    function init() {{
        if (document.readyState === 'loading') {{
            document.addEventListener('DOMContentLoaded', injectFlaskContent);
        }} else {{
            injectFlaskContent();
        }}
    }}

    init();
}})();
</script>
'''
        return script

    def get_error_page(self, error_type='general'):
        """
        Generate error HTML for WebFlow injection.

        Args:
            error_type: Type of error (general, 404, 500, etc.)

        Returns:
            str: Error HTML content
        """
        errors = {
            'general': '''
                <div class="flask-error-content" style="padding: 40px; text-align: center;">
                    <h2>Oops! Something went wrong</h2>
                    <p>We're having trouble loading this content.</p>
                    <button onclick="location.reload()" style="margin-top: 20px; padding: 10px 20px;">
                        Try Again
                    </button>
                </div>
            ''',
            '404': '''
                <div class="flask-404-content" style="padding: 40px; text-align: center;">
                    <h2>404 - Page Not Found</h2>
                    <p>The content you're looking for doesn't exist.</p>
                </div>
            ''',
            '500': '''
                <div class="flask-500-content" style="padding: 40px; text-align: center;">
                    <h2>500 - Server Error</h2>
                    <p>We're experiencing some issues. Please try again later.</p>
                </div>
            ''',
            'auth': '''
                <div class="flask-auth-required" style="padding: 40px; text-align: center;">
                    <h2>Authentication Required</h2>
                    <p>Please log in to access this content.</p>
                    <a href="/auth/login" style="display: inline-block; margin-top: 20px; padding: 10px 20px; background: #0066cc; color: white; text-decoration: none; border-radius: 4px;">
                        Log In
                    </a>
                </div>
            ''',
        }
        return errors.get(error_type, errors['general'])


webflow_integration = WebFlowIntegrator()
