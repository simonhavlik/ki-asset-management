# Analyst Performance Tracker - Mathematical Methodology

This document provides a comprehensive explanation of all mathematical calculations used in the Analyst Performance Tracker platform. All formulas are mathematically correct and follow industry-standard financial calculations.

---

## Table of Contents

1. [Return Calculations](#return-calculations)
2. [Performance Aggregation](#performance-aggregation)
3. [Risk Metrics](#risk-metrics)
4. [Benchmark Comparisons](#benchmark-comparisons)
5. [Portfolio Simulation](#portfolio-simulation)
6. [Sector Statistics](#sector-statistics)
7. [Analyst Rankings](#analyst-rankings)
8. [Implementation Details](#implementation-details)

---

## Return Calculations

### Simple Return

**Formula:**
$$
\text{Return\%} = \frac{P_{\text{current}} - P_{\text{analysis}}}{P_{\text{analysis}}} \times 100
$$

**Where:**
- $P_{\text{current}}$ = Latest available closing price
- $P_{\text{analysis}}$ = Closing price on the analysis date

**Example:**
- Analysis Date: January 15, 2025
- Price at Analysis: $150.00
- Current Price: $200.00
- Return = (200 - 150) / 150 × 100 = **33.33%**

**Implementation:**
```python
return_pct = ((price_current - price_at_analysis) / price_at_analysis) * 100
```

**Why This Matters:**
This is the fundamental building block of all performance metrics. It measures the total return from when an analyst recommended a stock until now. We use the closing price on the analysis date (or previous trading day if markets were closed) to ensure consistency.

---

### Annualized Return (CAGR)

**Formula:**
$$
\text{Annualized Return} = \left[(1 + \frac{r}{100})^{\frac{365}{d}} - 1\right] \times 100
$$

**Where:**
- $r$ = Raw return percentage (from simple return calculation)
- $d$ = Number of days held

**When Applied:**
- Only for holdings **longer than 365 days**
- Provides standardized comparison across different holding periods

**Example:**
- Raw Return: 50%
- Days Held: 730 (2 years)
- Annualized = ((1 + 0.50)^(365/730) - 1) × 100 = **22.47% per year**

**Implementation:**
```python
total_return = 1.0 + raw_return_pct / 100.0
years = days / 365.0
annualized_total = total_return ** (1.0 / years)
annualized_pct = (annualized_total - 1.0) * 100.0
```

**Alternative Implementation:**
```python
annualized = ((1 + avg_return / 100) ** (365 / days) - 1) * 100
```

**Why This Matters:**
Annualization allows fair comparison between:
- A stock held for 6 months with 15% return
- A stock held for 2 years with 30% return

Without annualization, the 30% return looks better, but the 15% return in 6 months is actually superior performance (≈30% annualized vs ≈14% annualized).

**Edge Cases Handled:**
- Returns ≤ -100%: Capped at -100% (total loss)
- Zero days held: Returns raw return
- Division by zero: Protected with try-catch

---

## Performance Aggregation

### Arithmetic Mean (Average Return)

**Formula:**
$$
\bar{x} = \frac{1}{n} \sum_{i=1}^{n} x_i
$$

**Where:**
- $\bar{x}$ = Average return
- $n$ = Number of analyses
- $x_i$ = Return of each individual analysis

**Example:**
Analyst has 3 approved analyses:
- Analysis 1: +33%
- Analysis 2: -5%
- Analysis 3: +10%

Average = (33 + (-5) + 10) / 3 = **12.67%**

**Implementation:**
```python
avg = sum(returns) / len(returns)
```

**Rationale for Equal-Weighting:**
We use equal-weighted averages (not value-weighted) because:

1. **Fair Comparison**: Each analyst pick represents equal "conviction" regardless of company size
2. **Skill Measurement**: Measures stock-picking ability, not position sizing
3. **Bias Prevention**: Prevents large-cap stocks from dominating metrics
4. **Industry Standard**: Most analyst performance rankings use equal-weighting

**Real-World Analogy:**
Imagine two analysts:
- Analyst A: Picks Apple (huge gains, but easy pick)
- Analyst B: Picks small unknown companies with consistent 15% gains

Equal-weighting gives proper credit to Analyst B's research skill.

---

### Median Return

**Formula:**

For **odd** number of observations:
$$
\text{Median} = x_{\frac{n+1}{2}}
$$

For **even** number of observations:
$$
\text{Median} = \frac{x_{\frac{n}{2}} + x_{\frac{n}{2}+1}}{2}
$$

**Where:**
- Values are sorted in ascending order
- $n$ = Number of observations

**Example - Odd Count (5 analyses):**
Returns: [-15%, -5%, 10%, 15%, 25%]
Sorted: [-15%, -5%, 10%, 15%, 25%]
Median = **10%** (3rd value)

**Example - Even Count (4 analyses):**
Returns: [-10%, 5%, 15%, 20%]
Median = (5% + 15%) / 2 = **10%**

**Why Use Median:**
- **Outlier Resistance**: Not affected by one extreme outlier
- **Typical Performance**: Shows what a "typical" pick returns
- **Complementary**: Use alongside mean for full picture

**When Median ≠ Mean:**
- Analyst has mostly small gains but one huge winner (Mean > Median)
- Analyst has consistent performance (Mean ≈ Median)
- Analyst has catastrophic loss dragging down average (Median > Mean)

---

### Win Rate

**Formula:**
$$
\text{Win Rate\%} = \frac{\text{Number of Positive Returns}}{\text{Total Number of Returns}} \times 100
$$

**Example:**
- Total analyses: 10
- Positive returns: 7
- Win Rate = 7 / 10 × 100 = **70%**

**Interpretation:**
- **70%+**: Excellent consistency
- **50-70%**: Good, beating coin flip
- **40-50%**: Room for improvement
- **<40%**: Needs strategy review

**Important Note:**
Win rate alone doesn't tell the whole story. An analyst with 40% win rate but +50% average gains on winners and -5% on losers can still be profitable.

---

## Risk Metrics

### Standard Deviation (Volatility)

**Formula:**
$$
\sigma = \sqrt{\frac{1}{N} \sum_{i=1}^{N} (x_i - \bar{x})^2}
$$

**Where:**
- $\sigma$ = Standard deviation (risk/volatility)
- $N$ = Number of observations (population size)
- $x_i$ = Individual return
- $\bar{x}$ = Mean return

**Step-by-Step Calculation:**

Given sector returns: [10%, 15%, -5%, 20%, 0%]

1. **Calculate Mean:**
   $\bar{x} = (10 + 15 + (-5) + 20 + 0) / 5 = 8\%$

2. **Calculate Deviations:**
   - (10 - 8)² = 4
   - (15 - 8)² = 49
   - (-5 - 8)² = 169
   - (20 - 8)² = 144
   - (0 - 8)² = 64

3. **Calculate Variance:**
   $\sigma^2 = (4 + 49 + 169 + 144 + 64) / 5 = 86$

4. **Calculate Standard Deviation:**
   $\sigma = \sqrt{86} = 9.27\%$

**Implementation:**
```python
mean = avg_return
variance = sum((r - mean) ** 2 for r in returns) / len(returns)
risk = variance ** 0.5  # Square root
```

**Why Population Standard Deviation:**
We divide by $N$ (not $N-1$) because:
1. We're treating the observed returns as the complete population of interest
2. We're not trying to estimate a larger population from a sample
3. All our returns are known and fixed

**Interpretation:**

| Risk Level | Standard Deviation | Interpretation |
|-----------|-------------------|----------------|
| Low | 0-5% | Very consistent returns |
| Medium | 5-15% | Normal volatility |
| High | 15-25% | Erratic performance |
| Very High | >25% | Unpredictable results |

**Sector Risk Example:**
- Technology sector: Risk = 18% (high volatility)
- Utilities sector: Risk = 5% (stable, predictable)

This helps identify which sectors are more "predictable" vs "variable" in our portfolio.

---

### Positive Ratio (Sector)

**Formula:**
$$
\text{Positive Ratio\%} = \frac{\text{Number of Positive Returns in Sector}}{\text{Total Analyses in Sector}} \times 100
$$

**Same as Win Rate**, just applied to sector-level data instead of analyst-level.

---

## Benchmark Comparisons

### Benchmark Return Calculation

**Formula:**
$$
\text{Benchmark Return\%} = \frac{P_{\text{end}} - P_{\text{start}}}{P_{\text{start}}} \times 100
$$

**Implemented Benchmarks:**

| Ticker | Index | Description | Approx. Annual Return |
|--------|-------|-------------|---------------------|
| SPY | S&P 500 | 500 largest US companies | ~10% |
| VT | FTSE All-World | Global equity markets | ~9% |
| EEMS | MSCI EM Small Cap | Emerging markets small cap | ~7% |

**Why These Benchmarks:**
1. **SPY**: Standard US large-cap benchmark
2. **VT**: Global diversification comparison
3. **EEMS**: Small-cap/emerging market exposure check

### Alpha Generation

**Formula:**
$$
\alpha = \text{Analyst Return} - \text{Benchmark Return}
$$

**Example:**
- Analyst Average Return: 25%
- SPY Return (same period): 15%
- Alpha = 25% - 15% = **+10%** (outperforming)

**Interpretation:**
- **Positive Alpha**: Beating the benchmark
- **Negative Alpha**: Underperforming (passive investing would be better)
- **Zero Alpha**: Matching the market

---

## Portfolio Simulation

### Portfolio Calculation Methods

We support two portfolio calculation methods:

#### Method 1: Incremental Equal-Weight Rebalancing (Recommended)

This method simulates realistic portfolio management where each new stock addition triggers rebalancing to maintain equal weights.

**How It Works:**

1. **First Stock**: Invest 100% of capital in Stock A
2. **Second Stock**: 
   - Sell 50% of Stock A position (realizing any gains/losses)
   - Use proceeds to buy Stock B
   - Result: 50% A, 50% B
3. **Third Stock**:
   - Sell 33.3% of both A and B positions
   - Use proceeds to buy Stock C
   - Result: 33.3% A, 33.3% B, 33.3% C
4. **Nth Stock**: Rebalance all positions to 1/N weight each

**Mathematical Formula:**

At each rebalancing point when adding the $n$-th stock:

$$
\text{Portfolio}_n = \frac{1}{n} \sum_{i=1}^{n} R_i^{\text{rebalanced}}
$$

Where $R_i^{\text{rebalanced}}$ is the return of position $i$ from its entry date to current date, accounting for position size changes during rebalancing events.

**Example with $10,000 Starting Capital:**

| Step | Action | Stock A Value | Stock B Value | Stock C Value | Total |
|------|--------|---------------|---------------|---------------|-------|
| 1 | Buy A with $10,000 | $10,000 | - | - | $10,000 |
| 2 | A grows 30% | $13,000 | - | - | $13,000 |
| 3 | Add B: rebalance 50/50 | $6,500 | $6,500 | - | $13,000 |
| 4 | A gains 10%, B gains 20% | $7,150 | $7,800 | - | $14,950 |
| 5 | Add C: rebalance 33/33/33 | $4,983 | $4,983 | $4,983 | $14,950 |
| 6 | Final values at exit | $6,000 | $7,500 | $5,500 | $19,000 |

**Portfolio Return**: ($19,000 - $10,000) / $10,000 = **90%**

**Why Incremental Rebalancing:**
- **Realistic**: Mimics actual portfolio management decisions
- **Captures Impact**: Shows effect of rebalancing and position sizing
- **Early Position Bias**: Early positions have larger impact (as in reality)
- **Opportunity Cost**: Reflects cost of adding new positions to the portfolio

---

#### Method 2: Simple Equal-Weighted Average

This method calculates a simple arithmetic average where each stock contributes equally regardless of when it was added.

**Formula:**
$$
R_{\text{portfolio}} = \frac{1}{n} \sum_{i=1}^{n} R_i
$$

**Where:**
- $R_{\text{portfolio}}$ = Portfolio return
- $n$ = Number of positions
- $R_i$ = Return of each position from entry to current date

**Example:**
Portfolio with 3 stocks:
- Stock A: +30% (entered 2 years ago)
- Stock B: +10% (entered 1 year ago)
- Stock C: -5% (entered 6 months ago)

Portfolio Return = (30 + 10 + (-5)) / 3 = **11.67%**

**Time-Weighted Interpretation:**
The portfolio return at any point in time includes only stocks that have been entered:

| Date | Active Stocks | Calculation | Portfolio Return |
|------|--------------|-------------|------------------|
| Jan 2023 | Stock A only | 30% | 30% |
| Jun 2023 | A, B | (30+10)/2 | 20% |
| Jan 2024 | A, B, C | (30+10-5)/3 | 11.67% |

**Why Equal-Weighting:**
- **Fair Comparison**: Removes position sizing as a factor
- **Skill Measurement**: Pure stock selection ability
- **Industry Standard**: Most analyst rankings use this method
- **Simple**: Easy to understand and calculate

**Real-World Example:**
$10,000 invested equally at portfolio inception:
- $3,333 in Stock A → +30% = $999 profit
- $3,333 in Stock B → +10% = $333 profit
- $3,333 in Stock C → -5% = $167 loss
- **Total Return**: ($999 + $333 - $167) / $10,000 = 11.65% ≈ 11.67%

---

### Which Method to Use?

| Method | Best For | Pros | Cons |
|--------|----------|------|------|
| **Incremental Rebalancing** | Portfolio performance tracking | Realistic, captures rebalancing effects | More complex, early positions dominate |
| **Equal-Weighted** | Analyst skill comparison | Simple, fair comparison, industry standard | Ignores portfolio management timing |

**Recommendation:**
- Use **Incremental Rebalancing** on the main page and for portfolio performance charts
- Use **Equal-Weighted** when comparing analyst stock-picking skill without portfolio management effects

---

### Cumulative Series Calculation

**Method:**
Track the portfolio value over time using the selected calculation method:

**For Incremental Rebalancing:**
1. **First Pick**: 100% in first stock
2. **Second Pick**: Rebalance to 50/50
3. **Third Pick**: Rebalance to 33/33/33
4. Continue rebalancing at each addition

**For Equal-Weighted:**
1. **First Pick**: Portfolio = That stock's performance
2. **Second Pick**: Portfolio = Average of both stocks
3. **Third Pick**: Portfolio = Average of all three

**Implementation:**
```python
running_total += item['return']
count += 1
avg_return = running_total / count
```

**Visualization:**
```
Return %
   40% |         /\
   30% |        /  \
   20% |       /    \
   10% |______/      \____
    0% +-------------------> Time
         A    B    C    D

A: First stock added (portfolio = Stock 1 return)
B: Second stock added (portfolio = avg of 1 & 2)
C: Third stock added (portfolio = avg of 1, 2 & 3)
D: Current date (portfolio = avg of all active positions)
```

---

## Sector Statistics

### Sector Aggregation

For each sector, we calculate:

1. **Count**: Number of stocks in the sector
2. **Average Return**: Mean of all returns in sector
3. **Positive Ratio**: % of stocks with positive returns
4. **Risk**: Standard deviation of sector returns
5. **Min Return**: Worst performing stock in sector
6. **Max Return**: Best performing stock in sector

### Sector Risk Ranking

**Formula:** Same standard deviation as above, grouped by sector

**Interpretation:**

| Sector | Risk | Interpretation |
|--------|------|----------------|
| Technology | High | Volatile, boom-bust cycles |
| Healthcare | Medium | Regulatory impacts |
| Utilities | Low | Stable, regulated returns |
| Financials | Medium-High | Economic sensitivity |

**Use Case:**
Identifies which sectors provide:
- **Consistent Performance**: Low risk sectors
- **High Reward Potential**: High return sectors (but check risk)
- **Balanced Exposure**: Medium risk/return sectors

---

## Analyst Rankings

### Top Board Approved

**Formula:** Count of analyses with `status = 'On Watchlist'`

**Interpretation:** Most prolific analysts by approved stock count

### Top Total Analyses

**Formula:** Count of all stock analyses (On Watchlist + Neutral + Refused)

**Interpretation:** Most active analysts by total coverage

### Top Win Rate

**Formula:** Win rate calculation (see above) with minimum 3 analyses

**Filter:** Only analysts with ≥3 analyses (statistical significance)

**Interpretation:** Most consistent analysts at picking winners

### Top Performance

**Formula:** Average return across all approved analyses

**Interpretation:** Highest returning analysts (absolute performance)

---

## Implementation Details

### Data Flow

```
1. Analysis Created
   ↓
2. Price Data Fetched (Yahoo Finance)
   ↓
3. Simple Return Calculated
   ↓
4. Stored in PerformanceCalculations table
   ↓
5. Aggregated for Analyst/Portfolio/Display
```

### Price Handling

**Price at Analysis Date:**
- Use closing price on exact date
- If market closed: Use previous trading day
- If no data available: Skip calculation (log warning)

**Current Price:**
- Latest available closing price
- Updated daily via background job
- If delisted: Use last available price

### Cache Strategy

**Why Caching Matters:**
- Stock prices don't change intraday for historical calculations
- Prevents API rate limiting
- Faster page loads

**Cache Duration:**
- Stock prices: 1 day
- Sector info: 3 days
- Performance calculations: Calculated on-demand but stored persistently

### Edge Cases

| Scenario | Handling |
|----------|----------|
| Missing ticker | Skip analysis, log warning |
| Missing price data | Skip calculation, admin can see which |
| Delisted stock | Use last available price |
| Zero price | Skip (division by zero protection) |
| -100% return | Capped, cannot annualize |
| Future analysis date | Exclude from calculations |

---

## Formula Summary

### Quick Reference

| Metric | Formula | Code Location |
|--------|---------|---------------|
| **Simple Return** | $\frac{P_{current} - P_{entry}}{P_{entry}} \times 100$ | `performance.py:209` |
| **Annualized Return** | $\left[(1 + \frac{r}{100})^{\frac{365}{d}} - 1\right] \times 100$ | `performance.py:102` |
| **Average Return** | $\frac{\sum returns}{n}$ | `performance.py:302` |
| **Median** | Middle value (or avg of two middles) | `performance.py:303` |
| **Win Rate** | $\frac{\text{positive}}{\text{total}} \times 100$ | `performance.py:305` |
| **Standard Deviation** | $\sqrt{\frac{\sum(x_i - \bar{x})^2}{N}}$ | `analyst/routes.py:381` |
| **Portfolio Return** | $\frac{\sum \text{individual returns}}{n}$ | `performance.py:471` |

---

## Glossary

- **Alpha**: Excess return above benchmark
- **Annualized**: Return normalized to one-year period
- **CAGR**: Compound Annual Growth Rate (same as annualized return)
- **Equal-Weighted**: Each position contributes equally (vs. value-weighted)
- **Median**: Middle value in sorted list
- **Population Std Dev**: Standard deviation using all data points
- **Risk**: Measured as standard deviation of returns
- **Win Rate**: Percentage of positive-returning picks

---

## References

1. **CAGR Formula**: [Investopedia - CAGR](https://www.investopedia.com/terms/c/cagr.asp)
2. **Standard Deviation**: [Khan Academy - Statistics](https://www.khanacademy.org/math/statistics-probability)
3. **Equal-Weighted Portfolios**: [CFA Institute](https://www.cfainstitute.org/)
4. **Benchmark Selection**: [Morningstar Methodology](https://www.morningstar.com/)

---

**Last Updated:** February 2026  
**Version:** 1.0  
**Maintainer:** Analyst Performance Tracker Team
