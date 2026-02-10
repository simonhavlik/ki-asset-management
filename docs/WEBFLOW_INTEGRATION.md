# WebFlow Integration Guide

This document explains how to connect your Flask application to a WebFlow-designed website. You will design the site in WebFlow, and Flask will provide the dynamic content (blog posts, dashboards, etc.) that gets injected into your WebFlow pages.

## Table of Contents

1. [What This Does](#what-this-does)
2. [Before You Start](#before-you-start)
3. [Step 1: Create Your WebFlow Site](#step-1-create-your-webflow-site)
4. [Step 2: Add the Injection Container](#step-2-add-the-injection-container)
5. [Step 3: Add the JavaScript Code](#step-3-add-the-javascript-code)
6. [Step 4: Configure Flask](#step-4-configure-flask)
7. [Step 5: Test It Works](#step-5-test-it-works)
8. [URL Mapping](#url-mapping)
9. [Troubleshooting](#troubleshooting)

---

## What This Does

Imagine your website has:

- **Header** (logo, navigation menu) - Designed in WebFlow
- **Footer** (links, copyright) - Designed in WebFlow
- **Main Content** - Comes from Flask!

When someone visits your site:
1. WebFlow loads the header and footer
2. JavaScript asks Flask for the page content
3. Flask returns just the body HTML
4. JavaScript puts Flask's content into the middle section

This way you get the best of both:
- WebFlow's easy design tools for the static parts
- Flask's power for dynamic content (dashboards, user areas, blogs)

---

## Before You Start

Make sure you have:

- [ ] A WebFlow account (free tier works)
- [ ] Your Flask app running somewhere (local or deployed)
- [ ] Access to edit your WebFlow site's HTML

---

## Step 1: Create Your WebFlow Site

### 1.1 Create a New Project

1. Go to [WebFlow](https://webflow.com) and log in
2. Click **"Create New Project"**
3. Choose **"Blank Site"** (start clean)
4. Name it (e.g., "KI Asset Management")
5. Click **"Create Project"**

### 1.2 Design Your Pages

Design your pages in WebFlow's Designer:

1. **Home Page** (/)
2. Any other pages you want to include

Use WebFlow's drag-and-drop to design each page.

---

## Step 2: Add the Injection Container

This is the most important step. You need to add a special HTML element where Flask content will appear.

### 2.1 Open Your Page Settings

1. In WebFlow Designer, click the **"Pages"** icon in the left sidebar
2. Select the page you want to edit (e.g., Home)

### 2.2 Add the Container Element

1. In the **Elements** panel, drag a **"Div Block"** onto your page
2. Place it where you want Flask content to appear (usually below the hero section)
3. With the div selected, go to the **"Settings"** panel (right side)
4. In the **"Element Tag"** field, change it to: `div`
5. In the **"Class Name"** field, add: `flask-content`

### 2.3 Add the ID

**This is critical - the ID must match exactly:**

1. In the **"Settings"** panel, find the **"ID"** field
2. Enter exactly: `flask-content-injection-point`
3. Press Enter to save

Your element should look like:

```
<div id="flask-content-injection-point" class="flask-content">
    <!-- Flask content will appear here -->
</div>
```

### 2.4 Repeat for All Pages

Do this for every page that will have Flask content.

---

## Step 3: Add the JavaScript Code

This JavaScript code fetches Flask content and puts it into your injection container.

### 3.1 Open Page Settings

1. In WebFlow Designer, click the **"Pages"** icon
2. Select your page (start with Home)

### 3.2 Add a Script Element

1. From the **Elements** panel, drag a **"Script"** element
2. Place it at the bottom of your page (just before `</body>`)
3. Double-click the script element to edit it
4. Paste this code:

```html
<script>
(function() {
    'use strict';

    // CONFIGURATION - Change this to YOUR Flask URL
    const FLASK_URL = 'http://localhost:5000';

    // Get the current page path
    function getPagePath() {
        const path = window.location.pathname;
        // Remove leading slash and convert to Flask route name
        // /about -> about
        // / -> home
        // /blog/post/123 -> blog
        let cleanPath = path.replace(/^\//, '').split('/')[0];
        if (!cleanPath || cleanPath === '') {
            cleanPath = 'home';
        }
        return cleanPath;
    }

    // Fetch content from Flask
    async function fetchFlaskContent() {
        const page = getPagePath();
        const url = `${FLASK_URL}/${page}?_embed=body`;

        console.log('Fetching from:', url);

        try {
            const response = await fetch(url, {
                method: 'GET',
                headers: {
                    'Accept': 'text/html'
                }
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const html = await response.text();
            return html;
        } catch (error) {
            console.error('Failed to fetch Flask content:', error);
            return null;
        }
    }

    // Put content into the page
    function injectContent(html) {
        const container = document.getElementById('flask-content-injection-point');

        if (!container) {
            console.error('Could not find element: #flask-content-injection-point');
            return false;
        }

        // Clear loading state if it exists
        container.innerHTML = html;
        console.log('Content injected successfully');
        return true;
    }

    // Initialize
    async function init() {
        const html = await fetchFlaskContent();
        if (html) {
            injectContent(html);
        }
    }

    // Run when page loads
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    // Handle browser back/forward buttons
    window.addEventListener('popstate', () => {
        const container = document.getElementById('flask-content-injection-point');
        if (container) {
            container.innerHTML = '<p>Loading...</p>';
            init();
        }
    });

})();
</script>
```

### 3.3 Configure the Flask URL

In the code above, find this line:

```javascript
const FLASK_URL = 'http://localhost:5000';
```

Change `http://localhost:5000` to your actual Flask URL:

- **Local development:** `http://localhost:5000`
- **Production:** `https://your-production-app.com`

### 3.4 Repeat for All Pages

Add this script to every page that has the injection container.

---

## URL Mapping

Map your WebFlow URLs to Flask routes:

| WebFlow URL | Flask Route |
|-------------|-------------|
| `/` | `/` (home) |
| `/your-page` | `/your-page` |

The JavaScript automatically converts WebFlow URLs to Flask routes.

---

## Step 4: Configure Flask

### 4.1 Set Environment Variable

Open your `.env` file and add:

```bash
# WebFlow Integration
WEBFLOW_SHELL_URL=https://your-webflow-site.webflow.io
```

Replace the URL with your actual WebFlow site URL.

### 4.2 Test the Configuration

Run Flask and visit:

```
http://localhost:5000/about?_embed=body
```

You should see just HTML body content (no header/footer), not a full page.

---

## Step 5: Test It Works

### 5.1 Local Testing

1. **Start Flask:**
   ```bash
   source venv/bin/activate
   flask run
   ```

2. **Start WebFlow Preview:**
   - In WebFlow Designer, click the **"Preview"** button (top right)
   - Or publish to WebFlow's staging URL

3. **Check the Console:**
   - Open browser DevTools (F12)
   - Go to Console tab
   - Look for messages like:
     - `Fetching from: http://localhost:5000/about?_embed=body`
     - `Content injected successfully`

### 5.2 Test Individual Endpoints

Visit these URLs directly in your browser:

| URL | What You Should See |
|-----|---------------------|
| `http://localhost:5000/?_embed=body` | Just the home page content |
| `http://localhost:5000/about?_embed=body` | Just the about page content |
| `http://localhost:5000/strategy?_embed=body` | Just the strategy page content |
| `http://localhost:5000/blog?_embed=body` | Just the blog content |

---

## Troubleshooting

### Content Not Appearing

**Problem:** The Flask content doesn't show up on the page.

**Solutions:**

1. **Check the element ID:**
   ```javascript
   // In browser console
   document.getElementById('flask-content-injection-point')
   ```
   If this returns `null`, the ID is wrong.

2. **Check for JavaScript errors:**
   - Open DevTools (F12)
   - Go to Console
   - Look for red error messages

3. **Check the network request:**
   - In DevTools, go to **Network** tab
   - Refresh the page
   - Look for a request to Flask
   - Check if it returns 200 OK

4. **Verify Flask is running:**
   ```bash
   curl http://localhost:5000/about?_embed=body
   ```
   Should return HTML body content.

---

### Wrong Content Appearing

**Problem:** Flask is showing the wrong page.

**Solutions:**

1. **Check the URL mapping:**
   ```javascript
   function getPagePath() {
       console.log('Path:', window.location.pathname);
       // ...
   }
   ```

2. **Verify the Flask URL:**
   Make sure `FLASK_URL` points to the correct server.

---

### Styles Not Applied

**Problem:** Flask content looks unstyled.

**Solutions:**

1. **Check CSS loading:**
   - Flask content should inherit page styles
   - Add this to your WebFlow CSS:
   ```css
   #flask-content-injection-point {
       all: initial;
   }
   ```

2. **Check for CSS conflicts:**
   - Flask templates might have their own CSS
   - WebFlow might override it

---

### Authentication Issues

**Problem:** Protected routes (like dashboard) show errors.

**Solutions:**

1. **Authentication is required:**
   - The user must be logged into Flask
   - Check Flask's login system

2. **Session sharing:**
   - WebFlow and Flask share sessions via cookies
   - Make sure cookies are working

---

### Mixed Content Errors

**Problem:** Browser shows "Mixed Content" warning.

**Solutions:**

This happens when:
- WebFlow is on HTTPS
- Flask is on HTTP

**Fix:** Use HTTPS for Flask in production.

---

### CORS Errors

**Problem:** `Access-Control-Allow-Origin` error.

**Solutions:**

Flask needs to allow requests from your WebFlow domain:

```python
from flask_cors import CORS

CORS(app, origins=['https://your-webflow-site.webflow.io'])
```

---

## Advanced Configuration

### Custom Loading State

Add a loading spinner while content loads:

```javascript
// In your injection container
<div id="flask-content-injection-point">
    <div class="flask-loading">
        <p>Loading content...</p>
        <style>
            .flask-loading {
                text-align: center;
                padding: 40px;
            }
            .flask-loading::after {
                content: '';
                display: block;
                width: 40px;
                height: 40px;
                margin: 20px auto;
                border: 3px solid #ddd;
                border-top-color: #333;
                border-radius: 50%;
                animation: spin 1s linear infinite;
            }
            @keyframes spin {
                to { transform: rotate(360deg); }
            }
        </style>
    </div>
</div>
```

### Error Handling

Show an error message if Flask is down:

```javascript
async function fetchFlaskContent() {
    const page = getPagePath();
    const url = `${FLASK_URL}/${page}?_embed=body`;

    try {
        const response = await fetch(url);
        if (!response.ok) throw new Error('Failed to load');
        return await response.text();
    } catch (error) {
        // Return error HTML
        return `
            <div style="padding: 40px; text-align: center;">
                <h2>Unable to load content</h2>
                <p>Please refresh the page to try again.</p>
            </div>
        `;
    }
}
```

---

## Publishing to Production

### 1. Deploy Flask

Deploy your Flask app to a production server (Render, Heroku, Railway, etc.)

### 2. Update WebFlow Script

Change the Flask URL from local to production:

```javascript
const FLASK_URL = 'https://your-production-app.com';
```

### 3. Publish WebFlow

1. In WebFlow Designer, click **"Publish"**
2. Choose where to publish (WebFlow.io, custom domain)
3. Click **"Publish"**

### 4. Test Production

Visit your live site and verify:
- [ ] Content loads correctly
- [ ] Navigation works
- [ ] Console has no errors

---

## Need Help?

If something's not working:

1. **Check browser console** for error messages
2. **Check Network tab** to see if Flask requests succeed
3. **Test Flask directly** by visiting `?_embed=body` URLs
4. **Verify your element ID** matches exactly: `flask-content-injection-point`

---

## File Reference

| File | Purpose |
|------|---------|
| `app/webflow_integration.py` | Core Flask integration code |
| `app/routes_webflow.py` | Route decorators for WebFlow |
| `app/templates/webflow_shell.html` | Complete shell template |
| `app/static/css/webflow-reset.css` | Shell styles |
| `docs/WEBFLOW_INTEGRATION.md` | This documentation |
