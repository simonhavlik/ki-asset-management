# UI Wireframes

## Design Principles
- Clean, professional interface using Bootstrap 5.
- Responsive layout (desktop first, mobile friendly).
- Consistent navigation bar with user role‑specific menu.
- Use cards for metrics, tables for data.

## Common Elements

### Navigation Bar
- Logo / Brand "Analyst Performance Tracker"
- Left: Links based on role:
  - **Public**: Home, Login, Register
  - **Analyst**: Dashboard, Performance, Logout
  - **Admin**: Dashboard, Users, CSV Upload, Performance, Activity Logs, Settings
- Right: User email and dropdown (Logout, Profile)

### Footer
- Copyright, version, contact.

## Page Wireframes

### 1. Landing Page (Public)

```
+---------------------------------------------------------------------------+
| Nav: Home | Login | Register                                              |
+---------------------------------------------------------------------------+
|                                                                           |
|                        Analyst Performance Tracker                         |
|                                                                           |
|          Track stock analysis performance with ease.                       |
|                                                                           |
|          [Login]     [Register]                                           |
|                                                                           |
|                                                                           |
+---------------------------------------------------------------------------+
```

### 2. Login Page

```
+---------------------------------------------------------------------------+
| Nav: Home | Login | Register                                              |
+---------------------------------------------------------------------------+
|                                                                           |
|                                Sign In                                    |
|                                                                           |
|          Email: [________________________]                                |
|          Password: [_____________________]                                |
|                                                                           |
|          [Login]                                                          |
|                                                                           |
|          Forgot password? [Click here]                                    |
|                                                                           |
+---------------------------------------------------------------------------+
```

### 3. Registration Page

```
+---------------------------------------------------------------------------+
| Nav: Home | Login | Register                                              |
+---------------------------------------------------------------------------+
|                                                                           |
|                             Create Account                                |
|                                                                           |
|          Email: [________________________]                                |
|          Full Name: [____________________]                                |
|                                                                           |
|          Note: Only @klubinvestoru.com emails are allowed.                |
|                                                                           |
|          [Register]                                                       |
|                                                                           |
|          After registration, you will receive a password‑setup link       |
|          via email.                                                       |
|                                                                           |
+---------------------------------------------------------------------------+
```

### 4. Analyst Dashboard

```
+---------------------------------------------------------------------------+
| Nav: Dashboard | Performance | Logout                                     |
+---------------------------------------------------------------------------+
|                                                                           |
|  Welcome, Šimon Havlík!                                                   |
|                                                                           |
|  +-------------------+ +-------------------+ +-------------------+        |
|  |   Analyses        | |   Avg Return      | |   Win Rate        |        |
|  |       12          | |       +15.3%      | |       75%         |        |
|  +-------------------+ +-------------------+ +-------------------+        |
|                                                                           |
|  Recent Approved Analyses                                                 |
|  +------+-------------+------------+------------+------------+            |
|  | Co. | AnalysisDate| Price Then | Price Now  | Return     |            |
|  +------+-------------+------------+------------+------------+            |
|  | AAPL| 2025‑01‑15  | $150.00    | $200.00    | +33.33%    |            |
|  | GOOG| 2025‑02‑01  | $120.00    | $130.00    | +8.33%     |            |
|  +------+-------------+------------+------------+------------+            |
|                                                                           |
|  [View All Performance]                                                   |
|                                                                           |
+---------------------------------------------------------------------------+
```

### 5. Analyst Performance Detail Page

