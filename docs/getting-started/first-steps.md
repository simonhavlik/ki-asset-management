# First Steps

Now that you've installed the application, let's get you familiar with the basics.

---

## 🎯 What You'll Learn

- Application structure and navigation
- How to access different user roles
- Basic configuration options
- First-time setup tasks

---

## 🏗️ Application Overview

### User Roles

The application has three user types:

| Role | Access | Description |
|------|--------|-------------|
| **Public Visitor** | Landing page, blog | Can view public information |
| **Analyst** | Personal dashboard | Can view own performance metrics |
| **Admin** | Full access | Can manage users, upload data, view all analytics |

### Main Sections

```
┌─────────────────────────────────────────────────────────────┐
│  🏠 Public Area                                             │
│  ├── Landing page with club information                     │
│  ├── Blog with articles                                     │
│  └── Terms and conditions                                   │
├─────────────────────────────────────────────────────────────┤
│  🔐 Authenticated Area                                      │
│  ├── Analyst Dashboard (personal performance)               │
│  ├── Blog management (create/edit posts)                    │
│  └── User profile settings                                  │
├─────────────────────────────────────────────────────────────┤
│  👑 Admin Area                                              │
│  ├── User management                                        │
│  ├── CSV upload & processing                                │
│  ├── Performance tracking & calculations                    │
│  ├── Board voting system                                    │
│  └── System logs & monitoring                               │
└─────────────────────────────────────────────────────────────┘
```

---

## 🚀 Initial Setup Tasks

### 1. Access the Admin Panel

1. Navigate to [http://127.0.0.1:5000/auth/login](http://127.0.0.1:5000/auth/login)
2. Log in with the admin credentials you created during setup
3. You'll be redirected to the **Admin Dashboard**

### 2. Configure Email (Required for User Registration)

Email is essential for:
- New user registration
- Password reset functionality
- Notifications

**Option A: Gmail SMTP (Local Development)**

1. Enable 2-Factor Authentication on your Google account
2. Generate an App Password at [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
3. Update your `.env` file:

```bash
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USE_TLS=true
MAIL_USERNAME=your-email@gmail.com
MAIL_PASSWORD=your-gmail-app-password
MAIL_DEFAULT_SENDER=your-email@gmail.com
```

**Option B: SendGrid (Production)**

See [Environment Variables Reference](../reference/environment-variables.md) for SendGrid setup.

### 3. Upload Initial Data

**Upload Analysis Schedule (CSV):**

1. Go to **Admin → CSV Upload**
2. Upload your Notion-exported analysis schedule
3. The system will:
   - Parse the CSV
   - Create company records
   - Create analysis records
   - Link analysts

**CSV Format Expected:**
```csv
Date,Company,Sector,Analysts,Opponents,Comment,Status,Files
2024-01-15,Apple Inc,Technology,John Doe,Jane Smith,Bullish thesis,On Watchlist,analysis.pdf
```

### 4. Set Up Company Tickers

After CSV upload:

1. Go to **Admin → Company Ticker Mappings**
2. For each company without a ticker:
   - **Manual:** Enter the ticker symbol directly
   - **Auto-fill:** Click "Auto-fill with DeepSeek" (requires DEEPSEEK_API_KEY)
   - **Mark as Other:** For non-stock events

> 💡 **Tip:** DeepSeek API significantly speeds up ticker matching. Get a free key at [platform.deepseek.com](https://platform.deepseek.com)

### 5. Run First Performance Calculation

1. Go to **Admin → Performance**
2. Click **"Recalculate Performance"**
3. The system will:
   - Fetch current stock prices from Yahoo Finance
   - Calculate returns for each analysis
   - Update analyst rankings

---

## 📊 Key Workflows

### As an Admin

**Daily Tasks:**
- Review new analyses from CSV uploads
- Verify ticker mappings
- Monitor performance calculations
- Manage board votes

**Weekly Tasks:**
- Run performance recalculation
- Export performance reports
- Review user activity logs

### As an Analyst

**Regular Use:**
1. Log in to view your personal dashboard
2. Check your performance metrics
3. Compare against benchmarks (S&P 500, FTSE All-World)
4. View detailed charts of your analysis performance

### Using the Blog

**Creating a Post:**
1. Go to **Blog → New Post**
2. Enter title and content
3. Click **"Auto-Generate with AI"** for SEO optimization (requires DEEPSEEK_API_KEY)
4. Select a featured image from the gallery
5. Click **Publish** or **Save Draft**

**AI Document Import:**
1. Upload a PDF or DOCX file
2. Choose style: Investment Pitch, SEO Article, Academic Paper, or Blog Post
3. AI generates a complete article from your document
4. Edit and publish

---

## 🔧 Customization Options

### Change the Allowed Email Domain

By default, only `@klubinvestoru.com` emails can register. To change:

Edit `.env`:
```bash
ALLOWED_EMAIL_DOMAIN=your-domain.com
```

### Customize the Landing Page

Edit these files:
- `app/templates/main/index.html` - Hero section
- `app/static/css/custom.css` - Styles

### Update Team Photos

Replace images in:
- `app/images/` directory

### Modify Email Templates

Templates located in:
- `app/templates/email/`

---

## 🧪 Testing Your Setup

### Test User Registration

1. Log out (or use incognito window)
2. Go to `/auth/register`
3. Register with an allowed domain email
4. Check your email for the verification link
5. Click the link to set your password

### Test CSV Upload

1. Create a test CSV file:
```csv
Date,Company,Sector,Analysts,Opponents,Comment,Status
2024-01-15,Microsoft,Technology,Test User,,Bullish,On Watchlist
```

2. Go to **Admin → CSV Upload**
3. Upload the file
4. Verify the analysis appears in the system

### Test Performance Calculation

1. Ensure you have at least one company with a valid ticker
2. Go to **Admin → Performance**
3. Click **"Recalculate Performance"**
4. Verify metrics appear in the table

---

## 📚 Next Steps

### For Administrators
- Read the [Admin Panel Guide](../user-guides/admin.md)
- Learn about [Security Best Practices](../operations/security.md)
- Review [Deployment Options](../deployment/README.md)

### For Analysts
- Check the [Analyst Dashboard Guide](../user-guides/analyst.md)
- Learn about [Performance Metrics](../user-guides/analyst.md#understanding-metrics)

### For Developers
- Read the [Development Guide](../development/README.md)
- Review the [Architecture Overview](../development/architecture.md)
- Check [Contributing Guidelines](../development/contributing.md)

---

## 🆘 Common First-Time Issues

**"CSRF token missing" error:**
- Set `SECRET_KEY` in `.env`
- Restart the Flask server

**Emails not sending:**
- Verify email configuration in `.env`
- Check spam folders
- For Gmail: Use App Password, not your regular password

**Stock prices not updating:**
- Ensure companies have valid ticker symbols
- Check internet connection
- Verify Yahoo Finance API is accessible

**"Company ticker not found":**
- Manually enter the ticker in Company Ticker Mappings
- Or set up DeepSeek API for auto-matching

---

## ✅ Setup Checklist

- [ ] Application installed and running
- [ ] Admin user created
- [ ] Email configured and tested
- [ ] CSV data uploaded (or sample data)
- [ ] Company tickers mapped
- [ ] Performance calculation run
- [ ] Test user registered
- [ ] Blog functionality verified (optional)

Once you've completed these steps, you're ready to use the full application!
