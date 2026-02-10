# Database Schema

Complete database schema reference for KI Asset Management.

---

## 📊 Entity Relationship Diagram

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│     User        │     │     Analysis     │     │    Company      │
├─────────────────┤     ├──────────────────┤     ├─────────────────┤
│ PK id           │◄────┤ PK id            │────►│ PK id           │
│ email           │     │ FK company_id    │     │ name            │
│ password_hash   │     │ date             │     │ ticker_symbol   │
│ is_admin        │     │ sector           │     │ sector          │
│ full_name       │     │ comment          │     │ exchange        │
│ created_at      │     │ status           │     └─────────────────┘
└─────────────────┘     │ created_at       │
         │              └──────────────────┘
         │                       │
         │              ┌──────────────────┐
         └─────────────►│ AnalysisAnalysts │
                        │ (junction table) │
                        └──────────────────┘
```

---

## 👤 User

Stores user accounts and authentication information.

```sql
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    is_admin BOOLEAN DEFAULT FALSE,
    full_name VARCHAR(255),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_login TIMESTAMP
);
```

**Fields:**
- `id` - Unique identifier
- `email` - User's email (must be @klubinvestoru.com)
- `password_hash` - Bcrypt hashed password
- `is_admin` - Admin privileges flag
- `full_name` - Display name
- `is_active` - Account status (can login?)
- `created_at` - Registration date
- `last_login` - Last successful login

---

## 🏢 Company

Stores company information and ticker symbols.

```sql
CREATE TABLE companies (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    ticker_symbol VARCHAR(20),
    sector VARCHAR(100),
    exchange VARCHAR(50),
    is_other BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Fields:**
- `id` - Unique identifier
- `name` - Company name
- `ticker_symbol` - Stock ticker (e.g., "AAPL")
- `sector` - Industry sector
- `exchange` - Stock exchange (NYSE, NASDAQ, etc.)
- `is_other` - Non-stock event flag
- `created_at` - Creation date

---

## 📊 Analysis

Stores stock analyses presented by analysts.

```sql
CREATE TABLE analyses (
    id SERIAL PRIMARY KEY,
    company_id INTEGER REFERENCES companies(id),
    date DATE NOT NULL,
    sector VARCHAR(100),
    comment TEXT,
    status VARCHAR(50) DEFAULT 'Scheduled',
    files TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Fields:**
- `id` - Unique identifier
- `company_id` - Reference to company
- `date` - Analysis presentation date
- `sector` - Industry sector (may differ from company)
- `comment` - Analysis notes/comments
- `status` - Scheduled, On Watchlist, Approved, Rejected
- `files` - Related file links
- `created_at` - Creation date

---

## 🔗 AnalysisAnalysts

Many-to-many relationship between analyses and analysts.

```sql
CREATE TABLE analysis_analysts (
    analysis_id INTEGER REFERENCES analyses(id),
    user_id INTEGER REFERENCES users(id),
    is_opponent BOOLEAN DEFAULT FALSE,
    PRIMARY KEY (analysis_id, user_id)
);
```

**Fields:**
- `analysis_id` - Reference to analysis
- `user_id` - Reference to analyst (user)
- `is_opponent` - True if analyst opposed the analysis

---

## 📈 PerformanceCalculation

Caches performance metrics for analyses.

```sql
CREATE TABLE performance_calculations (
    id SERIAL PRIMARY KEY,
    analysis_id INTEGER REFERENCES analyses(id),
    price_at_buy FLOAT,
    price_current FLOAT,
    return_pct FLOAT,
    annualized_return_pct FLOAT,
    calculated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Fields:**
- `id` - Unique identifier
- `analysis_id` - Reference to analysis
- `price_at_buy` - Stock price at analysis date
- `price_current` - Current stock price
- `return_pct` - Return percentage
- `annualized_return_pct` - Annualized return (for holdings > 1 year)
- `calculated_at` - Calculation timestamp

---

## 🗳️ BoardVote

Stores board voting records.

```sql
CREATE TABLE board_votes (
    id SERIAL PRIMARY KEY,
    analysis_id INTEGER REFERENCES analyses(id),
    user_id INTEGER REFERENCES users(id),
    vote VARCHAR(10) CHECK (vote IN ('Yes', 'No', 'Abstain')),
    voted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Fields:**
- `id` - Unique identifier
- `analysis_id` - Reference to analysis
- `user_id` - Board member who voted
- `vote` - Yes, No, or Abstain
- `voted_at` - Vote timestamp

---

## 💰 BenchmarkPrice

Stores historical benchmark prices (S&P 500, FTSE All-World).

```sql
CREATE TABLE benchmark_prices (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    date DATE NOT NULL,
    price FLOAT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, date)
);
```

**Fields:**
- `id` - Unique identifier
- `symbol` - Benchmark ticker (SPY, VT)
- `date` - Price date
- `price` - Closing price
- `created_at` - Creation date

---

## 📝 BlogPost

Stores blog articles.

```sql
CREATE TABLE blog_posts (
    id SERIAL PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    content TEXT NOT NULL,
    excerpt TEXT,
    category VARCHAR(100),
    tags VARCHAR(500),
    meta_description VARCHAR(500),
    meta_keywords VARCHAR(500),
    featured_image_url VARCHAR(500),
    author_id INTEGER REFERENCES users(id),
    is_published BOOLEAN DEFAULT FALSE,
    is_featured BOOLEAN DEFAULT FALSE,
    published_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Fields:**
- `id` - Unique identifier
- `title` - Article title
- `content` - Article body (HTML)
- `excerpt` - Short summary
- `category` - Topic category
- `tags` - Comma-separated tags
- `meta_description` - SEO description
- `meta_keywords` - SEO keywords
- `featured_image_url` - Hero image URL
- `author_id` - Post author
- `is_published` - Published flag
- `is_featured` - Featured on homepage
- `published_at` - Publication date
- `created_at` - Creation date
- `updated_at` - Last update

---

## 💡 Idea & IdeaComment

Public wall feature for sharing investment ideas.

```sql
CREATE TABLE ideas (
    id SERIAL PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    content TEXT NOT NULL,
    ticker_symbol VARCHAR(20),
    author_id INTEGER REFERENCES users(id),
    is_public BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE idea_comments (
    id SERIAL PRIMARY KEY,
    idea_id INTEGER REFERENCES ideas(id),
    author_id INTEGER REFERENCES users(id),
    content TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## 🔍 Common Queries

### Get User's Performance

```sql
SELECT 
    u.full_name,
    COUNT(DISTINCT a.id) as total_analyses,
    AVG(pc.return_pct) as avg_return,
    COUNT(CASE WHEN pc.return_pct > 0 THEN 1 END) * 100.0 / COUNT(*) as win_rate
FROM users u
JOIN analysis_analysts aa ON u.id = aa.user_id
JOIN analyses a ON aa.analysis_id = a.id
LEFT JOIN performance_calculations pc ON a.id = pc.analysis_id
WHERE u.id = :user_id AND a.status = 'Approved'
GROUP BY u.id;
```

### Get Portfolio Performance

```sql
SELECT 
    c.name,
    c.ticker_symbol,
    a.date as analysis_date,
    pc.price_at_buy,
    pc.price_current,
    pc.return_pct
FROM analyses a
JOIN companies c ON a.company_id = c.id
LEFT JOIN performance_calculations pc ON a.id = pc.analysis_id
JOIN board_votes bv ON a.id = bv.analysis_id
WHERE a.status = 'Approved'
GROUP BY a.id
HAVING SUM(CASE WHEN bv.vote = 'Yes' THEN 1 ELSE -1 END) > 0;
```

---

<p align="center">
  <strong>Database schema optimized for financial analysis workflows</strong>
</p>