```
+---------------------------------------------------------------------------+
| Nav: Dashboard | Performance | Logout                                     |
+---------------------------------------------------------------------------+
|                                                                           |
|  Your Performance                                                         |
|                                                                           |
|  Filter: [All] [Last Year] [Last Quarter]                                 |
|                                                                           |
|  +------+-------------+------------+------------+------------+------------+
|  | Co. | AnalysisDate| Status     | Price Then | Price Now  | Return     |
|  +------+-------------+------------+------------+------------+------------+
|  | AAPL| 2025‑01‑15  | On Watchlist| $150.00   | $200.00    | +33.33%    |
|  | GOOG| 2025‑02‑01  | On Watchlist| $120.00   | $130.00    | +8.33%     |
|  | ... | ...         | ...        | ...        | ...        | ...        |
|  +------+-------------+------------+------------+------------+------------+
|                                                                           |
|  Export as CSV [⬇]                                                        |
|                                                                           |
+---------------------------------------------------------------------------+
```

### 6. Admin Dashboard

```
+---------------------------------------------------------------------------+
| Nav: Dashboard | Users | CSV Upload | Performance | Activity | Settings   |
+---------------------------------------------------------------------------+
|                                                                           |
|  System Overview                                                          |
|                                                                           |
|  +-------------------+ +-------------------+ +-------------------+        |
|  |   Total Users     | |   Total Analyses  | |   Pending CSV     |        |
|  |       45          | |       120         | |       0           |        |
|  +-------------------+ +-------------------+ +-------------------+        |
|                                                                           |
|  Quick Actions                                                            |
|  [Upload CSV] [Recalculate Performance] [Create User]                     |
|                                                                           |
|  Recent Activity Log                                                      |
|  +------------+---------------------+------------------------------------+
|  | Time       | User               | Action                             |
|  +------------+---------------------+------------------------------------+
|  | 2026‑01‑29 | admin@...          | Uploaded "schedule.csv"            |
|  | 2026‑01‑28 | simon@...          | Logged in                          |
|  +------------+---------------------+------------------------------------+
|                                                                           |
+---------------------------------------------------------------------------+
```

### 7. User Management Page

```
+---------------------------------------------------------------------------+
| Nav: Dashboard | Users | CSV Upload | Performance | Activity | Settings   |
+---------------------------------------------------------------------------+
|                                                                           |
|  User Management                                                          |
|                                                                           |
|  Search: [____________] Filter: [All] [Active] [Inactive] [Admin]        |
|                                                                           |
|  +------+---------------------+---------+---------+------------+---------+
|  | Name | Email              | Role    | Status  | Last Login | Actions |
|  +------+---------------------+---------+---------+------------+---------+
|  | Šimon| simon@...          | Analyst | Active  | 2026‑01‑29 | [Edit]  |
|  | Admin| admin@...          | Admin   | Active  | 2026‑01‑29 | [Edit]  |
|  +------+---------------------+---------+---------+------------+---------+
|                                                                           |
|  [Create New User]                                                        |
|                                                                           |
|  Actions:                                                                 |
|  • Edit: toggle active, change role, send password reset.                 |
|  • Delete (soft).                                                         |
|                                                                           |
+---------------------------------------------------------------------------+
```

### 8. CSV Upload Page

```
+---------------------------------------------------------------------------+
| Nav: Dashboard | Users | CSV Upload | Performance | Activity | Settings   |
+---------------------------------------------------------------------------+
|                                                                           |
|  Upload CSV                                                                |
|                                                                           |
|  Choose file: [Browse...] schedule.csv                                    |
|                                                                           |
|  Options:                                                                 |
|  [ ] Replace existing data (will delete all analyses before import)       |
|  [ ] Auto‑create missing analyst accounts                                 |
|                                                                           |
|  [Upload and Process]                                                     |
|                                                                           |
|  Upload History                                                           |
|  +------+---------------------+----------+---------+---------------------+
|  | Date | File Name          | Uploaded | Rows    | Status              |
|  +------+---------------------+----------+---------+---------------------+
|  | ...  | schedule.csv       | Admin    | 120     | Completed           |
|  +------+---------------------+----------+---------+---------------------+
|                                                                           |
+---------------------------------------------------------------------------+
```

### 9. Performance Calculation Page (Admin)

