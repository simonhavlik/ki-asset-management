# WebFlow Integration Guide

**Goal:** Show Flask content inside your WebFlow site.

---

## The Problem

WebFlow shows static pages. Flask shows dynamic pages. You want Flask content inside WebFlow.

**Solution:** JavaScript fetches Flask content and puts it in a WebFlow element.

---

## Step 1: Add Code to WebFlow

### Open WebFlow Designer

1. Go to [WebFlow](https://webflow.com) and log in
2. Click on your project
3. Click **"Designer"** button (top right)

### Add the Div Element

1. In the left sidebar, click **"Add Elements"** (plus icon)
2. Scroll down to **"Basic"**
3. Drag **"Div Block"** onto your page
4. Place it where you want Flask content to appear
5. With the div selected, go to **"Settings"** panel (right side)
6. In the **"Element Tag"** field, change to: `div`
7. In the **"ID"** field, enter exactly: `flask-content-injection-point`

### Add the Script

1. In the left sidebar, click **"Add Elements"**
2. Scroll down to **"Advanced"**
3. Drag **"Embed"** element
4. Place it at the **very bottom** of your page (after the div)
5. A code editor will open
6. **Delete everything** in the editor
7. **Paste this code:**

```html
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

8. Click **"Save & Close"**

### Change the Flask URL

In the code you just pasted, find this line:

```javascript
const FLASK_URL = 'http://localhost:5000';  // CHANGE THIS
```

Change `http://localhost:5000` to your Flask URL:
- Local development: `http://localhost:5000`
- Production: `https://your-app.onrender.com`

---

## Step 2: Test Flask Body Mode

Visit your Flask URL with `?_embed=body`:

```bash
curl https://your-app.onrender.com/?_embed=body
```

You should see HTML **without** `<html>`, `<head>`, `<body>` tags - just the content.

---

## Step 3: Configure Flask (Optional)

Add to `.env` file:

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

1. **Export to static HTML** (then host on Render/Netlify/Vercel)
2. **Upgrade to paid WebFlow plan** ($14+/mo)

---

## Troubleshooting

**Content not showing?**
1. Open browser DevTools (F12) → Console tab
2. Look for red error messages
3. Verify `FLASK_URL` is correct
4. Test Flask directly: `curl https://your-app.com/?_embed=body`

**"Element not found" error?**
- Check the div ID is exactly: `flask-content-injection-point`

---

## Files Created

| File | Purpose |
|------|---------|
| `app/webflow_integration.py` | Flask integration code |
| `app/routes_webflow.py` | Route helpers |
| `app/templates/webflow_shell.html` | Shell template for testing |
| `app/static/css/webflow-reset.css` | Shell styles |
