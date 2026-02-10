# WebFlow Integration Guide

This document explains how to integrate the Flask-based Analyst Website with WebFlow-designed site shells.

## Overview

The integration allows you to:
- Design the site header, navigation, footer, and overall layout in WebFlow
- Use Flask for dynamic content (dashboards, analytics, authenticated user areas)
- Inject Flask content into WebFlow pages via JavaScript
- Maintain both standalone Flask mode and WebFlow-integrated mode

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     WebFlow Hosted Site                         │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Header/Nav (WebFlow)                                   │   │
│  ├─────────────────────────────────────────────────────────┤   │
│  │                                                         │   │
│  │  <div id="flask-content-injection-point">              │   │
│  │    <!-- Flask content injected here via AJAX -->        │   │
│  │  </div>                                                 │   │
│  │                                                         │   │
│  ├─────────────────────────────────────────────────────────┤   │
│  │  Footer (WebFlow)                                       │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                   │
│                              ▼ AJAX                             │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    Flask Application                    │   │
│  │  /page?_embed=body  →  Returns HTML body only          │   │
│  │  /dashboard?_embed=body  →  Dashboard content          │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

## Quick Start

### 1. Set Environment Variables

Add to your `.env` file:

```bash
# WebFlow Integration Settings
WEBFLOW_SHELL_URL=https://your-site.webflow.io
# Optional: API credentials for syncing pages
WEBFLOW_API_KEY=your_api_key_here
WEBFLOW_SITE_ID=your_site_id_here
WEBFLOW_SIGNATURE_SECRET=your_webhook_secret
```

### 2. Design WebFlow Site

Create your WebFlow site with:

1. **Navigation**: Links to `/`, `/about`, `/strategy`, `/blog`, `/dashboard`
2. **Content Area**: Add a div with `id="flask-content-injection-point"`
3. **Export**: Export to static HTML

### 3. Add Injection Script

Add this to your WebFlow exported HTML before `</body>`:

```html
<script>
(function() {
    const CONFIG = {
        baseUrl: 'https://your-flask-app.com',
        injectionSelector: '#flask-content-injection-point'
    };

    async function init() {
        const path = window.location.pathname.replace('/', '') || '';
        const endpoint = CONFIG.baseUrl + path + '?_embed=body';

        try {
            const response = await fetch(endpoint);
            if (!response.ok) throw new Error('Failed to fetch');
            const html = await response.text();

            const container = document.querySelector(CONFIG.injectionSelector);
            if (container) {
                container.innerHTML = html;
                console.log('[WebFlow] Content injected');
            }
        } catch (error) {
            console.error('[WebFlow] Error:', error);
        }
    }

    init();
})();
</script>
```

## Usage Modes

### Mode 1: Standalone Flask (Default)

访问页面 normally - Flask serves full HTML:

```bash
# Normal access
curl https://your-app.com/dashboard
# Returns: Full HTML page with header, body, footer
```

### Mode 2: WebFlow Integration

访问 with `?_embed=body` - Flask serves body only:

```bash
# WebFlow integration access
curl https://your-app.com/dashboard?_embed=body
# Returns: Body HTML only (no header/footer)
```

### Mode 3: Header Detection

Set Accept header for automatic detection:

```bash
curl -H "Accept: text/html+webflow" https://your-app.com/dashboard
# Returns: Body HTML only
```

## API Reference

### `webflow_integration.py`

Main module for WebFlow integration functionality.

#### `should_serve_body_only()`

Check if current request should receive body-only content.

```python
from app.webflow_integration import should_serve_body_only

if should_serve_body_only():
    # Serve body-only HTML
    return render_template('body_only.html')
```

#### `serve_body_only(content)`

Wrap content in minimal HTML for iframe injection.

```python
from app.webflow_integration import serve_body_only

html = render_template('content.html')
return serve_body_only(html)
```

#### `@webflow_body_only` Decorator

Decorator to make routes WebFlow-aware.

```python
from app.routes_webflow import webflow_body_only

@app.route('/dashboard')
@webflow_body_only
def dashboard():
    return render_template('dashboard.html')
```

### `routes_webflow.py`

Helpers for creating WebFlow-compatible routes.

