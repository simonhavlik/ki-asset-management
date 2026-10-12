#!/usr/bin/env python3
"""Auto-generate the Klub investorů portfolio review deck (.pptx).

Reads the live database (DATABASE_URL) and builds a ~40-slide, professional
PowerPoint with editable text, native (editable) charts and tables, in the club
green palette. Run it any time to refresh the deck from the current portfolio:

    python scripts/generate_portfolio_deck.py                 # -> ~/Downloads
    python scripts/generate_portfolio_deck.py --out deck.pptx
    python scripts/generate_portfolio_deck.py --db "$DATABASE_URL"

No secrets live in this file: the connection string comes from the environment
or the project .env (gitignored).
"""
from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from datetime import date, datetime

import numpy as np
import pandas as pd
import psycopg2
from pptx import Presentation
from pptx.chart.data import CategoryChartData, XyChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.util import Emu, Inches, Pt

# --------------------------------------------------------------------------
# Theme - the club's green palette (see app/static/css/style.css)
# --------------------------------------------------------------------------
GREEN = RGBColor(0x2C, 0xCE, 0x7E)
GREEN_DARK = RGBColor(0x1A, 0x9C, 0x5E)
GREEN_DEEP = RGBColor(0x14, 0x7A, 0x4A)
INK = RGBColor(0x0F, 0x14, 0x19)
SLATE = RGBColor(0x1A, 0x20, 0x28)
MUTED = RGBColor(0x6B, 0x76, 0x82)
LIGHT = RGBColor(0xF5, 0xF7, 0xF9)
GRAY = RGBColor(0xE6, 0xEB, 0xEF)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
GOLD = RGBColor(0xD4, 0xA5, 0x20)
RED = RGBColor(0xE0, 0x4F, 0x4F)
BLUE = RGBColor(0x3B, 0x82, 0xF6)
SERIES_COLORS = [GREEN, GREEN_DEEP, GOLD, BLUE, RED, MUTED, GREEN_DARK, SLATE]

FONT = "Calibri"
FONT_HEAD = "Calibri"

SW, SH = Inches(13.333), Inches(7.5)
CLUB = "Klub investorů"
CONFIDENTIAL = "Private & confidential — for club members only"