```
+---------------------------------------------------------------------------+
| Nav: Dashboard | Users | CSV Upload | Performance | Activity | Settings   |
+---------------------------------------------------------------------------+
|                                                                           |
|  Performance Calculation                                                  |
|                                                                           |
|  Last calculated: 2026‑01‑28 14:30                                        |
|                                                                           |
|  [Recalculate Now]                                                        |
|                                                                           |
|  Progress: [###############] 45% (Processing 45/100 analyses)             |
|                                                                           |
|  Analyst Ranking                                                          |
|  +------+---------------------+---------+------------+---------+---------+
|  | Rank | Analyst            | Analyses| Avg Return | Win Rate| Actions |
|  +------+---------------------+---------+------------+---------+---------+
|  | 1    | Šimon Havlík       | 12      | +15.3%     | 75%     | [View]  |
|  | 2    | Adam Kolomazník    | 18      | +10.2%     | 66%     | [View]  |
|  +------+---------------------+---------+------------+---------+---------+
|                                                                           |
|  Export Ranking as CSV [⬇]                                                |
|                                                                           |
+---------------------------------------------------------------------------+
```

### 10. Activity Logs Page

```
+---------------------------------------------------------------------------+
| Nav: Dashboard | Users | CSV Upload | Performance | Activity | Settings   |
+---------------------------------------------------------------------------+
|                                                                           |
|  Activity Logs                                                            |
|                                                                           |
|  Filter by user: [____________] Date range: [2026‑01‑01] to [2026‑01‑29]  |
|                                                                           |
|  +------------+---------------------+------------------------------------+
|  | Timestamp  | User               | Action (Details)                   |
|  +------------+---------------------+------------------------------------+
|  | 2026‑01‑29 | admin@...          | CSV upload "schedule.csv"          |
|  | 2026‑01‑29 | simon@...          | Login successful                   |
|  +------------+---------------------+------------------------------------+
|                                                                           |
|  Pagination: [Previous] 1 2 3 [Next]                                     |
|                                                                           |
+---------------------------------------------------------------------------+
```

### 11. Settings Page

```
+---------------------------------------------------------------------------+
| Nav: Dashboard | Users | CSV Upload | Performance | Activity | Settings   |
+---------------------------------------------------------------------------+
|                                                                           |
|  System Settings                                                          |
|                                                                           |
|  Email Domain Restriction                                                 |
|  Allowed domain: [klubinvestoru.com]                                      |
|                                                                           |
|  Auto‑create Analyst Accounts                                             |
|  [ ] Enable automatic account creation during CSV import                  |
|  Email pattern: [{first}.{last}@klubinvestoru.com]                        |
|                                                                           |
|  DeepSeek API Integration                                                 |
|  API Key: [************************] [Test Connection]                    |
|                                                                           |
|  SMTP Configuration                                                       |
|  Server: [smtp.gmail.com] Port: [587]                                     |
|  Username: [analytics@klubinvestoru.com]                                  |
|  Password: [************************] [Test Email]                        |
|                                                                           |
|  [Save Settings]                                                          |
|                                                                           |
+---------------------------------------------------------------------------+
```

## Mobile Adaptations

- Collapsible navigation hamburger menu.
- Stack cards vertically.
- Tables become scrollable horizontally.
- Reduce padding.

## Color Palette

- Primary: `#0066cc` (blue) – for buttons, active links.
- Secondary: `#6c757d` (gray) – for borders, inactive.
- Success: `#28a745` (green) – positive returns.
- Danger: `#dc3545` (red) – negative returns.
- Background: `#f8f9fa` (light gray).

## Icons

- Use Bootstrap Icons (free).
- Dashboard: `speedometer2`
- Users: `people`
- CSV Upload: `upload`
- Performance: `graph‑up`
- Activity: `list‑ul`
- Settings: `gear`

## Next Steps

- Convert wireframes to HTML templates.
- Integrate with Flask routes.
- Add dynamic data using Jinja2.
- Apply CSS styling.