# Database Schema (SQLite)

## Tables

### users
- `id` INTEGER PRIMARY KEY AUTOINCREMENT
- `email` TEXT UNIQUE NOT NULL
- `password_hash` TEXT NOT NULL
- `full_name` TEXT
- `is_admin` BOOLEAN DEFAULT 0
- `is_active` BOOLEAN DEFAULT 1
- `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP
- `last_login` TIMESTAMP NULL
- `email_verified` BOOLEAN DEFAULT 0
- `verification_token` TEXT NULL

### companies
- `id` INTEGER PRIMARY KEY AUTOINCREMENT
- `name` TEXT NOT NULL
- `ticker_symbol` TEXT NULL
- `sector` TEXT NULL
- `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP

### analyses
- `id` INTEGER PRIMARY KEY AUTOINCREMENT
- `company_id` INTEGER NOT NULL REFERENCES companies(id)
- `analysis_date` DATE NOT NULL
- `status` TEXT NOT NULL (e.g., 'On Watchlist', 'Refused', 'Neutral', 'To-Be-Analyzed', 'Event', 'Workshop', 'Learning', 'NA')
- `comment` TEXT
- `files_media` TEXT (comma-separated file paths)
- `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP
- `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP
- `is_approved` BOOLEAN GENERATED ALWAYS AS (status = 'On Watchlist') STORED (SQLite 3.31+)
- `csv_upload_id` INTEGER NULL REFERENCES csv_uploads(id)

### analysis_analysts
- `analysis_id` INTEGER NOT NULL REFERENCES analyses(id) ON DELETE CASCADE
- `user_id` INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE
- `role` TEXT DEFAULT 'analyst'  -- 'analyst' or 'opponent'
- PRIMARY KEY (analysis_id, user_id, role)

### stock_prices
- `id` INTEGER PRIMARY KEY AUTOINCREMENT
- `company_id` INTEGER NOT NULL REFERENCES companies(id)
- `date` DATE NOT NULL
- `close_price` DECIMAL(10,2) NOT NULL
- `volume` BIGINT NULL
- `fetched_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP
- UNIQUE(company_id, date)

### performance_calculations
- `id` INTEGER PRIMARY KEY AUTOINCREMENT
- `analysis_id` INTEGER NOT NULL REFERENCES analyses(id)
- `calculation_date` DATE NOT NULL
- `price_at_analysis` DECIMAL(10,2) NOT NULL
- `price_current` DECIMAL(10,2) NOT NULL
- `return_pct` DECIMAL(10,2) NOT NULL
- `calculated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP
- UNIQUE(analysis_id, calculation_date)

### activity_logs
- `id` INTEGER PRIMARY KEY AUTOINCREMENT
- `user_id` INTEGER NULL REFERENCES users(id)
- `action` TEXT NOT NULL
- `details` TEXT
- `timestamp` TIMESTAMP DEFAULT CURRENT_TIMESTAMP

### csv_uploads
- `id` INTEGER PRIMARY KEY AUTOINCREMENT
- `filename` TEXT NOT NULL
- `uploaded_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP
- `processed_at` TIMESTAMP NULL
- `uploaded_by` INTEGER NULL REFERENCES users(id)
- `row_count` INTEGER DEFAULT 0

## Indexes

- `idx_users_email` ON users(email)
- `idx_analyses_company_date` ON analyses(company_id, analysis_date)
- `idx_analyses_status` ON analyses(status)
- `idx_stock_prices_company_date` ON stock_prices(company_id, date)
- `idx_activity_logs_user` ON activity_logs(user_id)
- `idx_csv_uploads_processed` ON csv_uploads(processed_at)

## Relationships

- Each analysis belongs to one company (many-to-one).
- Each analysis can have multiple analysts (many-to-many via analysis_analysts).
- Each analysis can have multiple opponents (same table with role='opponent').
- Stock prices are stored per company per date.
- Performance calculations are snapshots per analysis per calculation date.
- CSV uploads track each imported file and its processing status.

## Notes

- The `is_approved` column is a generated column that automatically reflects whether status equals 'On Watchlist'. This ensures consistency.
- For simplicity, we store `files_media` as a comma-separated string; alternatively could be a separate table.
- The `ticker_symbol` may be null for non‑stock entries (events, workshops). Those rows will be excluded from performance tracking.
- Email domain validation (@klubinvestoru.com) will be enforced at application level, but could also be added as a CHECK constraint.
- Password reset tokens can be stored in a separate table if needed; for simplicity we can implement token‑based reset with expiry.