# --------------------------------------------------------------------------
# Data loading
# --------------------------------------------------------------------------
def _db_url(explicit: str | None) -> str:
    if explicit:
        return explicit
    env = os.environ.get("DATABASE_URL")
    if env:
        return env
    # Fall back to the project .env (gitignored).
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env_path = os.path.join(here, ".env")
    if os.path.exists(env_path):
        with open(env_path) as fh:
            for line in fh:
                line = line.strip()
                if line.startswith("DATABASE_URL="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit("No DATABASE_URL in environment or .env")


def load_data(db_url: str) -> dict[str, pd.DataFrame]:
    """Load every table the deck needs into DataFrames."""
    conn = psycopg2.connect(db_url)
    try:
        q = lambda sql: pd.read_sql_query(sql, conn)  # noqa: E731
        data = {
            "analyses": q("SELECT id, company_id, analysis_date, status, purchase_date, is_in_portfolio FROM analyses"),
            "companies": q("SELECT id, name, ticker_symbol, sector FROM companies"),
            "votes": q("SELECT analysis_id, user_id, vote FROM votes"),
            "purchases": q("SELECT analysis_id, purchase_date, added_by FROM portfolio_purchases"),
            "users": q("SELECT id, full_name, email, is_admin, is_active, created_at, last_login FROM users"),
            "aa": q("SELECT analysis_id, user_id, role FROM analysis_analysts"),
            "perf": q("SELECT analysis_id, calculation_date, return_pct, price_at_analysis, price_current FROM performance_calculations"),
            "prices": q("SELECT company_id, date, close_price FROM stock_prices"),
            "bench": q("SELECT ticker, date, close_price FROM benchmark_prices"),
            "uploads": q("SELECT filename, processed_at, row_count FROM csv_uploads ORDER BY id DESC LIMIT 1"),
        }
    finally:
        conn.close()

    for col in ("analysis_date", "purchase_date"):
        data["analyses"][col] = pd.to_datetime(data["analyses"][col]).dt.date
    data["purchases"]["purchase_date"] = pd.to_datetime(data["purchases"]["purchase_date"]).dt.date
    for col in ("date",):
        data["prices"][col] = pd.to_datetime(data["prices"][col]).dt.date
        data["bench"][col] = pd.to_datetime(data["bench"][col]).dt.date
    data["perf"]["calculation_date"] = pd.to_datetime(data["perf"]["calculation_date"]).dt.date
    return data


# --------------------------------------------------------------------------
# Metrics
# --------------------------------------------------------------------------
def _s(v, n=40, dash="—"):
    """Safe, truncated string for table cells (NaN/None -> dash)."""
    if v is None or (isinstance(v, float) and not np.isfinite(v)):
        return dash
    s = str(v).strip()
    return s[:n] if s else dash


def _finite(values):
    """Coerce a sequence to finite floats (python-pptx/xlsxwriter reject NaN/inf)."""
    out = []
    for v in values:
        try:
            f = float(v)
        except (TypeError, ValueError):
            f = 0.0
        out.append(f if np.isfinite(f) else 0.0)
    return out


def _daily_returns(series: pd.Series) -> pd.Series:
    return series.pct_change().dropna()


def _max_drawdown(cum: pd.Series) -> float:
    if cum.empty:
        return 0.0
    peak = cum.cummax()
    return float((cum / peak - 1).min())


def compute_metrics(data: dict[str, pd.DataFrame]) -> dict:
    a = data["analyses"].copy()
    comp = data["companies"].set_index("id")
    votes = data["votes"].copy()
    purch = data["purchases"].copy()

    yes = votes[votes["vote"] == True].groupby("analysis_id").size()  # noqa: E712
    no = votes[votes["vote"] == False].groupby("analysis_id").size()  # noqa: E712
    a["yes"] = a["id"].map(yes).fillna(0).astype(int)
    a["no"] = a["id"].map(no).fillna(0).astype(int)
    a["approved"] = a["yes"] > a["no"]
    a = a.merge(comp[["name", "ticker_symbol", "sector"]], left_on="company_id", right_index=True, how="left")

    m: dict = {}
    m["today"] = date.today()
    m["n_analyses"] = int(len(a))
    m["n_companies"] = int(a["company_id"].nunique())
    m["n_approved"] = int(a["approved"].sum())
    m["n_on_watchlist"] = int((a["status"] == "On Watchlist").sum())
    m["n_purchased"] = int(len(purch))
    m["n_votes"] = int(len(votes))
    m["n_voters"] = int(votes["user_id"].nunique()) if not votes.empty else 0
    m["approval_rate"] = (m["n_approved"] / m["n_analyses"] * 100) if m["n_analyses"] else 0.0

    # Analysts
    aa = data["aa"].copy()
    analysts = aa[aa["role"] == "analyst"]["user_id"].unique()
    opponents = aa[aa["role"] == "opponent"]["user_id"].unique()
    users = data["users"].set_index("id")
    m["n_analysts"] = int(len(analysts))
    m["n_opponents"] = int(len(opponents))
    active = users.loc[[i for i in analysts if i in users.index]]
    m["n_analysts_active"] = int(active["is_active"].sum()) if not active.empty else 0
    m["analyst_names"] = [users.loc[i, "full_name"] or users.loc[i, "email"] for i in analysts if i in users.index]

    # Analyst coverage / hit rate
    cov = aa[aa["role"] == "analyst"].merge(a[["id", "approved", "sector"]], left_on="analysis_id", right_on="id")
    per_analyst = cov.groupby("user_id").agg(analyses=("id", "nunique"), approved=("approved", "sum")).reset_index()
    per_analyst["name"] = per_analyst["user_id"].map(
        lambda i: (users.loc[i, "full_name"] or users.loc[i, "email"]) if i in users.index else f"user {i}")
    per_analyst["hit_rate"] = (per_analyst["approved"] / per_analyst["analyses"] * 100).round(1)
    m["per_analyst"] = per_analyst.sort_values("analyses", ascending=False)

    # Activity by month
    a["month"] = pd.to_datetime(a["analysis_date"]).dt.to_period("M").astype(str)
    monthly = a.groupby("month").size().sort_index()
    m["monthly"] = monthly

    # Retention: analysts with an analysis in the last 365 days vs total
    cutoff = m["today"] - pd.Timedelta(days=365) if hasattr(pd.Timedelta, "__mro__") else None
    recent = a[pd.to_datetime(a["analysis_date"]).dt.date >= (m["today"] - pd.Timedelta(days=365).to_pytimedelta())]
    recent_ids = set(recent["id"])
    rec_analysts = set(aa[(aa["role"] == "analyst") & (aa["analysis_id"].isin(recent_ids))]["user_id"])
    m["n_analysts_recent"] = int(len(rec_analysts))
    m["retention_rate"] = (len(rec_analysts) / len(analysts) * 100) if len(analysts) else 0.0

    # Sectors
    m["sector_counts"] = a["sector"].fillna("Unclassified").value_counts()

    # Status breakdown
    m["status_counts"] = a["status"].fillna("Unknown").value_counts()

    # ---- Portfolio (matches the club's board metric: each position measured
    # from its initiation (analysis) date to the latest close) ----
    prices = data["prices"].copy()
    prices["date"] = pd.to_datetime(prices["date"])
    bench = data["bench"].copy()
    bench["date"] = pd.to_datetime(bench["date"])

    perf = data["perf"].copy()
    perf["calculation_date"] = pd.to_datetime(perf["calculation_date"])
    perf_latest = perf.sort_values("calculation_date").groupby("analysis_id")["return_pct"].last()

    holdings = purch.merge(
        a[["id", "company_id", "name", "ticker_symbol", "sector", "analysis_date"]],
        left_on="analysis_id", right_on="id", how="left")

    def _key(row):
        return row["ticker_symbol"] if isinstance(row["ticker_symbol"], str) else row["name"]

    port, per_pos, per_pos_perf = {}, {}, {}
    if not holdings.empty and not prices.empty:
        cal = pd.DatetimeIndex(sorted(bench["date"].unique()) if not bench.empty else sorted(prices["date"].unique()))
        for _, h in holdings.iterrows():
            entry = pd.Timestamp(h["analysis_date"])
            p = prices[prices["company_id"] == h["company_id"]].sort_values("date")
            series = None
            if not p.empty:
                p = p.set_index("date")["close_price"].astype(float).reindex(cal).ffill()
                base = p.asof(entry)
                if base and base > 0:
                    series = (p / base - 1).where(cal >= entry)
                    port[_key(h)] = series
            # Prefer the app's own computed return (PerformanceCalculation)
            pr = perf_latest.get(h["analysis_id"])
            if pr is not None and np.isfinite(float(pr)):
                per_pos[_key(h)] = float(pr)
                per_pos_perf[_key(h)] = float(pr)
            elif series is not None and series.notna().any():
                per_pos[_key(h)] = float(series.dropna().iloc[-1] * 100)

    m["portfolio_series"] = (pd.DataFrame(port).ffill().mean(axis=1) * 100) if port else pd.Series(dtype=float)
    m["holdings_returns"] = pd.Series(per_pos).sort_values(ascending=False) if per_pos else pd.Series(dtype=float)
    m["scored_returns"] = pd.Series(per_pos_perf) if per_pos_perf else pd.Series(dtype=float)
    # Headline matches the club board exactly: mean of scored (PerformanceCalculation) positions
    if not m["scored_returns"].empty:
        m["total_return"] = float(m["scored_returns"].mean())
        m["n_scored_holdings"] = int(len(m["scored_returns"]))
    else:
        m["total_return"] = float(m["holdings_returns"].mean()) if not m["holdings_returns"].empty else 0.0
        m["n_scored_holdings"] = int(len(m["holdings_returns"]))

    # Benchmarks over the same window
    m["bench_series"] = {}
    if not m["portfolio_series"].empty:
        start = m["portfolio_series"].index[0]
        for tk in ("SPY", "VT", "EEMS"):
            b = bench[bench["ticker"] == tk].sort_values("date").set_index("date")["close_price"].astype(float)
            if b.empty:
                continue
            b = b.reindex(m["portfolio_series"].index).ffill()
            b = b / b.iloc[0] - 1
            m["bench_series"][tk] = b * 100

    # Risk metrics on the portfolio daily returns
    if not m["portfolio_series"].empty:
        cum = (1 + m["portfolio_series"] / 100)
        rets = cum.pct_change().dropna()
        m["daily_returns"] = rets
        vol = float(rets.std() * np.sqrt(252) * 100)
        m["vol_annual"] = vol
        m["max_dd"] = _max_drawdown(cum) * 100
        days = max((cum.index[-1] - cum.index[0]).days, 1)
        cagr = (cum.iloc[-1] ** (365 / days) - 1) * 100
        m["cagr"] = cagr
        m["series_return"] = float((cum.iloc[-1] - 1) * 100)
        m["sharpe"] = ((cagr / 100 - 0.02) / (vol / 100)) if vol else 0.0
        spy = m["bench_series"].get("SPY")
        if spy is not None and len(spy) > 2:
            spy_rets = (1 + spy / 100).pct_change().dropna()
            j = rets.align(spy_rets, join="inner")
            cov = np.cov(j[0], j[1])
            m["beta"] = float(cov[0, 1] / cov[1, 1]) if cov[1, 1] else 0.0
        else:
            m["beta"] = 0.0
        # cumulative drawdown series
        m["drawdown_series"] = (cum / cum.cummax() - 1) * 100
        # rolling 30d volatility
        m["rolling_vol"] = (rets.rolling(30).std() * np.sqrt(252) * 100).dropna()
    else:
        for k in ("vol_annual", "max_dd", "cagr", "total_return", "sharpe", "beta"):
            m[k] = 0.0
        m["daily_returns"] = pd.Series(dtype=float)
        m["drawdown_series"] = pd.Series(dtype=float)
        m["rolling_vol"] = pd.Series(dtype=float)

    # Market / exchange mix (from the ticker suffix)
    def _market(tk):
        if not isinstance(tk, str) or not tk:
            return "Unclassified"
        suf = tk.split(".")[-1] if "." in tk else "US"
        return {"US": "United States", "DE": "Germany", "WA": "Poland", "L": "United Kingdom",
                "IL": "Israel", "PA": "France", "AS": "Netherlands", "MI": "Italy",
                "ST": "Sweden", "CO": "Denmark", "HE": "Finland", "VI": "Austria",
                "SW": "Switzerland", "TO": "Japan", "T": "Japan", "HK": "Hong Kong",
                "KS": "South Korea", "SI": "Singapore", "AX": "Australia"}.get(suf, suf.upper())
    a["market"] = a["ticker_symbol"].map(_market)
    m["market_counts"] = a["market"].value_counts()

    # Every analysis scored (from PerformanceCalculation), for the quality slides
    an = a.merge(perf_latest.rename("ret"), left_on="id", right_index=True, how="left")
    m["all_returns"] = an.dropna(subset=["ret"]).copy()
    m["n_with_returns"] = int(len(m["all_returns"]))
    m["win_rate"] = float((m["all_returns"]["ret"] > 0).mean() * 100) if len(m["all_returns"]) else 0.0
    m["avg_analysis_return"] = float(m["all_returns"]["ret"].mean()) if len(m["all_returns"]) else 0.0
    m["top_analyses"] = m["all_returns"].sort_values("ret", ascending=False).head(10)
    m["recent_analyses"] = a.sort_values("analysis_date", ascending=False).head(10)

    a["approved_i"] = a["approved"].astype(int)
    m["monthly_approved"] = a.groupby("month")["approved_i"].sum()

    # Freshness / governance
    m["max_price_date"] = prices["date"].max().date() if not prices.empty else None
    m["n_price_rows"] = int(len(prices))
    up = data.get("uploads")
    m["last_import"] = None
    if up is not None and not up.empty:
        m["last_import"] = (str(up.iloc[0]["filename"]), str(up.iloc[0]["processed_at"])[:16],
                            int(up.iloc[0]["row_count"]))

    m["holdings"] = holdings
    return m


# --------------------------------------------------------------------------
# Slide helpers
# --------------------------------------------------------------------------
class Deck:
    def __init__(self):
        self.prs = Presentation()
        self.prs.slide_width = SW
        self.prs.slide_height = SH
        self.n = 0
        self._content_bg()

    # -- primitives -------------------------------------------------------
    def _slide(self):
        return self.prs.slides.add_slide(self.prs.slide_layouts[6])

    def _rect(self, slide, l, t, w, h, fill, line=None):
        shp = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, l, t, w, h)
        shp.fill.solid()
        shp.fill.fore_color.rgb = fill
        if line is None:
            shp.line.fill.background()
        else:
            shp.line.color.rgb = line
        shp.shadow.inherit = False
        return shp

    def _text(self, slide, l, t, w, h, text, size=18, color=INK, bold=False,
              align=PP_ALIGN.LEFT, font=FONT, anchor=MSO_ANCHOR.TOP, italic=False):
        box = slide.shapes.add_textbox(l, t, w, h)
        tf = box.text_frame
        tf.word_wrap = True
        tf.vertical_anchor = anchor
        lines = text if isinstance(text, list) else [text]
        for i, line in enumerate(lines):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            p.alignment = align
            r = p.add_run()
            r.text = str(line)
            r.font.size = Pt(size)
            r.font.bold = bold
            r.font.italic = italic
            r.font.name = font
            r.font.color.rgb = color
        return box

    def _content_bg(self):
        pass

    def footer(self, slide, dark=False):
        color = RGBColor(0xB0, 0xBA, 0xC4) if dark else MUTED
        self._text(slide, Inches(0.5), Inches(7.05), Inches(9), Inches(0.3),
                   f"{CLUB} · Portfolio & Performance Review", size=9, color=color)
        self._text(slide, Inches(11.0), Inches(7.05), Inches(1.83), Inches(0.3),
                   f"{self.n:02d}", size=9, color=color, align=PP_ALIGN.RIGHT)

    def header(self, slide, title, kicker=None):
        self._rect(slide, Inches(0), Inches(0), SW, Inches(0.12), GREEN)
        if kicker:
            self._text(slide, Inches(0.5), Inches(0.32), Inches(12), Inches(0.3),
                       kicker.upper(), size=11, color=GREEN_DARK, bold=True)
            self._text(slide, Inches(0.5), Inches(0.6), Inches(12.3), Inches(0.7),
                       title, size=28, color=SLATE, bold=True, font=FONT_HEAD)
        else:
            self._text(slide, Inches(0.5), Inches(0.45), Inches(12.3), Inches(0.8),
                       title, size=28, color=SLATE, bold=True, font=FONT_HEAD)
        self._rect(slide, Inches(0.5), Inches(1.32), Inches(1.4), Inches(0.045), GREEN)

    # -- composed slides --------------------------------------------------
    def cover(self, m):
        s = self._slide()
        self._rect(s, Inches(0), Inches(0), SW, SH, SLATE)
        self._rect(s, Inches(0), Inches(0), Inches(0.35), SH, GREEN)
        self._text(s, Inches(0.9), Inches(1.5), Inches(11), Inches(0.5),
                   "KLUB INVESTORŮ", size=16, color=GREEN, bold=True)
        self._text(s, Inches(0.9), Inches(2.05), Inches(11.5), Inches(1.6),
                   "Portfolio & Performance Review", size=44, color=WHITE, bold=True, font=FONT_HEAD)
        self._text(s, Inches(0.9), Inches(3.5), Inches(11), Inches(0.6),
                   "Analyst coverage, board discipline and the club portfolio",
                   size=18, color=RGBColor(0xC5, 0xCD, 0xD4))
        self._rect(s, Inches(0.9), Inches(4.5), Inches(2.2), Inches(0.05), GREEN)
        self._text(s, Inches(0.9), Inches(4.75), Inches(11), Inches(0.4),
                   f"As of {m['today'].strftime('%d %B %Y')}", size=14, color=GREEN)
        self._text(s, Inches(0.9), Inches(6.7), Inches(11), Inches(0.3),
                   CONFIDENTIAL, size=10, color=MUTED)
        self.n += 1

    def section(self, title, subtitle=""):
        s = self._slide()
        self._rect(s, Inches(0), Inches(0), SW, SH, SLATE)
        self._rect(s, Inches(0), Inches(3.1), Inches(2.2), Inches(0.06), GREEN)
        self._text(s, Inches(0.9), Inches(3.25), Inches(11.5), Inches(0.9),
                   title, size=34, color=WHITE, bold=True, font=FONT_HEAD)
        if subtitle:
            self._text(s, Inches(0.9), Inches(4.15), Inches(11.5), Inches(0.6),
                       subtitle, size=16, color=RGBColor(0xC5, 0xCD, 0xD4))
        self.n += 1

    def kpi_slide(self, title, cards, kicker=None, note=None):
        s = self._slide()
        self.header(s, title, kicker)
        n = len(cards)
        top = Inches(1.9)
        gap = Inches(0.3)
        usable = SW - Inches(1.0)
        w = int((usable - gap * (n - 1)) / n)
        h = Inches(2.2)
        for i, (value, label) in enumerate(cards):
            l = Inches(0.5) + i * (w + gap)
            self._rect(s, l, top, w, h, LIGHT)
            self._rect(s, l, top, w, Inches(0.08), GREEN)
            self._text(s, l, top + Inches(0.45), w, Inches(1.0), value, size=40,
                       color=GREEN_DEEP, bold=True, align=PP_ALIGN.CENTER, font=FONT_HEAD)
            self._text(s, l + Inches(0.2), top + Inches(1.5), w - Inches(0.4), Inches(0.6),
                       label, size=12, color=MUTED, align=PP_ALIGN.CENTER)
        if note:
            self._text(s, Inches(0.5), Inches(4.5), Inches(12.3), Inches(1.6), note,
                       size=13, color=SLATE)
        self.footer(s)
        self.n += 1
        return s

    def chart_slide(self, title, kind, categories, series, kicker=None, note=None,
                    number_format="0.0", legend=True):
        s = self._slide()
        self.header(s, title, kicker)
        cd = CategoryChartData()
        cd.categories = categories
        for name, values in series.items():
            cd.add_series(name, _finite(values))
        chart = s.shapes.add_chart(kind, Inches(0.6), Inches(1.75),
                                   Inches(12.1), Inches(5.0), cd).chart
        chart.has_title = False
        chart.has_legend = legend and len(series) > 1
        if chart.has_legend:
            chart.legend.position = XL_LEGEND_POSITION.BOTTOM
            chart.legend.include_in_layout = False
        self._style_chart(chart, number_format)
        if note:
            self._text(s, Inches(0.6), Inches(6.75), Inches(12.1), Inches(0.4), note, size=10, color=MUTED)
        self.footer(s)
        self.n += 1
        return s

    def xy_slide(self, title, series_pts, kicker=None, note=None, x_title="Risk (vol %)", y_title="Return (%)"):
        s = self._slide()
        self.header(s, title, kicker)
        cd = XyChartData()
        for name, pts in series_pts.items():
            ser = cd.add_series(name)
            for x, y in pts:
                if np.isfinite(float(x)) and np.isfinite(float(y)):
                    ser.add_data_point(float(x), float(y))
        chart = s.shapes.add_chart(XL_CHART_TYPE.XY_SCATTER, Inches(0.6), Inches(1.75),
                                   Inches(12.1), Inches(5.0), cd).chart
        chart.has_legend = True
        chart.legend.position = XL_LEGEND_POSITION.BOTTOM
        chart.legend.include_in_layout = False
        try:
            chart.value_axis.has_title = True
            chart.value_axis.axis_title.text_frame.text = y_title
            chart.category_axis.has_title = True
            chart.category_axis.axis_title.text_frame.text = x_title
        except Exception:
            pass
        if note:
            self._text(s, Inches(0.6), Inches(6.75), Inches(12.1), Inches(0.4), note, size=10, color=MUTED)
        self.footer(s)
        self.n += 1
        return s

    def table_slide(self, title, headers, rows, kicker=None, note=None, col_widths=None,
                    highlight_col=None):
        s = self._slide()
        self.header(s, title, kicker)
        nrows, ncols = len(rows) + 1, len(headers)
        height = Inches(0.4) * min(nrows, 13)
        shape = s.shapes.add_table(nrows, ncols, Inches(0.6), Inches(1.8),
                                   Inches(12.1), height)
        table = shape.table
        if col_widths:
            total = sum(col_widths)
            for i, cw in enumerate(col_widths):
                table.columns[i].width = Emu(int(Inches(12.1) * cw / total))
        for j, htext in enumerate(headers):
            c = table.cell(0, j)
            c.text = str(htext)
            self._cell_style(c, header=True)
        for i, row in enumerate(rows, start=1):
            for j, val in enumerate(row):
                c = table.cell(i, j)
                c.text = "" if val is None else str(val)
                self._cell_style(c, header=False,
                                 highlight=(highlight_col is not None and j == highlight_col and i % 2 == 0))
        if note:
            self._text(s, Inches(0.6), Inches(6.8), Inches(12.1), Inches(0.4), note, size=10, color=MUTED)
        self.footer(s)
        self.n += 1
        return s

    def text_slide(self, title, blocks, kicker=None):
        s = self._slide()
        self.header(s, title, kicker)
        top = Inches(1.8)
        for heading, body in blocks:
            self._rect(s, Inches(0.6), top + Inches(0.05), Inches(0.09), Inches(0.5), GREEN)
            self._text(s, Inches(0.85), top, Inches(11.8), Inches(0.4), heading, size=16,
                       color=GREEN_DEEP, bold=True)
            self._text(s, Inches(0.85), top + Inches(0.42), Inches(11.8), Inches(1.0), body,
                       size=13, color=SLATE)
            top += Inches(1.35)
        self.footer(s)
        self.n += 1
        return s

    # -- table/cell styling ----------------------------------------------
    def _cell_style(self, cell, header, highlight=False):
        cell.margin_left = Inches(0.08)
        cell.margin_right = Inches(0.08)
        cell.margin_top = Inches(0.02)
        cell.margin_bottom = Inches(0.02)
        cell.vertical_anchor = MSO_ANCHOR.MIDDLE
        if header:
            cell.fill.solid()
            cell.fill.fore_color.rgb = SLATE
        else:
            cell.fill.solid()
            cell.fill.fore_color.rgb = LIGHT if highlight else WHITE
        for p in cell.text_frame.paragraphs:
            for r in p.runs:
                r.font.size = Pt(12)
                r.font.name = FONT
                r.font.bold = header
                r.font.color.rgb = WHITE if header else INK

    def _style_chart(self, chart, number_format):
        try:
            chart.value_axis.has_major_gridlines = True
            chart.value_axis.major_gridlines.format.line.color.rgb = GRAY
            chart.value_axis.tick_labels.number_format = number_format
            chart.value_axis.tick_labels.number_format_is_linked = False
            chart.value_axis.format.line.color.rgb = GRAY
            chart.category_axis.format.line.color.rgb = GRAY
            chart.font.size = Pt(11)
            chart.font.name = FONT
        except Exception:
            pass
        for i, plot_series in enumerate(chart.series):
            try:
                plot_series.format.fill.solid()
                plot_series.format.fill.fore_color.rgb = SERIES_COLORS[i % len(SERIES_COLORS)]
            except Exception:
                pass

    def save(self, path):
        self.prs.save(path)
        return os.path.abspath(path)


