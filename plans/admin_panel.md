# Admin Panel Features

## Overview
The admin panel provides tools for managing users, uploading and processing CSV data, calculating analyst performance, and monitoring system activity. Accessible only to users with `is_admin=True`.

## 1. User Management

### List Users
- Table displaying all registered users with columns: Email, Full Name, Role (Admin/Analyst), Status (Active/Inactive), Last Login, Actions.
- Filter by role and status.
- Pagination (optional).

### User Actions
- **Toggle Active Status**: Deactivate/reactivate a user (deactivated users cannot log in).
- **Promote/Demote Admin**: Grant or revoke admin privileges.
- **Send Password Reset**: Force‑send a password‑reset link to the user's email (useful for onboarding).
- **Delete User** (soft delete): Mark as deleted, hide from lists but keep referential integrity.

### Create User
- Form with fields: Email (domain validated), Full Name, Role (Admin/Analyst).
- On submission, create an inactive account and send a password‑setup email (same flow as self‑registration).
- Option to skip email and create a temporary password (less secure).

## 2. CSV Upload & Processing

### Upload Interface
- Form with file input (accept `.csv`).
- Optional checkbox: "Replace existing data" – if checked, delete all existing analyses before import (warning shown).
- Upload button triggers processing.

### CSV Processing Steps
1. Validate file format (header row must match expected columns).
2. Parse each row:
   - Skip empty rows.
   - Determine if row represents a stock analysis (using DeepSeek API or heuristic).
   - Extract/clean company name, date, sector, analysts, opponents, comment, status, files.
   - For each analyst name, find or create a user record (if `auto‑create analyst accounts` toggle is enabled).
   - Find or create a company record; attempt to map to a stock ticker (using DeepSeek API or manual mapping table).
   - Create analysis record with many‑to‑many links to analysts/opponents.
3. Track progress and errors (e.g., rows that could not be processed).
4. Store upload metadata in `csv_uploads` table.

### Post‑Upload Actions
- Display summary: number of rows processed, skipped, errors.
- Provide link to error log for download.
- Option to retry failed rows.

### Auto‑Create Analyst Accounts
- Global toggle in admin settings (or per‑upload option).
- When enabled, for each unique analyst name in the CSV that does not have a matching user account:
  - Generate email: `{firstname.lastname}@klubinvestoru.com` (requires name‑to‑email mapping logic).
  - Create inactive user with no password.
  - Send password‑setup email to that address.
- If email cannot be derived, skip and log warning.

## 3. Performance Calculation

### Calculation Trigger
- Button "Recalculate Performance" in admin panel.
- When clicked, the system:
  1. Fetches latest stock prices for all companies that have approved analyses (`status = 'On Watchlist'`) and missing price data.
  2. For each approved analysis:
     - Get stock price on the analysis date (or nearest trading day).
     - Get most recent available stock price (today or last trading day).
     - Compute return percentage: `(price_current - price_at_analysis) / price_at_analysis * 100`.
     - Store/update `performance_calculations` table with calculation date = today.
  3. Aggregate per‑analyst metrics (average return, win rate, etc.).
- Progress indicator (background task) optional.

### Performance Dashboard
- View showing analyst rankings (table or cards) based on aggregated performance.
- Metrics:
  - Number of approved analyses.
  - Average return across all approved analyses.
  - Median return.
  - Win rate (percentage of analyses with positive return).
  - Total portfolio return (hypothetical equal‑weighted).
- Filter by time period (e.g., last year, all time).
- Export to CSV.

### Individual Analyst Drill‑Down
- Click on analyst name to see detailed table of their approved analyses:
  - Company, analysis date, price at analysis, current price, return, status.
  - Link to original files if available.

## 4. Activity Logs

### Logged Actions
- User login/logout (success/failure).
- Password changes and resets.
- CSV uploads (who, when, file name).
- Performance calculation runs.
- Admin actions (user status changes, promotions).
- Any data modifications (optional).

### Log View
- Table with columns: Timestamp, User, Action, Details (JSON snippet), IP address (if captured).
- Filter by date range, user, action type.
- Export logs.

## 5. System Settings

### Editable Settings (via UI or environment)
- Allowed email domain (default `@klubinvestoru.com`).
- Auto‑create analyst accounts (on/off).
- Default analyst email pattern (e.g., `{first}.{last}@klubinvestoru.com`).
- DeepSeek API key (masked input).
- SMTP configuration (test button).
- Performance calculation frequency (manual only per requirement).

## 6. Data Management

### Browse Analyses
- Table of all analyses with filters by status, date range, analyst, company.
- Ability to edit individual analysis (status, comment, assign analysts) – advanced feature.

### Company & Ticker Mapping
- List of companies with associated ticker symbols.
- Admin can manually correct ticker symbols, mark as non‑stock (e.g., events).
- Option to trigger ticker lookup via DeepSeek API for selected companies.

## Implementation Notes

### Background Tasks
- CSV processing and performance calculation may be long‑running; consider using Celery (optional) or simple threading with progress polling via SSE/WebSockets. For simplicity, synchronous processing with progress updates via page refresh is acceptable.

### Error Handling
- Comprehensive validation with user‑friendly error messages.
- Log errors to database for later review.

### UI Framework
- Use Bootstrap 5 for responsive, clean interface.
- Admin panel as a separate layout with a sidebar navigation.

### Permissions
- All admin endpoints must be protected by `@admin_required` decorator.
- Sensitive actions (e.g., delete user) require confirmation.

## Mermaid Diagram: Admin Panel Navigation

```mermaid
flowchart TD
    A[Admin Dashboard] --> B[User Management]
    A --> C[CSV Upload]
    A --> D[Performance Calculation]
    A --> E[Activity Logs]
    A --> F[System Settings]
    A --> G[Browse Analyses]
    
    B --> B1[List Users]
    B --> B2[Create User]
    
    C --> C1[Upload Form]
    C --> C2[Upload History]
    
    D --> D1[Recalculate Button]
    D --> D2[Performance Dashboard]
    
    E --> E1[Filter Logs]
    
    F --> F1[Edit Settings]
    
    G --> G1[Filter & Edit]