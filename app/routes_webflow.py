"""
WebFlow Route Helpers

This module provides decorators and utilities for Flask routes to support
both standalone and WebFlow integration modes.

Usage:
    from .routes_webflow import webflow_body_only

    @app.route('/page')
    @webflow_body_only
    def page():
        return render_template('page.html')
"""

from functools import wraps
from flask import request, current_app, Response
from .webflow_integration import (
    should_serve_body_only,
    serve_body_only,
    is_webflow_request
)


def webflow_body_only(template_name=None):
    """
    Decorator to serve body content only when requested by WebFlow.

    Args:
        template_name: Optional template to render (defaults to endpoint name)

    Usage:
        @app.route('/about')
        @webflow_body_only('about.html')
        def about():
            return render_template('about.html')

        @app.route('/dashboard')
        @webflow_body_only
        def dashboard():
            return render_template('dashboard.html', user=current_user)
    """
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if should_serve_body_only():
                # Check if user is authenticated for protected routes
                from flask_login import current_user
                if hasattr(current_user, 'is_authenticated') and not current_user.is_authenticated:
                    # Return auth required message
                    error_html = '''
                    <div class="auth-required" style="padding: 40px; text-align: center;">
                        <h2>Authentication Required</h2>
                        <p>Please log in to access this content.</p>
                        <a href="/auth/login" style="display: inline-block; margin-top: 20px; padding: 10px 20px; background: #0066cc; color: white; text-decoration: none; border-radius: 4px;">
                            Log In
                        </a>
                    </div>
                    '''
                    return Response(error_html, status=401, mimetype='text/html')

                # Render the template
                response = f(*args, **kwargs)

                # Handle different response types
                if isinstance(response, Response):
                    return response

                # Get HTML content
                html_content = response if isinstance(response, str) else response.get_data(as_text=True)

                return serve_body_only(html_content)

            # Normal mode - return full page
            return f(*args, **kwargs)
        return decorated
    return decorator


def webflow_aware_render(template_name, **context):
    """
    Render a template that adapts to WebFlow integration mode.

    When serving body-only mode, wraps content in minimal HTML.
    Otherwise renders full page with base template.

    Args:
        template_name: Path to template file
        **context: Template variables

    Returns:
        Flask Response with appropriate HTML
    """
    from flask import render_template

    if should_serve_body_only():
        # Render just the template content
        html = render_template(template_name, **context)
        return serve_body_only(html)
    else:
        # Render full page
        return render_template(template_name, **context)


class WebFlowRouteMixin:
    """
    Mixin class for Flask route handlers that support WebFlow integration.

    Subclass your route handlers with this mixin to add WebFlow support:

        from .routes_webflow import WebFlowRouteMixin

        class MyRoutes(WebFlowRouteMixin):
            @app.route('/custom')
            def custom_page(self):
                return self.webflow_render('custom.html')
    """

    def webflow_render(self, template, **kwargs):
        """
        Render a template with WebFlow awareness.

        Args:
            template: Template path
            **kwargs: Template variables

        Returns:
            Full page or body-only HTML depending on request mode
        """
        from flask import render_template

        if should_serve_body_only():
            html = render_template(template, **kwargs)
            return serve_body_only(html)
        return render_template(template, **kwargs)

    def get_page_data(self):
        """
        Get common page data for WebFlow integration.

        Returns:
            dict with common template variables
        """
        from flask_login import current_user
        from datetime import datetime

        return {
            'now': datetime.utcnow(),
            'current_user': current_user if hasattr(current_user, 'is_authenticated') and current_user.is_authenticated else None,
            'is_webflow_request': is_webflow_request(),
        }


def create_api_endpoint_for_content(endpoint_name, template, requires_auth=False):
    """
    Factory function to create API endpoints that serve page content.

    Args:
        endpoint_name: Name for the endpoint
        template: Template to render
        requires_auth: Whether login is required

    Returns:
        Flask route function
    """
    from flask import render_template
    from flask_login import login_required, current_user

    def endpoint():
        if requires_auth and not (hasattr(current_user, 'is_authenticated') and current_user.is_authenticated):
            return Response('''
                <div class="auth-required" style="padding: 40px; text-align: center;">
                    <h2>Authentication Required</h2>
                    <p>Please log in to access this content.</p>
                </div>
            ''', status=401, mimetype='text/html')

        html = render_template(template)
        return serve_body_only(html)

    endpoint.__name__ = endpoint_name
    return endpoint