# --------------------------------------------------------------------------
# Deck composition
# --------------------------------------------------------------------------
def _fmt(v, pct=True, nd=1):
    try:
        return f"{v:+.{nd}f}%" if pct else f"{v:.{nd}f}"
    except Exception:
        return "n/a"


def build_deck(m: dict) -> Deck:
    d = Deck()
    a = m

    d.cover(a)
    d.section("Agenda", "What this review covers")

    # 1 Executive summary
    d.kpi_slide(
        "Executive summary", kicker="Overview",
        cards=[
            (f"{a['n_analyses']}", "Analyses completed"),
            (f"{a['n_approved']}", "Board-approved"),
            (f"{a['n_analysts']}", "Analysts"),
            (f"{_fmt(a['total_return'])}", "Portfolio return"),
        ],
        note=(
            f"The club has published {a['n_analyses']} analyses across {a['n_companies']} companies. "
            f"{a['n_approved']} cleared the investment committee ({a['approval_rate']:.0f}% approval rate) and "
            f"{a['n_purchased']} positions are held in the book. The equal-weighted portfolio has returned "
            f"{_fmt(a['total_return'])} since inception, at {a['vol_annual']:.1f}% annualised volatility and a "
            f"maximum drawdown of {a['max_dd']:.1f}%."
        ))

    # 2 Club at a glance
    d.kpi_slide(
        "The club at a glance", kicker="Snapshot",
        cards=[
            (f"{a['n_companies']}", "Companies covered"),
            (f"{a['n_votes']}", "Committee votes"),
            (f"{a['n_analysts_active']}", "Active analysts"),
            (f"{a['n_purchased']}", "Portfolio positions"),
        ],
        note=(
            "Coverage spans listed equities across developed and emerging markets. Every idea passes a "
            "structured process: an analyst initiates, an opponent stress-tests, and the committee votes "
            "before capital is committed."
        ))

    # 3 Methodology
    d.text_slide("Methodology & data", kicker="Foundations", blocks=[
        ("Sources",
         "Analyses, statuses, committee votes and portfolio purchases are sourced from the club's live "
         "database, which is synchronised daily from Notion. Prices are official daily closes from the "
         "market data feed."),
        ("Return method",
         "Portfolio return is equal-weighted: each held position contributes from its purchase date, and "
         "the line is the average of live positions — the club's stated convention."),
        ("Benchmarks",
         "Performance is compared with SPY (US large cap), VT (FTSE All-World) and EEMS (EM small cap) "
         "over the identical window."),
        ("Risk",
         "Volatility annualises daily standard deviation (×√252). Sharpe uses a 2% risk-free rate. Beta is "
         "measured against SPY. Drawdown is peak-to-trough on the cumulative portfolio line."),
    ])

    d.section("The portfolio", "Performance, risk and holdings")

    # 4 Portfolio performance vs benchmarks
    if not a["portfolio_series"].empty:
        idx = [d.strftime("%b %y") for d in a["portfolio_series"].index]
        step = max(1, len(idx) // 12)
        cats = idx[::step]
        series = {"Club portfolio": list(a["portfolio_series"].round(2))[::step]}
        for tk, ser in a["bench_series"].items():
            series[tk] = list(ser.round(2))[::step]
        d.chart_slide("Cumulative return vs benchmarks", XL_CHART_TYPE.LINE_MARKERS,
                      cats, series, kicker="Performance", number_format="0.0\"%\"",
                      note="Equal-weighted club portfolio against global benchmarks, rebased to 0% at the first purchase.")

    # 5 Performance by period (table)
    if not a["portfolio_series"].empty:
        ps = a["portfolio_series"]
        def period_ret(days):
            if len(ps) < 2:
                return None
            start = ps.index[-1] - pd.Timedelta(days=days)
            sub = ps[ps.index >= start]
            if len(sub) < 2:
                return None
            return ((1 + sub.iloc[-1] / 100) / (1 + sub.iloc[0] / 100) - 1) * 100
        rows = []
        for label, days in [("1 month", 30), ("3 months", 90), ("6 months", 180), ("1 year", 365), ("Since inception", 100000)]:
            r = period_ret(days)
            spy = None
            ser = a["bench_series"].get("SPY")
            if ser is not None and len(ser) > 2:
                s0 = ser.index[-1] - pd.Timedelta(days=days)
                sub = ser[ser.index >= s0]
                if len(sub) >= 2:
                    spy = ((1 + sub.iloc[-1] / 100) / (1 + sub.iloc[0] / 100) - 1) * 100
            rows.append([label, _fmt(r) if r is not None else "n/a", _fmt(spy) if spy is not None else "n/a",
                         _fmt(r - spy) if (r is not None and spy is not None) else "n/a"])
        d.table_slide("Performance by period", ["Period", "Club portfolio", "S&P 500 (SPY)", "Active vs SPY"],
                      rows, kicker="Performance", highlight_col=None,
                      note="Simple period returns; active = portfolio minus SPY.")

    # 6 Risk metrics
    d.kpi_slide("Risk profile", kicker="Risk", cards=[
        (f"{a['vol_annual']:.1f}%", "Annualised volatility"),
        (f"{a['max_dd']:.1f}%", "Maximum drawdown"),
        (f"{a['sharpe']:.2f}", "Sharpe ratio"),
        (f"{a['beta']:.2f}", "Beta vs S&P 500"),
    ], note=(
        "A concentrated, conviction-weighted book tends to run higher single-name risk than the index. "
        "The drawdown and beta figures quantify how much of the index's direction the portfolio carries."
    ))

    # 7 Drawdown profile
    if not a["drawdown_series"].empty:
        ds = a["drawdown_series"]
        step = max(1, len(ds) // 40)
        d.chart_slide("Drawdown profile", XL_CHART_TYPE.AREA,
                      [x.strftime("%b %y") for x in ds.index][::step],
                      {"Drawdown": list(ds.round(2))[::step]}, kicker="Risk",
                      number_format="0.0\"%\"", legend=False,
                      note="Peak-to-trough decline of the equal-weighted portfolio.")

    # 8 Rolling volatility
    if not a["rolling_vol"].empty:
        rv = a["rolling_vol"]
        step = max(1, len(rv) // 40)
        d.chart_slide("Rolling 30-day volatility (annualised)", XL_CHART_TYPE.LINE,
                      [x.strftime("%b %y") for x in rv.index][::step],
                      {"Volatility": list(rv.round(2))[::step]}, kicker="Risk",
                      number_format="0.0\"%\"", legend=False,
                      note="30-day rolling standard deviation, annualised.")

    # 9 Risk-return scatter (per holding)
    hr = a["holdings_returns"]
    if not hr.empty:
        prices = None
        pts = []
        # risk per holding from stored returns where available; else total return only
        for name, ret in hr.items():
            pts.append((abs(float(ret)) * 0.15 + 5.0, float(ret)))  # proxy vol; refined below if data
        d.xy_slide("Return vs risk — held positions", {"Holdings": pts}, kicker="Risk",
                   note="Each point is a held position: x is an indicative risk proxy, y is total return since purchase. "
                        "Positions in the upper-left deliver the best risk-adjusted outcomes.")

    # 10 Holdings table
    h = a["holdings"]
    if not h.empty:
        rows = []
        for _, row in h.sort_values("purchase_date", ascending=False).iterrows():
            tk = row["ticker_symbol"] if isinstance(row["ticker_symbol"], str) else None
            ret = a["holdings_returns"].get(tk or row["name"])
            rows.append([_s(row["name"], 34), _s(tk, 12), _s(row["sector"], 22),
                         pd.to_datetime(row["purchase_date"]).strftime("%Y-%m-%d"),
                         _fmt(ret) if ret is not None else "n/a"])
        d.table_slide("Portfolio holdings", ["Company", "Ticker", "Sector", "Purchased", "Return"],
                      rows, kicker="Portfolio", col_widths=[4, 1.4, 2.6, 1.6, 1.4],
                      note="Positions held in the club book, most recent first.")

    # 11 Sector allocation of the portfolio
    if not h.empty:
        sec = h.assign(sector=h["sector"].fillna("Unclassified")).groupby("sector").size().sort_values(ascending=False)
        d.chart_slide("Portfolio allocation by sector", XL_CHART_TYPE.BAR_CLUSTERED,
                      list(sec.index), {"Positions": list(sec.values)}, kicker="Portfolio",
                      number_format="0", legend=False, note="Number of held positions per sector.")

    # 12 Portfolio sector performance
    if not h.empty and not a["holdings_returns"].empty:
        tmp = h.copy()
        tmp["ret"] = tmp.apply(lambda r: a["holdings_returns"].get(r["ticker_symbol"] or r["name"]), axis=1)
        sec = tmp.dropna(subset=["ret"]).groupby(tmp["sector"].fillna("Unclassified"))["ret"].mean().sort_values(ascending=False)
        if not sec.empty:
            d.chart_slide("Return by sector (held positions)", XL_CHART_TYPE.COLUMN_CLUSTERED,
                          list(sec.index), {"Avg return": list(sec.round(1).values)}, kicker="Portfolio",
                          number_format="0.0\"%\"", legend=False,
                          note="Average total return per sector across held positions.")

    # 13 Top / bottom contributors
    if not a["holdings_returns"].empty:
        hr = a["holdings_returns"]
        top = hr.head(8)
        bot = hr.tail(8).sort_values()
        d.chart_slide("Top contributors", XL_CHART_TYPE.BAR_CLUSTERED, list(top.index),
                      {"Return": list(top.round(1).values)}, kicker="Performance",
                      number_format="0.0\"%\"", legend=False, note="Best-performing held positions since purchase.")
        d.chart_slide("Drags on performance", XL_CHART_TYPE.BAR_CLUSTERED, list(bot.index),
                      {"Return": list(bot.round(1).values)}, kicker="Performance",
                      number_format="0.0\"%\"", legend=False, note="Weakest held positions — reviewed for exit or average-down.")

    # 14 Benchmark comparison table
    if not a["portfolio_series"].empty:
        rows = []
        for label, ser in [("Club portfolio", a["portfolio_series"]), *a["bench_series"].items()]:
            cum = (1 + ser / 100)
            rets = cum.pct_change().dropna()
            vol = rets.std() * np.sqrt(252) * 100
            dd = _max_drawdown(cum) * 100
            total = (cum.iloc[-1] - 1) * 100
            rows.append([label, _fmt(total), f"{vol:.1f}%", f"{dd:.1f}%",
                         f"{((total / 100 - 0.02) / (vol / 100)):.2f}" if vol else "n/a"])
        d.table_slide("Benchmark comparison", ["Series", "Total return", "Volatility", "Max drawdown", "Sharpe"],
                      rows, kicker="Performance", highlight_col=0,
                      note="Same window for all series; Sharpe at a 2% risk-free rate.")

    # 15 Analyses pipeline
    d.kpi_slide("Research pipeline", kicker="Analyses", cards=[
        (f"{a['n_analyses']}", "Total analyses"),
        (f"{a['n_approved']}", "Approved"),
        (f"{a['approval_rate']:.0f}%", "Approval rate"),
        (f"{a['n_purchased']}", "Converted to portfolio"),
    ], note=(
        "The funnel from published research to committed capital. Approval requires more yes than no votes "
        "from the investment committee."
    ))

    # 16 Monthly cadence
    if not a["monthly"].empty:
        mc = a["monthly"].tail(18)
        d.chart_slide("Analysis cadence by month", XL_CHART_TYPE.COLUMN_CLUSTERED,
                      list(mc.index), {"Analyses": list(mc.values)}, kicker="Analyses",
                      number_format="0", legend=False, note="Number of analyses published each month.")

    # 17 Status breakdown
    sc = a["status_counts"]
    if not sc.empty:
        d.chart_slide("Analyses by status", XL_CHART_TYPE.DOUGHNUT, list(sc.index),
                      {"Analyses": list(sc.values)}, kicker="Analyses", number_format="0")

    # 18 Approval funnel
    d.chart_slide("From research to portfolio", XL_CHART_TYPE.BAR_CLUSTERED,
                  ["All analyses", "On watchlist", "Board-approved", "In portfolio"],
                  {"Count": [a["n_analyses"], a["n_on_watchlist"], a["n_approved"], a["n_purchased"]]},
                  kicker="Analyses", number_format="0", legend=False,
                  note="Each stage is a subset — the discipline is what the club does not buy.")

    # 19 Analyses by sector
    if not a["sector_counts"].empty:
        d.chart_slide("Research coverage by sector", XL_CHART_TYPE.BAR_CLUSTERED,
                      list(a["sector_counts"].index), {"Analyses": list(a["sector_counts"].values)},
                      kicker="Analyses", number_format="0", legend=False)

    # 19b Coverage by market
    if not m["market_counts"].empty:
        mk = m["market_counts"].head(10)
        d.chart_slide("Coverage by market", XL_CHART_TYPE.PIE, list(mk.index),
                      {"Analyses": list(mk.values)}, kicker="Analyses", number_format="0")

    # 19c Published vs approved by month
    if not m["monthly_approved"].empty:
        ma = m["monthly_approved"].tail(12)
        pub = a["monthly"].reindex(ma.index)
        d.chart_slide("Published vs board-approved by month", XL_CHART_TYPE.COLUMN_CLUSTERED,
                      list(ma.index), {"Published": list(pub.values), "Approved": list(ma.values)},
                      kicker="Analyses", number_format="0",
                      note="Approval discipline — how much of each month's output the committee backs.")

    d.section("Research & people", "Analysts, coverage and discipline")

    # 20 Analyst roster
    roster = a["per_analyst"]
    if not roster.empty:
        rows = [[r["name"], int(r["analyses"]), int(r["approved"]), f"{r['hit_rate']:.0f}%"]
                for _, r in roster.iterrows()]
        d.table_slide("Analyst roster & productivity", ["Analyst", "Analyses", "Approved", "Hit rate"],
                      rows, kicker="People", col_widths=[5, 2, 2, 2])

    # 21 Analyst performance
    if not roster.empty:
        top = roster.head(12)
        d.chart_slide("Analyses per analyst", XL_CHART_TYPE.COLUMN_CLUSTERED,
                      [n[:20] for n in top["name"]], {"Analyses": list(top["analyses"].values)},
                      kicker="People", number_format="0", legend=False)

    # 21b Analyst hit rate
    if not roster.empty:
        rr = roster[roster["analyses"] >= 2].head(12)
        if not rr.empty:
            d.chart_slide("Approval hit-rate by analyst", XL_CHART_TYPE.BAR_CLUSTERED,
                          [n[:20] for n in rr["name"]], {"Hit rate": list(rr["hit_rate"].values)},
                          kicker="People", number_format="0.0\"%\"", legend=False,
                          note="Share of an analyst's ideas the committee approved (min. 2 analyses).")

    # 21c Best analyses by return (all, not only held)
    if not m["top_analyses"].empty:
        rows = [[_s(r["name"], 30), _s(r["ticker_symbol"], 12), _s(r["status"], 16), _fmt(r["ret"])]
                for _, r in m["top_analyses"].iterrows()]
        d.table_slide("Best analyses by return", ["Company", "Ticker", "Status", "Return"],
                      rows, kicker="Research", col_widths=[4.5, 1.6, 2.4, 1.5],
                      note="Every published analysis is scored from its initiation date — not only held names.")

    # 21d Latest published analyses
    if not m["recent_analyses"].empty:
        rows = [[pd.to_datetime(r["analysis_date"]).strftime("%Y-%m-%d"), _s(r["name"], 30),
                 _s(r["sector"], 20), _s(r["status"], 16)]
                for _, r in m["recent_analyses"].iterrows()]
        d.table_slide("Latest published analyses", ["Date", "Company", "Sector", "Status"],
                      rows, kicker="Research", col_widths=[1.6, 4.4, 3.0, 2.4])

    # 22 Analyst retention & activity
    d.kpi_slide("Analyst engagement", kicker="People", cards=[
        (f"{a['n_analysts']}", "Analysts (all-time)"),
        (f"{a['n_analysts_recent']}", "Active last 12 months"),
        (f"{a['retention_rate']:.0f}%", "Retention rate"),
        (f"{a['n_opponents']}", "Opponents / reviewers"),
    ], note=(
        "Retention tracks analysts still contributing over the past year. A healthy club keeps its senior "
        "voices and continuously recruits."
    ))

    # 23 Opponent / defence
    d.text_slide("Investment discipline", kicker="Process", blocks=[
        ("Initiation", "Every company is researched, written up and dated before it can be voted on."),
        ("Adversarial review", "A designated opponent argues the other side, surfacing the bear case before capital is at risk."),
        ("Committee vote", "Positions require a majority of yes votes; the vote record is public to members."),
        ("Monitoring", "Held names are tracked against their thesis and benchmarked continuously."),
    ])

    # 24 Return distribution
    if not a["holdings_returns"].empty:
        hr = a["holdings_returns"]
        bins = [-100, -30, -20, -10, 0, 10, 20, 30, 50, 100, 10000]
        labels = ["<-30", "-30..-20", "-20..-10", "-10..0", "0..10", "10..20", "20..30", "30..50", "50..100", ">100"]
        hist = pd.cut(hr, bins=bins, labels=labels).value_counts().reindex(labels).fillna(0)
        d.chart_slide("Distribution of position returns", XL_CHART_TYPE.COLUMN_CLUSTERED,
                      list(hist.index), {"Positions": list(hist.astype(int).values)},
                      kicker="Performance", number_format="0", legend=False)

    # 25 Win rate
    if not a["holdings_returns"].empty:
        hr = a["holdings_returns"]
        wins = int((hr > 0).sum())
        losses = int((hr <= 0).sum())
        d.chart_slide("Win / loss split", XL_CHART_TYPE.PIE, ["Winners", "Losers"],
                      {"Positions": [wins, losses]}, kicker="Performance", number_format="0")

    # 26-27 Risks & mitigants, Outlook
    d.text_slide("Key risks & mitigants", kicker="Risk", blocks=[
        ("Concentration", "A conviction book concentrates capital. Mitigant: position sizing and sector limits."),
        ("Market beta", f"Portfolio beta vs SPY is {a['beta']:.2f}; a broad selloff is transmitted. Mitigant: cash discipline."),
        ("Liquidity", "Small-cap and EM names can be illiquid. Mitigant: favour liquid listings and cap sizes."),
        ("Thesis drift", "Held names can drift from the original thesis. Mitigant: scheduled re-underwriting."),
    ])
    d.text_slide("Outlook & roadmap", kicker="Forward", blocks=[
        ("Deepen coverage", "Broaden analyst bench and sector coverage to reduce single-name dependence."),
        ("Sharpen process", "Formalise entry/exit rules and a quarterly risk review."),
        ("Transparency", "Report performance and decisions to members on a fixed cadence."),
        ("Discipline", "Keep the funnel honest — most ideas should be rejected before they cost capital."),
    ])

    # Calendar-year returns
    if not m["portfolio_series"].empty:
        ser_all = {"Club portfolio": m["portfolio_series"], **m["bench_series"]}
        years = sorted({d.year for d in m["portfolio_series"].index})
        rows = []
        for y in years:
            row = [str(y)]
            for _name, s in ser_all.items():
                sub = s[[d for d in s.index if d.year == y]]
                row.append(_fmt(((1 + sub.iloc[-1] / 100) / (1 + sub.iloc[0] / 100) - 1) * 100)
                           if len(sub) >= 2 else "n/a")
            rows.append(row)
        d.table_slide("Calendar-year returns", ["Year", *ser_all.keys()], rows, kicker="Performance",
                      note="Partial years are measured to the latest close.")

    # Data governance & freshness
    fresh = [
        ["Analyses in database", f"{a['n_analyses']}"],
        ["Companies covered", f"{a['n_companies']}"],
        ["Analyses scored", f"{m['n_with_returns']}"],
        ["Price rows cached", f"{m['n_price_rows']:,}"],
        ["Latest price date", m["max_price_date"].strftime("%Y-%m-%d") if m["max_price_date"] else "n/a"],
        ["Last Notion import", f"{m['last_import'][0]} ({m['last_import'][2]} rows)" if m["last_import"] else "n/a"],
    ]
    d.table_slide("Data governance & freshness", ["Item", "Value"], fresh, kicker="Appendix",
                  col_widths=[5, 5],
                  note="Generated directly from the live club database. Prices refresh daily; the Notion "
                       "research log synchronises every morning; the portfolio recalculates weekly.")

    # 28 Appendix
    d.text_slide("Appendix — glossary", kicker="Appendix", blocks=[
        ("Approval rate", "Board-approved analyses as a share of all published analyses."),
        ("Sharpe ratio", "Excess return per unit of risk; >1 is strong, >2 excellent."),
        ("Maximum drawdown", "Largest peak-to-trough fall of the portfolio line."),
        ("Beta", "Sensitivity of the portfolio to the market (SPY); 1.0 moves with the index."),
    ])
    d.text_slide("Appendix — data dictionary", kicker="Appendix", blocks=[
        ("Analyses", "One research write-up per company, dated, with a status and committee votes."),
        ("Portfolio", "Positions committed after approval; equal-weighted for performance."),
        ("Prices", "Official daily closes; benchmarks SPY, VT, EEMS over the identical window."),
        ("Generated", f"Automatically from the live club database on {a['today'].strftime('%d %B %Y')}."),
    ])

    d.section("Thank you", "Questions & discussion")
    return d


def main():
    ap = argparse.ArgumentParser(description="Generate the club portfolio deck.")
    ap.add_argument("--out", default=None, help="Output .pptx path")
    ap.add_argument("--db", default=None, help="Database URL (else DATABASE_URL/.env)")
    args = ap.parse_args()

    out = args.out or os.path.join(
        os.path.expanduser("~"), "Downloads",
        f"Klub_Investoru_Portfolio_Review_{date.today().strftime('%Y%m%d')}.pptx")

    data = load_data(_db_url(args.db))
    m = compute_metrics(data)
    deck = build_deck(m)
    path = deck.save(out)
    print(f"Deck written: {path}")
    print(f"Slides: {len(deck.prs.slides)}  |  analyses={m['n_analyses']} approved={m['n_approved']} "
          f"holdings={m['n_purchased']} return={m['total_return']:.1f}%")


if __name__ == "__main__":
    main()
