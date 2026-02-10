# Admin Panel Guide

Complete guide for administrators managing the KI Asset Management system.

---

## 🎯 Admin Capabilities

As an admin, you have full access to:

- 👥 **User Management** - Create, edit, deactivate users
- 📊 **Performance Tracking** - Calculate and view analyst metrics
- 📁 **CSV Upload** - Import analysis schedules from Notion
- 🏢 **Company Management** - Map tickers and manage companies
- 🗳️ **Board Voting** - Track votes and portfolio performance
- 📝 **Blog Management** - Manage all blog posts
- 🔍 **Activity Logs** - Monitor system activity

---

## 👥 User Management

### Accessing User Management

1. Log in as admin
2. Go to **Admin → Users**

### Creating Users

**Option 1: Manual Creation**
1. Click **"Create User"**
2. Enter email (must be `@klubinvestoru.com`)
3. Enter full name
4. Select role (Admin or Analyst)
5. Click **Create**
6. User receives email to set password

**Option 2: Via CSV Import**
- Analysts are auto-created during CSV upload
- See [CSV Upload section](#csv-upload)

### Managing Users

| Action | How To |
|--------|--------|
| **Deactivate User** | Toggle "Active" status (user can't log in) |
| **Promote to Admin** | Edit user → Check "Admin" role |
| **Reset Password** | Click "Reset Password" → Email sent automatically |
| **Delete User** | Soft delete (hides user but keeps data integrity) |

### User Roles

- **Admin**: Full system access
- **Analyst**: Dashboard access, blog posting

---

## 📁 CSV Upload

### Preparing Your CSV

Export from Notion with these columns:

```csv
Date,Company,Sector,Analysts,Opponents,Comment,Status,Files
2024-01-15,Apple Inc,Technology,John Doe,Jane Smith,Bullish thesis,On Watchlist,analysis.pdf
```

**Required Columns:**
- `Date` - Analysis date (YYYY-MM-DD)
- `Company` - Company name
- `Sector` - Industry sector
- `Analysts` - Comma-separated analyst names
- `Status` - Scheduled, On Watchlist, Approved, Rejected

**Optional Columns:**
- `Opponents` - Analysts opposing
- `Comment` - Analysis notes
- `Files` - Related file links

### Upload Process

1. Go to **Admin → CSV Upload**
2. Select your CSV file
3. Choose options:
   - ☑️ Replace existing data (optional)
4. Click **Upload**
5. Review summary:
   - Rows processed
   - Errors (if any)
   - Companies created
   - Analyses created

### Notion Integration

Direct import from Notion databases.

**1. Configure Notion Integration**

Create a Notion integration:
- Go to https://www.notion.so/my-integrations
- Create new integration with "Read content" capabilities
- Copy the **Internal Integration Token**

**2. Share Database with Integration**

- Open your Notion database
- Click ⋮ → Connections → Add connections
- Select your integration

**3. Configure Environment Variables**

Add to `.env`:

```bash
NOTION_API_KEY=your_notion_api_key_here
NOTION_DATABASE_ID=your_database_id_here
```

### Post-Upload Actions

After CSV upload, you must:

1. **Map Company Tickers** (see below)
2. **Run Performance Calculation** (see below)

---

## 🏢 Company Ticker Management

### Why This Matters

Tickers are required to fetch stock prices and calculate performance.

### Mapping Tickers

1. Go to **Admin → Company Ticker Mappings**
2. For each company without a ticker:

**Option A: Manual Entry**
- Click "Edit"
- Enter ticker symbol (e.g., "AAPL")
- Click "Save"

**Option B: Auto-Fill with AI**
- Click "Auto-fill with DeepSeek"
- AI attempts to match company name to ticker
- Review and confirm

**Option C: Mark as Other**
- For non-stock events
- Click "Mark as Other"
- Won't affect performance calculations

### Bulk Operations

- **Auto-fill All**: Uses AI to fill all missing tickers
- **Export Mappings**: Download current ticker mappings
- **Import Mappings**: Upload corrected mappings

---

## 📊 Performance Tracking

### Calculating Performance

1. Go to **Admin → Performance**
2. Click **"Recalculate Performance"**
3. System will:
   - Fetch current stock prices from Yahoo Finance
   - Get historical prices at analysis dates
   - Calculate returns for each approved analysis
   - Update analyst rankings

**Takes:** 1-2 minutes depending on data size

### Understanding Metrics

| Metric | Description |
|--------|-------------|
| **Win Rate** | % of analyses with positive return |
| **Avg Return** | Average return across all analyses |
| **Median Return** | Middle value (less affected by outliers) |
| **Total Return** | Hypothetical equal-weighted portfolio |
| **Benchmark** | S&P 500 (SPY) or FTSE All-World (VT) comparison |

### Viewing Analyst Details

1. Click on any analyst name
2. View detailed breakdown:
   - All approved analyses
   - Individual returns
   - Price at buy vs current
   - Charts and visualizations

### Filtering Options

- **Decision Type**: Approved only, Neutral+Approved, All
- **Time Period**: All time, last year, custom range
- **Annualized**: Toggle annualized returns for long-term holdings

### Exporting Data

Click **"Export CSV"** to download:
- Analyst rankings
- Individual analysis performance
- Portfolio details

---

## 🗳️ Board Voting System

### How It Works

Board members vote on analyses to decide which stocks to purchase.

### Voting Process

1. Go to **Admin → Board**
2. View all analyses requiring votes
3. For each analysis:
   - Click **"Yes"** to approve purchase
   - Click **"No"** to reject
   - Click **"Abstain"** to skip

### Portfolio Tracking

**Purchased Stocks:**
- If Yes votes > No votes = "Purchased"
- Purchase date recorded
- Performance tracked separately

**Purchase Date Management:**
- Click **"Edit Purchase Date"** to adjust
- Used for accurate performance calculation
- Can be backdated if needed

### Portfolio Performance

Click **"Calculate Portfolio Performance"** to see:
- Overall portfolio return
- Comparison vs benchmarks
- Individual stock performance
- Purchase date tracking

### Export Portfolio

Click **"Export CSV"** for:
- Portfolio holdings
- Purchase dates
- Current values
- Returns

---

## 📝 Blog Management

### Managing Posts

1. Go to **Admin → Blog Posts**
2. View all posts (drafts and published)

### Actions

| Action | Description |
|--------|-------------|
| **Edit** | Modify post content |
| **Publish/Unpublish** | Toggle visibility |
| **Feature** | Highlight on homepage |
| **Delete** | Remove post permanently |

### Featured Posts

- Featured posts appear on homepage
- Max 3 featured posts recommended
- Use for important announcements or best content

---

## 🔍 Activity Logs

### Viewing Logs

1. Go to **Admin → Activity Logs**
2. Filter by:
   - Date range
   - User
   - Action type

### Logged Actions

- User login/logout
- Password changes
- CSV uploads
- Performance calculations
- Admin actions (user changes, etc.)

### Export Logs

Click **"Export CSV"** for:
- Audit trails
- Security reviews
- Compliance reporting

---

## ⚙️ System Settings

### Email Configuration

Verify email is working:
1. Check environment variables
2. Send test email
3. Review email logs

### Cache Management

Clear cache if needed:
- **Public data cache**: Clears automatically on data changes
- **Manual clear**: Use "Clear Cache" button (if available)

### Database Maintenance

- **Backup**: Automatic (neon.tech)
- **Restore**: Via neon.tech dashboard
- **Optimization**: Runs automatically

---

## 📈 Best Practices

### Regular Tasks (Weekly)

- [ ] Review new user registrations
- [ ] Run performance calculation
- [ ] Check board votes
- [ ] Review activity logs for issues

### Monthly Tasks

- [ ] Export performance reports
- [ ] Review and archive old data
- [ ] Check system health
- [ ] Update documentation

### Quarterly Tasks

- [ ] Security audit
- [ ] User access review
- [ ] Performance optimization review
- [ ] Backup verification

---

## 🆘 Troubleshooting

### CSV Upload Fails

**Problem:** File not processing
**Solution:**
- Check CSV format matches template
- Ensure required columns present
- Remove special characters from company names

### Performance Calculation Stuck

**Problem:** Long calculation time
**Solution:**
- Check internet connection (Yahoo Finance API)
- Verify tickers are valid
- Try again later if Yahoo is slow

### Emails Not Sending

**Problem:** Registration/password reset emails not received
**Solution:**
- Check SendGrid/SMTP configuration
- Verify sender email is verified
- Check spam folders

### Users Can't Register

**Problem:** Registration fails
**Solution:**
- Check `ALLOWED_EMAIL_DOMAIN` setting
- Verify email service is working
- Check user isn't already registered

---

## 🔐 Security Checklist

- [ ] Change default admin password
- [ ] Enable 2FA where possible
- [ ] Regular access review
- [ ] Monitor activity logs
- [ ] Keep software updated
- [ ] Regular backups verified

---

<p align="center">
  <strong>Questions about admin features?</strong><br>
  Contact the technical team or check <a href="../AI-ORIENTATION.md">technical documentation</a>
</p>
