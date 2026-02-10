# WebFlow Integration Guide

**Goal:** Show Flask content inside your WebFlow site.

---

## The Core Problem

WebFlow shows static pages. Flask shows dynamic pages. You want Flask content inside WebFlow.

**Solution:** JavaScript fetches Flask content and puts it in a WebFlow element.

---

## Step 1: Add This to Your WebFlow Page

Go to your WebFlow page and add:

```html
<!-- Where Flask content will appear -->
<div id="flask-content-injection-point"></div>

<!-- JavaScript to fetch and inject Flask content -->
<script>
(function() {
    const FLASK_URL = 'http://localhost:5000';  // CHANGE THIS
    const path = window.location.pathname.replace(/^\//, '') || 'home';
    const url = `${FLASK_URL}/${path}?_embed=body`;

    fetch(url)
        .then(r => r.text())
        .then(html => {
            document.getElementById('flask-content-injection-point').innerHTML = html;
        })
        .catch(err => console.error('Flask error:', err));
})();
</script>
```

**Change `FLASK_URL`** to your actual Flask URL:
- Local: `http://localhost:5000`
- Production: `https://your-app.onrender.com`

---

## Step 2: Test Flask Body-Only Mode

Visit your Flask URL with `?_embed=body`:

```bash
curl https://your-app.onrender.com/?_embed=body
```

You should see HTML **without** `<html>`, `<head>`, `<body>` tags - just the content.

---

## Step 3: Configure Flask (Optional)

If you want Flask to know your WebFlow URL, add to `.env`:

```bash
WEBFLOW_SHELL_URL=https://your-webflow-site.com
```

---

## How It Works

1. User visits WebFlow page
2. JavaScript calls Flask: `/page?_embed=body`
3. Flask returns just the body HTML
4. JavaScript puts it in `<div id="flask-content-injection-point">`

---

## WebFlow Free Tier

**Free tier cannot add custom JavaScript.** Options:

1. **Export to static HTML** (free, then host anywhere)
2. **Upgrade to paid WebFlow plan** ($14+/mo)
3. **Host WebFlow design on another service** (Netlify, Vercel, etc.)

---

## Troubleshooting

**Content not showing?**
1. Check browser console (F12) for errors
2. Verify `FLASK_URL` is correct
3. Test Flask directly: `curl https://your-app.com/?_embed=body`

**CORS error?**
- Flask and WebFlow must use same protocol (both HTTPS or both HTTP)

---

## Files Created

| File | Purpose |
|------|---------|
| `app/webflow_integration.py` | Flask integration code |
| `app/routes_webflow.py` | Route helpers |
| `app/templates/webflow_shell.html` | Shell template for testing |
| `app/static/css/webflow-reset.css` | Shell styles |