#### `webflow_aware_render()`

Render templates that adapt to WebFlow mode.

```python
from app.routes_webflow import webflow_aware_render

@app.route('/page')
def page():
    return webflow_aware_render('page.html', title='My Page')
```

#### `WebFlowRouteMixin`

Mixin class for route handlers.

```python
from app.routes_webflow import WebFlowRouteMixin

class MyRoutes(WebFlowRouteMixin):
    @app.route('/custom')
    def custom_page(self):
        return self.webflow_render('custom.html')
```

## WebFlow Shell Template

A ready-to-use WebFlow shell template is available at:

```
app/templates/webflow_shell.html
```

This template includes:
- Responsive navigation with authentication states
- Content injection point
- Footer with links
- JavaScript for fetching Flask content
- CSRF token support for AJAX requests

## Testing

### Test Standalone Mode

```bash
source venv/bin/activate
flask run

# Visit http://localhost:5000 - Full page
```

### Test WebFlow Integration

```bash
# Visit with query parameter
curl http://localhost:5000/dashboard?_embed=body
# Returns: Body-only HTML

# Or set Accept header
curl -H "Accept: text/html+webflow" http://localhost:5000/dashboard
# Returns: Body-only HTML
```

### Test WebFlow Shell

```bash
# Visit the shell template directly
curl http://localhost:5000/webflow-shell
# Returns: Full shell with Flask content injection
```

## Security

### CSRF Protection

Flask-WTF CSRF tokens are included in the shell template:

```javascript
window.FLASK_CONFIG = {
    csrfToken: '{{ csrf_token() }}',
    // ...
};
```

Include CSRF in AJAX requests:

```javascript
fetch('/api/endpoint', {
    method: 'POST',
    headers: {
        'X-CSRFToken': window.FLASK_CONFIG.csrfToken
    },
    body: formData
});
```

### Webhook Verification

Verify WebFlow webhook signatures:

```python
from app.webflow_integration import verify_webhook_signature

@app.route('/webflow-webhook', methods=['POST'])
def webflow_webhook():
    signature = request.headers.get('X-Webflow-Signature')
    if not verify_webflow_signature(request.data, signature, secret):
        return {'error': 'Invalid signature'}, 401
    # Process webhook...
```

## URL Mapping

Flask routes can map to WebFlow pages:

| WebFlow URL | Flask Endpoint |
|-------------|----------------|
| `/about` | `/about` |
| `/strategy` | `/strategy` |
| `/blog` | `/blog` |
| `/dashboard` | `/dashboard` |
| `/analyst/*` | `/analyst/*` |

## Troubleshooting

### Content Not Injecting

1. Check browser console for errors
2. Verify `?_embed=body` parameter is being sent
3. Ensure `injectionSelector` matches WebFlow div ID
4. Check Flask is running and accessible

### Missing Styles

Styles from Flask templates may need adjustment:

```css
/* Add to your WebFlow custom CSS */
.flask-content {
    /* Ensure Flask content inherits styles */
}
```

### JavaScript Not Working

Flask-rendered JavaScript in body-only mode:

```javascript
// Initialize after injection
window.addEventListener('flask-content-injected', () => {
    // Your initialization code
});
```

## Production Deployment

### Environment Variables

```bash
WEBFLOW_SHELL_URL=https://your-production-webflow-site.com
WEBFLOW_API_KEY=production_api_key
WEBFLOW_SIGNATURE_SECRET=production_webhook_secret
```

### Caching

The integration supports response caching:

```python
from flask import cache

@app.route('/page')
@cache.cached(timeout=3600, query_string=True)
def page():
    return render_template('page.html')
```

### CDN Integration

Serve WebFlow static assets via CDN:

```html
<!-- In WebFlow export -->
<link rel="stylesheet" href="https://cdn.your-cdn.com/webflow-styles.css">
<script src="https://cdn.your-cdn.com/webflow-scripts.js"></script>
```

## Contributing

To extend the integration:

1. Add new decorators in `routes_webflow.py`
2. Update shell template in `templates/webflow_shell.html`
3. Add tests in `tests/test_webflow_integration.py`
4. Update this documentation

## License

Part of the Analyst Website project. See LICENSE file.
