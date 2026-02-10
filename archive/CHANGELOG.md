# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-02-05

### First Official Release 🎉

### Added
- **Complete Analyst Performance Tracking System**
  - Individual analyst performance metrics (win rate, avg return, median return)
  - Benchmark comparisons (S&P 500, FTSE All-World)
  - Cumulative performance charts
  - Annualized returns for long-term holdings

- **Board Voting & Portfolio Management**
  - Democratic voting system for stock selections
  - Portfolio performance tracking
  - Purchase date management
  - Board-approved portfolio vs benchmark comparison

- **Smart Ticker Resolution**
  - AI-assisted ticker matching (DeepSeek API)
  - Web search fallback (Brave Search)
  - Yahoo Finance API integration
  - Caching system to avoid repeated lookups
  - "Other" event auto-detection for non-stock items
  - Admin manual override for ticker mappings

- **Email System**
  - SendGrid API integration for reliable email delivery on Render
  - SMTP fallback for local development
  - Account activation emails
  - Password reset functionality

- **User Management**
  - Domain-restricted registration (@klubinvestoru.com)
  - Secure email-based password setup
  - Admin and analyst roles
  - Activity logging

- **Data Import/Export**
  - CSV upload for analysis schedules
  - CSV export for performance reports
  - Automatic company and ticker extraction

- **Modern UI/UX**
  - Responsive design (desktop, tablet, mobile)
  - Bloomberg Terminal-inspired dashboards
  - Smooth animations and transitions
  - Glassmorphism effects

- **Multiple Deployment Options**
  - Docker support
  - Fly.io deployment
  - Render + neon.tech (recommended)
  - Debian/Ubuntu server setup
  - Comprehensive setup guides

### Changed
- Replaced `yfinance` with `yahooquery` for better cloud platform compatibility
- Improved ticker resolution with caching to reduce API calls
- Win rate calculation now excludes "Other" events and analyses without price data

### Security
- CSRF protection on all forms
- Secure password hashing
- Environment variable management
- Domain-restricted email registration

### Technical
- Flask 2.3.3 with SQLAlchemy
- PostgreSQL support for production
- SQLite for local development
- Bootstrap 5 frontend
- Gunicorn WSGI server
