"""
Pitch deck export for KI Asset Management — portfolio edition.

Every chart and table in the deck is a NATIVE PowerPoint object (chart or
table XML with editable data), not a rendered bitmap: the committee can edit
numbers, colors and text directly in PowerPoint. The only shapes drawn are
the design chrome (hairlines, chips).

Content is the actual portfolio: the vote-approved positions, their entry /
current prices and returns, contributions, monthly returns, drawdowns,
tracking vs EEMS, regression beta/alpha, tails (VaR/CVaR/Sortino/Skew/Kurt)
and a smoothed-block-bootstrap forward fan chart.

Languages: en / cs. The Czech copy is not a machine translation - it reuses
the club's own i18n.js wording where it exists and writes the rest by hand
in the same voice.

Usage:
    from app.utils.pitchdeck import build_pitch_deck
    stream, filename = build_pitch_deck('cs')
"""

import io
import math
from datetime import date, datetime
from typing import Dict, List, Optional, Tuple

import numpy as np

from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE
from pptx.chart.data import CategoryChartData, XyChartData
from pptx.enum.chart import (XL_CHART_TYPE, XL_LEGEND_POSITION,
                             XL_TICK_LABEL_POSITION, XL_TICK_MARK,
                             XL_LABEL_POSITION)
from pptx.oxml.ns import qn

from sqlalchemy import func

from ..extensions import db
from ..models import (Analysis, PerformanceCalculation, PortfolioPurchase,
                      User, BenchmarkPrice, Company, StockPrice, CompanySectorCache)
from .performance import get_vote_counts_for_analyses
from .presentation_export import (
    get_analyst_summary_table,
    generate_portfolio_chart_series,
)

import logging
logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Design tokens - the club's institutional palette (style.css values)
# ------------------------------------------------------------------

GREEN      = RGBColor(0x1A, 0x9C, 0x5E)
GREEN_DARK = RGBColor(0x14, 0x7A, 0x4A)
GREEN_DEEP = RGBColor(0x0B, 0x4B, 0x2E)
GREEN_GHOST = RGBColor(0x11, 0x63, 0x3D)
GREEN_PALE = RGBColor(0xE7, 0xF3, 0xEC)
GREEN_MID  = RGBColor(0x6F, 0xC3, 0x9B)
GREEN_SOFT = RGBColor(0xB5, 0xE0, 0xCC)
INK        = RGBColor(0x0F, 0x14, 0x19)
GRAY_700   = RGBColor(0x2D, 0x37, 0x42)
GRAY_500   = RGBColor(0x6B, 0x76, 0x82)
GRAY_400   = RGBColor(0x9A, 0xA5, 0xB1)
LINE       = RGBColor(0xE1, 0xE5, 0xE9)
LINE_SOFT  = RGBColor(0xEE, 0xF1, 0xF4)
PAPER      = RGBColor(0xF5, 0xF7, 0xF9)
WHITE      = RGBColor(0xFF, 0xFF, 0xFF)
GOLD       = RGBColor(0xB8, 0x86, 0x0B)
NAVY       = RGBColor(0x2B, 0x6C, 0xB0)
RED        = RGBColor(0xC5, 0x30, 0x30)
RED_PALE   = RGBColor(0xF7, 0xE3, 0xE3)
MINT_TEXT  = RGBColor(0xCF, 0xE8, 0xDA)

SLIDE_W, SLIDE_H = Inches(13.333), Inches(7.5)
MARGIN = Inches(0.62)
CONTENT_W = SLIDE_W - 2 * MARGIN
FONT = 'Calibri'

HEX = {'green': '1A9C5E', 'gdark': '147A4A', 'gold': 'B8B860', 'navy': '2B6CB0',
       'gray': '6B7682', 'ink': '0F1419', 'mid': '6FC39B', 'soft': 'B5E0CC'}
M_GREEN, M_GDARK, M_GOLD = '#1a9c5e', '#147a4a', '#b8860b'
M_NAVY, M_GRAY, M_INK, M_MID, M_SOFT = '#2b6cb0', '#6b7682', '#0f1419', '#6fc39b', '#b5e0cc'


def _mm(v):
    if v is None:
        return '—'
    s = f'{v:+.1f}' if v < 0 else f'{v:.1f}'
    return s.replace('.', ',')


# ------------------------------------------------------------------
# Copy (portfolio edition, two authentic voices)
# ------------------------------------------------------------------

_EN = {
    'club': 'KI Asset Management — Prague Club of Investors',
    'footer_of': 'Prague Club of Investors',
    'cover_kicker': 'PORTFOLIO & RISK · LOOK INSIDE',
    'cover_title': 'One portfolio, every number inside.',
    'cover_sub': 'Live from the club database: positions, prices, monthly returns, drawdowns, '
                 'tracking and tail metrics - the same data the public website shows, in full detail.',
    'cover_window': 'First position to today',
    'disclaimer': 'Student research for educational purposes only - not investment advice.',
    'accepting': 'Currently accepting analysts working in Czech only',
    'perf_kicker': 'RETURN', 'risk_kicker': 'RISK', 'decomp_kicker': 'DEPEND',
    'd1_kicker': 'RETURN', 'd1_title': 'Return',
    'd1_sub': 'How the portfolio compounded against the global indexes, and what each position added.',
    'd2_kicker': 'RISK', 'd2_title': 'Risk',
    'd2_sub': 'Drawdowns, monthly distribution, tail measures and the regression against EEMS.',
    'd3_kicker': 'FORWARD', 'd3_title': 'Forward look',
    'd3_sub': 'What history says about the year ahead - resampled, not promised.',
    'pos_title': 'The portfolio, position by position',
    'pos_sub': 'All committee-approved positions with live prices. Weight = final equal-weight book.',
    'h_ticker': 'Ticker', 'h_name': 'Company', 'h_entry': 'Entered',
    'h_px0': 'Entry price', 'h_px1': 'Price today', 'h_ret': 'Return', 'h_weight': 'Weight',
    'perf_title': 'Total return vs the indexes',
    'perf_sub': 'Incremental equal-weight simulation from the first approved position; benchmarks '
                'buy-and-hold from the same date.',
    'chip_total': 'Total return',
    'chip_cagr': 'Annualised (CAGR)',
    'chip_12m': 'Trailing 12M',
    'chip_vs_eems': 'vs EEMS, trailing 12M',
    'chip_sharpe': 'Sharpe (3% p.a.)',
    'chip_start': 'First position',
    'chip_vol': 'Annualised volatility',
    'chip_td': 'Annualised tracking difference',
    'chip_te': 'Tracking error, annualised',
    'chip_ir': 'Information ratio vs EEMS',
    'contrib_title': 'Where the return came from',
    'contrib_sub': 'Contribution to the annualised portfolio return under final equal weights '
                   '(\u2248 return \u00f7 positions).',
    'contrib_h_ticker': 'Ticker', 'contrib_h_ret': 'Position return', 'contrib_h_pp': 'Contribution',
    'paths_title': 'Price paths since entry',
    'paths_sub': 'Every position indexed to 100 at its own entry date - the committee sees through to today.',
    'legend_index100': 'Entry = 100',
    'month_title': 'Month-by-month ledger',
    'month_sub': 'Portfolio monthly return, heat-coded. Red months are work kept on the watchlist.',
    'dist_title': 'The shape of monthly returns',
    'dist_sub': 'Bins of the monthly history with the counts it holds.',
    'dist_bins': 'Monthly return bin',
    'dist_count': 'Months',
    'chip_mean': 'Average month',
    'chip_best': 'Best / worst month',
    'chip_pos_share': 'Positive months',
    'dd_title': 'Drawdown discipline',
    'dd_sub': 'How far below the running peak the portfolio has traded.',
    'chip_maxdd': 'Deepest drawdown',
    'chip_under': 'Longest underwater spell',
    'chip_ulcer': 'Ulcer index',
    'chip_recovery': 'Recovery so far',
    'dd_chart_title': 'Portfolio drawdown from peak',
    'roll_title': 'Risk through time',
    'roll_sub': '12-month rolling standard deviation, annualised, against EEMS.',
    'reg_title': 'Regression against EEMS',
    'reg_sub': 'Monthly portfolio returns regressed on EEMS monthly returns.',
    'chip_beta': 'Beta vs EEMS',
    'chip_alpha': 'Alpha (monthly, ann.)',
    'chip_r2': 'R\u00b2',
    'chip_tstat': 't-statistic',
    'reg_fit': 'OLS fit',
    'tail_title': 'Tails and downside',
    'tail_sub': 'What a bad month costs, and how often it hurts.',
    'tail_var95': 'VaR 95% (monthly)',
    'tail_cvar95': 'CVaR 95% (monthly)',
    'chip_sortino': 'Sortino ratio',
    'chip_calmar': 'Calmar ratio',
    'tail_worst_title': 'Five worst months',
    'fwd_title': 'What the year ahead could look like',
    'fwd_sub': 'Smoothed-block bootstrap of the monthly history (1,000 paths of 12 blocks of 3 months). '
               'Bands at the 10th-90th percentiles. Resampled history, not a promise.',
    'fwd_p90': '90th percentile',
    'fwd_p75': '75th percentile',
    'fwd_p50': 'Median',
    'fwd_p25': '25th percentile',
    'fwd_p10': '10th percentile',
    'chip_fwd_median': 'Median 12M path',
    'chip_fwd_pos': 'Path probability of >0 after 12M',
    'fwd_horizon': 'Months ahead',
    'bench_title': 'Against the indexes',
    'bench_sub': 'Returns on matching windows for every series.',
    'h_12m': '12M',
    'h_incept': 'Since inception',
    'corr_title': 'Correlation of monthly returns',
    'close_title': 'ki.havliksimon.eu',
    'close_sub': 'Every number above is recomputed from the database on export.',
    'close_kicker': 'CONTACT',
}

_CS = {
    'club': 'KI Asset Management — Pražský klub investorů',
    'footer_of': 'Pražský klub investorů',
    'cover_kicker': 'PORTFOLIO & RIZIKO · DOHLÉDNUTÍ',
    'cover_title': 'Jedno portfolio, všechna čísla uvnitř.',
    'cover_sub': 'Živě z databáze klubu: pozice, ceny, měsíční výnosy, propady, sledování indexů a '
                 'ocasová rizika – ta samá data, která ukazuje web, tentokrát do posledního centu.',
    'cover_window': 'Od první pozice do dneška',
    'disclaimer': 'Studentský výzkum pouze pro vzdělávací účely — není investiční doporučení.',   # reuse
    'accepting': 'Přijímáme analytiky, kteří pracují v češtině',                                  # reuse
    'd1_kicker': 'VÝNOS', 'd1_title': 'Výnos',
    'd1_sub': 'Jak portfolio rostlo vůči globálním indexům – a kolik k tomu přidala každá pozice.',
    'd2_kicker': 'RIZIKO', 'd2_title': 'Riziko',
    'd2_sub': 'Propady, rozložení měsíců, ocasové ukazatele a regresní poměr k EEMS.',
    'd3_kicker': 'VPŘED', 'd3_title': 'Co před námi',
    'd3_sub': 'Co říká historie o dalším roce – převzorkované, neslibované.',
    'pos_title': 'Portfolio, pozice po pozici',
    'pos_sub': 'Všechny výborem schválené pozice se živými cenami. Váha = konečné rovnovážené rozložení.',
    'h_ticker': 'Ticker', 'h_name': 'Společnost', 'h_entry': 'Vstup',
    'h_px0': 'Vstupní kurz', 'h_px1': 'Kurz dnes', 'h_ret': 'Výnos', 'h_weight': 'Váha',
    'perf_title': 'Celkový výnos vůči indexům',
    'perf_sub': 'Inkrementální rovnovážená simulace od první schválené pozice; indexy kupují a drží od '
                'téhož data.',
    'chip_total': 'Celkový výnos',                    # reuse i18n
    'chip_cagr': 'Roční tempo (CAGR)',
    'chip_12m': 'Posledních 12 měsíců',
    'chip_vs_eems': 'vs EEMS, 12M',
    'chip_sharpe': 'Sharpeho poměr',
    'chip_start': 'První pozice',
    'chip_vol': 'Roční volatilita',
    'chip_td': 'Roční odchylka vůči EEMS',
    'chip_te': 'Chyba sledování (roční)',
    'chip_ir': 'Information ratio vůči EEMS',
    'contrib_title': 'Odkud výnos přišel',
    'contrib_sub': 'Příspěvek k ročnímu výnosu portfolia v konečném rovnováženém rozložení '
                   '(≈ výnos ÷ počet pozic).',
    'contrib_h_ticker': 'Ticker', 'contrib_h_ret': 'Výnos pozice', 'contrib_h_pp': 'Příspěvek',
    'paths_title': 'Cenové dráhy od vstupu',
    'paths_sub': 'Každá pozice indexovaná ke 100 ve svém dni vstupu – výbor vidí průběh do dneška.',
    'legend_index100': 'Vstup = 100',
    'month_title': 'Ledger měsíc po měsíci',
    'month_sub': 'Měsíční výnosy portfolia po měsících, barevně.',
    'dist_title': 'Tvar měsíčních rozdílů',
    'dist_sub': 'Kategorie měsíční výnosů s počty.',
    'dist_bins': 'Výnosová kategorie',
    'dist_count': 'Měsíců',
    'chip_mean': 'Průměr měsíc',
    'chip_best': 'Nejlepší / nejhorší',
    'chip_pos_share': 'Kladných měsíců',
    'dd_title': 'Disciplína propadů',
    'dd_sub': 'Jak hluboko pod běžícím maximem portfolio občas zavítalo.',
    'chip_maxdd': 'Nejhlubší propad',
    'chip_under': 'Nejdelší doba pod hladinou',
    'chip_ulcer': 'Ulcer index',
    'chip_recovery': 'Výhled do obnovy',
    'dd_chart_title': 'Propad portfolia od maxima',
    'roll_title': 'Riziko v čase',
    'roll_sub': 'Rolující 12měsíční volatilita, anualizovaná, proti EEMS.',
    'reg_title': 'Regrese k EEMS',
    'reg_sub': 'Měsíční výnosy portfolia na měsíční výnosy indexu EEMS.',
    'chip_beta': 'Beta vůči EEMS',
    'chip_alpha': 'Alfa (ročně)',
    'chip_r2': 'R²',
    'chip_tstat': 't-statistika',
    'reg_fit': 'OLS regresní přímka',
    'tail_title': 'Ocasy a downside',
    'tail_sub': 'Kolik stojí špatný měsíc – a jak často se stane.',
    'tail_var95': 'VaR 95% (měsíčně)',
    'tail_cvar95': 'CVaR 95% (měsíčně)',
    'chip_sortino': 'Sortino ratio',
    'chip_calmar': 'Calmar ratio',
    'tail_worst_title': 'Pět nejhorších měsíců',
    'fwd_title': 'Jak by mohl vypadat příští rok',
    'fwd_sub': 'Vyhlazený blokový bootstrap měsíční historie (1 000 cest po 12 blocích po 3 měsících). '
               'Pásy mezi 10.–90. percentilem. Převzorkovaná history – ne slib.',
    'fwd_p90': '90. percentil',
    'fwd_p75': '75. percentil',
    'fwd_p50': 'Medián',
    'fwd_p25': '25. percentil',
    'fwd_p10': '10. percentil',
    'chip_fwd_median': 'Medián 12M dráhy',
    'chip_fwd_pos': 'Pravděpodobnost pozitivního roku',
    'fwd_horizon': 'Měsíců dopředu',
    'bench_title': 'Vůči indexům',
    'bench_sub': 'Výnosy na identickém okně pro každou řadu.',
    'h_12m': '12M',
    'h_incept': 'Od založení',
    'corr_title': 'Korelace měsíčních výnosů',
    'close_title': 'ki.havliksimon.eu',
    'close_sub': 'Všechna čísla výše se při exportu přepočítají z databáze.',
    'close_kicker': 'KONTAKT',
}


def _txt(lang: str) -> Dict[str, str]:
    return _CS if lang == 'cs' else _EN


# ------------------------------------------------------------------
# Data layer
# ------------------------------------------------------------------

def _board_approved():
    """Committee-approved positions - the same rule the homepage chart uses."""
    analyses = Analysis.query.filter_by(status='On Watchlist').all()
    counts = get_vote_counts_for_analyses([a.id for a in analyses])
    approved = [a for a in analyses
                if counts.get(a.id, {'yes': 0, 'no': 0})['yes'] >
                counts.get(a.id, {'yes': 0, 'no': 0})['no']]
    return sorted(approved, key=lambda a: a.analysis_date)


def _benchmark_return(ticker: str, start_date, end_date) -> float:
    try:
        s = (BenchmarkPrice.query.filter(BenchmarkPrice.ticker == ticker,
                                         BenchmarkPrice.date <= start_date)
             .order_by(BenchmarkPrice.date.desc()).first())
        e = (BenchmarkPrice.query.filter(BenchmarkPrice.ticker == ticker,
                                         BenchmarkPrice.date <= end_date)
             .order_by(BenchmarkPrice.date.desc()).first())
        if not s or not e or float(s.close_price) <= 0:
            return 0.0
        return round((float(e.close_price) / float(s.close_price) - 1.0) * 100.0, 2)
    except Exception as exc:  # noqa: BLE001
        logger.warning('benchmark %s failed: %s', ticker, exc)
        return 0.0


def _monthly_closes(company_id: int, dates: List) -> List[Optional[float]]:
    """Close price on (or before) each month-start date for one company."""
    rows = (StockPrice.query.filter(StockPrice.company_id == company_id)
            .order_by(StockPrice.date).all())
    by_date = [(r.date, float(r.close_price)) for r in rows]
    out, i = [], 0
    for d in dates:
        dd = d.date() if hasattr(d, 'date') else d
        while i < len(by_date) and by_date[i][0] <= dd:
            i += 1
        out.append(by_date[i - 1][1] if i else None)
    return out


def _series_metrics(dates, port_pct, spy_pct, vt_pct, eems_pct) -> dict:
    port = np.array(port_pct, dtype=float)
    if len(port) < 3:
        return {}
    p = port / 100.0
    eq = 1.0 + p
    dd = eq / np.maximum.accumulate(eq) - 1.0
    monthly = np.diff(p)

    years_span = monthly.size / 12.0
    total = float(p[-1])
    cagr = (1.0 + total) ** (1 / years_span) - 1.0 if total > -1 else total / years_span
    ann_vol = float(monthly.std(ddof=1) * math.sqrt(12.0))

    def period_ret(x, n=13):
        arr = 1.0 + np.array(x, dtype=float) / 100.0
        return float(arr[-1] / arr[-n] - 1.0) * 100.0 if arr.size >= n else None

    def dm(x):
        return np.diff(np.array(x, dtype=float) / 100.0)

    em = dm(eems_pct)
    sm = dm(spy_pct)
    n = min(monthly.size, em.size)
    excess = monthly[-n:] - em[-n:]
    te_ann = float(excess.std(ddof=1) * math.sqrt(12.0))
    td_ann = float(excess.mean() * 12.0)

    nb = min(monthly.size, sm.size)
    x_p, x_mk = monthly[-nb:], sm[-nb:]
    cov = np.cov(x_p, x_mk)
    beta = float(cov[0, 1] / cov[1, 1]) if nb > 3 and cov[1, 1] > 0 else None
    corr = float(np.corrcoef(x_p, x_mk)[0, 1]) if nb > 3 else None
    r2 = corr ** 2 if corr is not None else None
    tstat = (corr * math.sqrt((nb - 2) / max(1e-9, (1 - corr ** 2))).real
             if corr is not None and nb > 3 else None)
    alpha_m = float(x_p.mean() - beta * x_mk.mean()) if beta is not None else None

    downside = monthly[monthly < 0]
    semi = float(downside.std(ddof=1) * math.sqrt(12) * 100) if downside.size > 1 else None
    max_dd = float(dd.min()) * 100.0
    sortino = (cagr * 100.0 / semi) if semi and semi > 0 else None
    calmar = (cagr * 100.0 / abs(max_dd)) if max_dd < 0 else None

    spell = 0
    for v in dd:
        spell = spell + 1 if v < -1e-12 else 0
    max_spell = 0
    cur = 0
    for v in dd:
        cur = cur + 1 if v < -1e-12 else 0
        max_spell = max(max_spell, cur)

    mu = float(monthly.mean())
    skew = float(((monthly - mu) ** 3).mean() / (monthly.std(ddof=1) ** 3 + 1e-12))
    kurt = float(((monthly - mu) ** 4).mean() / (monthly.std(ddof=1) ** 4 + 1e-12) - 3.0)
    var95 = float(np.percentile(monthly, 5) * 100.0)
    cvar95 = float(monthly[monthly <= np.percentile(monthly, 5)].mean() * 100.0)
    ulcer = float(np.sqrt((dd * 100.0) ** 2).mean())

    # smoothed block bootstrap, 1,000 paths of 12 months in blocks of 3
    rng = np.random.default_rng(7)
    rets_d = monthly  # decimals per month
    nblocks = 4
    sims = []
    starts = rets_d.size - 3
    for _ in range(1000):
        path = []
        for _b in range(nblocks):
            i0 = int(rng.integers(0, starts)) if starts > 0 else 0
            path.extend(rets_d[i0:i0 + 3])
        path = path[:12]
        sims.append(np.cumprod(1 + np.array(path)) - 1.0)
    sims = np.array(sims) * 100.0
    pct = {q: np.percentile(sims, q, axis=0) for q in (10, 25, 50, 75, 90)}
    prob_pos = float((sims[:, -1] > 0).mean() * 100.0)
    med_12m = float(pct[50][-1])

    tr_p, tr_e = period_ret(port_pct), period_ret(eems_pct)

    return {
        'total_return': total * 100.0, 'cagr': cagr * 100.0,
        'ann_vol': ann_vol * 100.0,
        'sharpe': float((cagr - 0.03) / ann_vol) if ann_vol > 0 else None,
        'trailing_12m': tr_p,
        'vs_eems_12m': (tr_p - tr_e) if tr_p is not None and tr_e is not None else None,
        'max_dd': max_dd, 'underwater_months': max_spell,
        'ulcer': ulcer, 'semidev': semi, 'sortino': sortino, 'calmar': calmar,
        'skew': skew, 'kurt': kurt, 'var95': var95, 'cvar95': cvar95,
        'monthly_avg': float(monthly.mean() * 100),
        'monthly_best': float(monthly.max() * 100),
        'monthly_worst': float(monthly.min() * 100),
        'positive_months': float((monthly > 0).mean() * 100),
        'beta': beta, 'alpha_m': alpha_m, 'r2': r2, 'tstat': tstat,
        'corr_eems': float(np.corrcoef(monthly[-n:], em[-n:])[0, 1]) if n > 3 else None,
        'tr_'.join([]) or 'tracking_diff': td_ann * 100, 'tracking_err': te_ann * 100, 'info_ratio': (td_ann / te_ann) if te_ann > 1e-9 else None,
        'dd_series': dd * 100,
        'monthly': monthly * 100,
        'monthly_dates': [d for d in dates[1:]],
        'boot_pct': pct, 'prob_pos': prob_pos, 'med_12m': med_12m,
    }


def _collect(window_years: Optional[int] = None) -> dict:
    import pandas as pd

    approved = _board_approved()
    analysis_ids = [a.id for a in approved]
    s = generate_portfolio_chart_series(analysis_ids, years=window_years, method='incremental')
    dates = pd.to_datetime(s['dates'])
    start_date = approved[0].analysis_date if approved else date.today()

    series = {
        'port': s['values'],
        'spy': [_benchmark_return('SPY', start_date, d.date()) for d in dates],
        'vt': [_benchmark_return('VT', start_date, d.date()) for d in dates],
        'eems': [_benchmark_return('EEMS', start_date, d.date()) for d in dates],
    }

    # positions: entry/current prices + monthly normalized paths since entry
    positions = []
    for z in approved:
        c = Company.query.get(z.company_id)
        pc = (PerformanceCalculation.query.filter_by(analysis_id=z.id)
              .order_by(PerformanceCalculation.calculation_date.desc()).first())
        entry_px = float(pc.price_at_analysis) if pc else None
        cur_px = float(pc.price_current) if pc else None
        ret = float(pc.return_pct) if pc else None
        closes = _monthly_closes(z.company_id, dates)
        path = None
        if closes:
            base = None
            for v in closes:
                if v:
                    base = v
                    break
            if base:
                path = [None if not v else (v / base - 1.0) * 100.0 for v in closes]
        positions.append({
            'analysis_id': z.id, 'name': c.name, 'ticker': c.ticker_symbol,
            'entry_date': z.analysis_date, 'entry_px': entry_px,
            'cur_px': cur_px, 'ret_pct': ret, 'path': path,
        })
    n = len(positions)
    for p in positions:
        p['weight'] = 100.0 / n if n else 0.0
        p['contribution'] = (p['ret_pct'] / n) if (p['ret_pct'] is not None and n) else None

    metrics = _series_metrics(s['dates'], series['port'], series['spy'], series['vt'], series['eems'])

    return {
        'approved': approved, 'positions': positions, 'n_positions': n,
        'dates': dates, 'start_date': start_date,
        'series': series, 'metrics': metrics,
        'win_rate': (sum(1 for p in positions if p['ret_pct'] and p['ret_pct'] > 0) / n * 100.0) if n else None,
    }

def _collect_full(lang: str, window_years: Optional[int] = None) -> dict:
    data = _collect(window_years)
    tracker = _load_tracker()
    pipe = _pipeline_counts()
    live_ret = [p['unreal_pct'] for p in tracker['positions']]
    data['live_win_rate'] = (sum(1 for v in live_ret if v > 0) / len(live_ret) * 100.0) if live_ret else None
    data['tracker'] = tracker
    data['pipe'] = pipe
    return data


# ------------------------------------------------------------------
# Slide primitives
# ------------------------------------------------------------------

def _tbox(slide, l, t, w, h, anchor=MSO_ANCHOR.TOP):
    box = slide.shapes.add_textbox(l, t, w, h)
    tf = box.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    return tf


def _para(tf, text='', size=10, color=INK, bold=False, italic=False, align=PP_ALIGN.LEFT,
          space_after=0, space_before=0, line=1.0, first=False, spc=None, font=FONT):
    first_p = tf.paragraphs[0]
    use = first_p if (first and not first_p.runs and not first_p.text) else tf.add_paragraph()
    p = use
    p.alignment = align
    p.space_before = Pt(space_before)
    p.space_after = Pt(space_after)
    p.line_spacing = line
    chunks = str(text).split('\n')
    for i, chunk in enumerate(chunks):
        if i:
            p = tf.add_paragraph()
            p.alignment = align
            p.space_before = Pt(space_before)
            p.space_after = Pt(space_after)
            p.line_spacing = line
        r = p.add_run()
        r.text = chunk
        f = r.font
        f.name = font
        f.size = Pt(size)
        f.bold = bold
        f.italic = italic
        f.color.rgb = color
        if spc is not None:
            f._rPr.set('spc', str(spc))
    return p


def _rule(slide, l, t, w, color=LINE, thickness=0.011):
    shp = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, l, t, w, Inches(thickness))
    shp.fill.solid()
    shp.fill.fore_color.rgb = color
    shp.line.fill.background()
    shp.shadow.inherit = False
    return shp


def _rect(slide, l, t, w, h, fill, radius=None):
    shape_type = MSO_SHAPE.ROUNDED_RECTANGLE if radius else MSO_SHAPE.RECTANGLE
    shp = slide.shapes.add_shape(shape_type, l, t, w, h)
    if radius:
        try:
            shp.adjustments[0] = radius
        except Exception:
            pass
    shp.fill.solid()
    shp.fill.fore_color.rgb = fill
    shp.line.fill.background()
    shp.shadow.inherit = False
    return shp


def _badge(slide, l, t, w, h, fill, label, label_color=GREEN_DARK, size=8, radius=0.5, bold=True):
    shp = _rect(slide, l, t, w, h, fill, radius=radius)
    tf = shp.text_frame
    tf.word_wrap = False
    tf.margin_left = tf.margin_right = Inches(0.08)
    tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    _para(tf, label, size=size, color=label_color, bold=bold, align=PP_ALIGN.CENTER, first=True)
    return shp


def _page_chrome(slide, idx, kicker, title, subtitle, txt):
    top = Inches(0.55)
    tf = _tbox(slide, MARGIN, top, CONTENT_W * 0.8, Inches(0.3))
    _para(tf, kicker, size=10, color=GREEN_DARK, bold=True, spc=200, first=True)
    _rule(slide, MARGIN, top + Inches(0.30), Inches(0.42), color=GREEN, thickness=0.028)
    tf = _tbox(slide, MARGIN, top + Inches(0.42), CONTENT_W, Inches(0.42))
    _para(tf, title, size=23, color=INK, bold=True, first=True)
    if subtitle:
        tf = _tbox(slide, MARGIN, top + Inches(0.92), CONTENT_W * 0.95, Inches(0.55))
        _para(tf, subtitle, size=10.5, color=GRAY_500, line=1.18, first=True)
    _rule(slide, MARGIN, SLIDE_H - Inches(0.5), CONTENT_W, color=LINE_SOFT)
    tf = _tbox(slide, MARGIN, SLIDE_H - Inches(0.42), Inches(6.4), Inches(0.25))
    _para(tf, txt['club'], size=7.5, color=GRAY_400, first=True)
    tf = _tbox(slide, SLIDE_W - MARGIN - Inches(1.2), SLIDE_H - Inches(0.42), Inches(1.2), Inches(0.25))
    _para(tf, f"{idx:02d}", size=7.5, color=GRAY_400, bold=True, align=PP_ALIGN.RIGHT, first=True)
    _badge(slide, SLIDE_W - MARGIN - Inches(1.55), SLIDE_H - Inches(0.44), Inches(0.28), Inches(0.17),
           GREEN_PALE, 'KI', size=6, radius=0.35)


def _kpi(slide, l, t, w, h, label, value, note=None, value_color=INK, fill=PAPER,
         value_size=21, small=False):
    _rect(slide, l, t, w, h, fill, radius=0.06)
    tf = _tbox(slide, l + Inches(0.14), t + Inches(0.12), w - Inches(0.28), h - Inches(0.2))
    _para(tf, label, size=7.5, color=GRAY_500, bold=True, spc=120, first=True, space_after=3)
    _para(tf, value, size=min(value_size, 12 if small and False else value_size) if not small else 11,
          color=value_color, bold=True, line=0.95)
    if note:
        _para(tf, note, size=7.5, color=GRAY_400, line=1.05, space_before=2)


_TCPR_ORDER = ['a:lnL', 'a:lnR', 'a:lnT', 'a:lnB', 'a:lnTlToBr', 'a:lnBlToTr']


def _cell_border(cell, edge='bottom', color=LINE, width_pt=0.75):
    tag_map = {'left': 'a:lnL', 'right': 'a:lnR', 'top': 'a:lnT', 'bottom': 'a:lnB'}
    tag = tag_map[edge]
    tcPr = cell._tc.get_or_add_tcPr()
    ln = tcPr.find(qn(tag))
    if ln is None:
        ln = tcPr.makeelement(qn(tag), {})
        pos = _TCPR_ORDER.index(tag)
        insert_at = len(tcPr)
        for i, child in enumerate(list(tcPr)):
            name = f"a:{child.tag.split('}')[-1]}"
            if name in _TCPR_ORDER and _TCPR_ORDER.index(name) > pos:
                insert_at = i
                break
        tcPr.insert(insert_at, ln)
    ln.set('w', str(int(width_pt * 12700)))
    ln.set('cap', 'flat')
    ln.set('cmpd', 'sng')
    ln.set('algn', 'ctr')
    for child in list(ln):
        ln.remove(child)
    solid = ln.makeelement(qn('a:solidFill'), {})
    srgb = solid.makeelement(qn('a:srgbClr'), {})
    srgb.set('val', str(color))
    solid.append(srgb)
    ln.append(solid)
    ln.append(ln.makeelement(qn('a:prstDash'), {'val': 'solid'}))


def _pptx_table(slide, l, t, w, col_w, headers, rows, row_h=Inches(0.3), header_h=Inches(0.3),
                size=9, header_size=7.5, cell_fills=None, align=None, bold_col0=True):
    """Native PPTX table. cell_fills maps (row, col)->RGBColor; align maps col->PP_ALIGN."""
    gf = slide.shapes.add_table(len(rows) + 1, len(headers), l, t, w,
                                header_h + row_h * len(rows))
    tbl = gf.table
    tot = sum(col_w)
    tbl.first_row = False
    tbl.horz_banding = False
    for i, cw in enumerate(col_w):
        tbl.columns[i].width = Emu(int(w * cw / tot))
    tbl.rows[0].height = header_h
    for j, htext in enumerate(headers):
        c = tbl.cell(0, j)
        c.fill.solid()
        c.fill.fore_color.rgb = WHITE
        c.vertical_anchor = MSO_ANCHOR.MIDDLE
        c.margin_left = c.margin_right = Inches(0.07)
        c.margin_top = c.margin_bottom = Inches(0.03)
        _para(c.text_frame, htext.upper(), size=header_size, color=GRAY_500, bold=True, spc=90,
              first=True, align=(align or {}).get(j, PP_ALIGN.LEFT if j == 0 else PP_ALIGN.RIGHT))
        _cell_border(c, 'bottom', GREEN, 1.4)
    for ri, row in enumerate(rows, start=1):
        tbl.rows[ri].height = row_h
        for ci, val in enumerate(row):
            c = tbl.cell(ri, ci)
            fill_rgb = (cell_fills or {}).get((ri - 1, ci))
            c.fill.solid()
            c.fill.fore_color.rgb = fill_rgb if fill_rgb else (PAPER if ri % 2 == 0 else WHITE)
            c.vertical_anchor = MSO_ANCHOR.MIDDLE
            c.margin_left = c.margin_right = Inches(0.07)
            c.margin_top = c.margin_bottom = Inches(0.03)
            al = (align or {}).get(ci, PP_ALIGN.LEFT if ci == 0 else PP_ALIGN.RIGHT)
            num_col = align.get(ci) if align else None
            right = al == PP_ALIGN.RIGHT
            color = INK
            if isinstance(val, str):
                if val.startswith('+'):
                    color = GREEN_DARK
                elif val.startswith('-') and right:
                    color = RED
            _para(c.text_frame, str(val), size=size, color=color, first=True, align=al,
                  bold=(bold_col0 and ci == 0))
            _cell_border(c, 'bottom', LINE_SOFT, 0.75)
    return tbl


# ------------------------------------------------------------------
# Native charts
# ------------------------------------------------------------------

def _style_chart(chart, legend=True, font_size=8):
    chart.has_title = False
    chart.font.size = Pt(font_size)
    chart.font.name = FONT
    chart.font.color.rgb = GRAY_700
    chart.has_legend = legend
    if legend:
        chart.legend.position = XL_LEGEND_POSITION.TOP
        chart.legend.include_in_layout = False
        chart.legend.font.size = Pt(font_size)
        chart.legend.font.color.rgb = GRAY_500
    va = chart.value_axis
    ca = chart.category_axis
    va.has_major_gridlines = True
    va.major_gridlines.format.line.color.rgb = LINE
    va.major_gridlines.format.line.width = Pt(0.5)
    ca.has_major_gridlines = False
    ca.tick_labels.font.size = Pt(7.5)
    ca.tick_labels.font.color.rgb = GRAY_500
    ca.format.line.color.rgb = LINE
    va.tick_labels.font.size = Pt(7.5)
    va.tick_labels.font.color.rgb = GRAY_500
    va.format.line.fill.background()
    ca.major_tick_mark = XL_TICK_MARK.NONE
    va.major_tick_mark = XL_TICK_MARK.NONE


def _native_line(slide, l, t, w, h, cats, series, y_min=None, y_max=None, num_fmt='0',
                 line_width=2.2):
    chart_data = CategoryChartData()
    chart_data.categories = cats
    for name, vals, color in series:
        chart_data.add_series(name, vals)
    gf = slide.shapes.add_chart(XL_CHART_TYPE.LINE, l, t, w, h, chart_data)
    chart = gf.chart
    _style_chart(chart)
    for si, (_, _, color) in enumerate(series):
        s = chart.series[si]
        s.format.line.color.rgb = color
        s.format.line.width = Pt(line_width * (1.35 if color == GREEN else 1.0))
        try:
            s.smooth = False
        except Exception:
            pass
    va = chart.value_axis
    if y_min is not None:
        va.minimum_scale = y_min
    if y_max is not None:
        va.maximum_scale = y_max
    va.tick_labels.number_format = num_fmt
    va.tick_labels.number_format_is_linked = False
    return chart


def _native_area(slide, l, t, w, h, cats, series, n_fmt='0', y_min=None, y_max=None):
    chart_data = CategoryChartData()
    chart_data.categories = cats
    for name, vals, color in series:
        chart_data.add_series(name, vals)
    gf = slide.shapes.add_chart(XL_CHART_TYPE.AREA, l, t, w, h, chart_data)
    chart = gf.chart
    _style_chart(chart, legend=False)
    for si, (_, _, color) in enumerate(series):
        ser = chart.series[si]
        ser.format.fill.solid()
        ser.format.fill.fore_color.rgb = color
        ser.format.fill.fore_color.brightness = 0.75
        ser.format.line.color.rgb = color
        ser.format.line.width = Pt(1.3)
    if y_min is not None:
        chart.value_axis.minimum_scale = y_min
    if y_max is not None:
        chart.value_axis.maximum_scale = y_max
    chart.value_axis.tick_labels.number_format = n_fmt
    chart.value_axis.tick_labels.number_format_is_linked = False
    return chart


def _native_bar(slide, l, t, w, h, cats, named_vals, horiz=False, labels=False, n_fmt='0.0',
                per_point_colors=None, gap_width=50, y_min=None, y_max=None):
    chart_data = CategoryChartData()
    chart_data.categories = cats
    for name, vals, color in named_vals:
        chart_data.add_series(name, vals)
    xl = XL_CHART_TYPE.BAR_CLUSTERED if horiz else XL_CHART_TYPE.COLUMN_CLUSTERED
    gf = slide.shapes.add_chart(xl, l, t, w, h, chart_data)
    chart = gf.chart
    _style_chart(chart, legend=len(named_vals) > 1)
    plot = chart.plots[0]
    plot.vary_by_categories = False
    plot.gap_width = gap_width
    ser = chart.series[0]
    ser.format.fill.solid()
    ser.format.fill.fore_color.rgb = named_vals[0][2]
    ser.format.line.fill.background()
    if per_point_colors:
        for pi, col in enumerate(per_point_colors):
            if col:
                pt = ser.points[pi]
                pt.format.fill.solid()
                pt.format.fill.fore_color.rgb = col
                pt.format.line.fill.background()
    if labels:
        plot.has_data_labels = True
        dl = plot.data_labels
        dl.number_format = n_fmt
        dl.number_format_is_linked = False
        dl.font.size = Pt(7.5)
        dl.font.color.rgb = GRAY_700
        dl.position = XL_LABEL_POSITION.OUTSIDE_END
    chart.value_axis.tick_labels.number_format = n_fmt
    chart.value_axis.tick_labels.number_format_is_linked = False
    return chart


def _native_scatter(slide, l, t, w, h, series, x_min, x_max, y_min, y_max, num_fmt='0',
                    marker_sizes=None):
    """xy series: list of (name, [(x, y)...], color, line:bool)"""
    chart_data = XyChartData()
    for name, xy, color, line in series:
        s = chart_data.add_series(name)
        for x, y in xy:
            s.add_data_point(x, y)
    gf = slide.shapes.add_chart(XL_CHART_TYPE.XY_SCATTER, l, t, w, h, chart_data)
    chart = gf.chart
    _style_chart(chart, legend=True)
    for si, (_, _, color, line) in enumerate(series):
        ser = chart.series[si]
        if line:
            ser.format.line.color.rgb = color
            ser.format.line.width = Pt(1.6)
        else:
            ser.marker.style = 8  # circle
            ser.marker.size = (marker_sizes or {}).get(si, 5)
            ser.marker.format.fill.solid()
            ser.marker.format.fill.fore_color.rgb = color
            ser.marker.format.line.color.rgb = WHITE
        ser.smooth = False
    for axis, lo, hi in ((chart.value_axis, y_min, y_max), (chart.category_axis, x_min, x_max)):
        if lo is not None:
            axis.minimum_scale = lo
        if hi is not None:
            axis.maximum_scale = hi
        axis.tick_labels.number_format = num_fmt
        axis.tick_labels.number_format_is_linked = False
    return chart


def _native_donut(slide, l, t, w, h, cats, vals, colors):
    chart_data = CategoryChartData()
    chart_data.categories = cats
    chart_data.add_series('', vals)
    gf = slide.shapes.add_chart(XL_CHART_TYPE.DOUGHNUT, l, t, w, h, chart_data)
    chart = gf.chart
    chart.has_title = False
    chart.font.name = FONT
    chart.font.size = Pt(10)
    chart.has_legend = True
    chart.legend.position = XL_LEGEND_POSITION.BOTTOM
    chart.legend.include_in_layout = False
    ser = chart.series[0]
    for pi, color in enumerate(colors):
        pt = ser.points[pi]
        pt.format.fill.solid()
        pt.format.fill.fore_color.rgb = color
        pt.format.line.color.rgb = WHITE
        pt.format.line.width = Pt(1.5)
    return chart


# ------------------------------------------------------------------
# Formatting helpers
# ------------------------------------------------------------------

def _p(v, lang, signed=False):
    """Percent with a Czech comma."""
    if v is None:
        return '—'
    s = (f'{v:+.1f}' if signed else f'{v:.1f}')
    if s.endswith('.0'):
        s = s[:-2]
    return s.replace('.', ',') + (' %')


def _px(v, lang):
    if v is None:
        return '—'
    s = f'{v:,.2f}'.replace(',', ' ')
    return s.replace('.', ',') if lang == 'cs' else s


def _axis_cats(dates, start=0):
    return [f'{d.month}/{d.year % 100}' for d in list(dates)[start:]]


_DATE_FMT = {'cs': '{d.day:02d}. {d.month:02d}. {d.year}', 'en': '{d.day:02d}/{d.month:02d}/{d.year}'}


def _d(v, lang):
    return _DATE_FMT[lang].format(d=v)


# ------------------------------------------------------------------
# Slides
# ------------------------------------------------------------------

def _slide_cover(prs, txt, lang, data):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _rect(slide, 0, 0, SLIDE_W, SLIDE_H, GREEN_DEEP)
    _rule(slide, MARGIN, Inches(0.62), Inches(0.9), color=GREEN_GHOST, thickness=0.014)
    tf = _tbox(slide, MARGIN, Inches(0.5), Inches(6), Inches(0.3))
    _para(tf, txt['club'].upper(), size=10, color=WHITE, bold=True, spc=220, first=True)
    tf = _tbox(slide, MARGIN, Inches(2.5), Inches(11), Inches(2.4))
    _para(tf, txt['cover_title'], size=40, color=WHITE, bold=True, line=1.05, first=True)
    tf = _tbox(slide, MARGIN, Inches(4.35), Inches(8.6), Inches(1.0))
    _para(tf, txt['cover_sub'], size=12, color=MINT_TEXT, line=1.3, first=True)
    _rule(slide, MARGIN, SLIDE_H - Inches(1.06), CONTENT_W, color=GREEN_GHOST, thickness=0.012)
    tf = _tbox(slide, MARGIN, SLIDE_H - Inches(0.86), Inches(7), Inches(0.5))
    _para(tf, txt['cover_kicker'], size=9, color=MINT_TEXT, bold=True, spc=220, first=True, space_after=2)
    _para(tf, f"{txt['cover_window']}: {_d(data['start_date'], lang)}", size=9.5, color=WHITE, bold=True)
    m = data['metrics']
    tf = _tbox(slide, SLIDE_W - MARGIN - Inches(4.4), SLIDE_H - Inches(0.86), Inches(4.4), Inches(0.5))
    _para(tf, txt['chip_total'].upper(), size=8, color=MINT_TEXT, bold=True, spc=160,
          align=PP_ALIGN.RIGHT, first=True, space_after=2)
    _para(tf, _p(m.get('total_return'), lang), size=17, color=WHITE, bold=True, align=PP_ALIGN.RIGHT)
    return slide


def _slide_positions(prs, idx, txt, lang, data):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _page_chrome(slide, idx, f"{txt['d1_kicker']} · {txt['club']}", txt['pos_title'],
                 txt['pos_sub'], txt)
    rows = []
    for p in data['positions']:
        rows.append((p['ticker'], (p['name'] or '')[:26], _d(p['entry_date'], lang),
                     _px(p['entry_px'], lang), _px(p['cur_px'], lang),
                     _p(p['ret_pct'], lang, signed=True), _p(p['weight'], lang)))
    if not rows:
        rows = [('—', '—', '—', '—', '—', '—', '—')]
    table_w = Inches(8.5)
    _pptx_table(slide, MARGIN, Inches(2.25), table_w, (1.1, 2.2, 1.15, 1.0, 1.0, 0.95, 0.8),
                [txt['h_ticker'], txt['h_name'], txt['h_entry'], txt['h_px0'],
                 txt['h_px1'], txt['h_ret'], txt['h_weight']], rows,
                row_h=Inches(0.44), size=9.5,
                align={2: PP_ALIGN.CENTER, 3: PP_ALIGN.RIGHT, 4: PP_ALIGN.RIGHT, 5: PP_ALIGN.RIGHT,
                       6: PP_ALIGN.RIGHT})
    rail_x = MARGIN + Inches(8.8)
    rail_w = SLIDE_W - MARGIN - rail_x
    m = data['metrics']
    chips = [
        (txt['chip_total'], _p(m.get('total_return'), lang), GREEN_DARK, GREEN_PALE),
        (_txt(lang)['kpi_win'] if False else ('Úspěšnost' if lang == 'cs' else 'Win rate'),
         _p(data['win_rate'], lang), GREEN_DARK, PAPER),
        (txt['perf_sub'].split('.')[0] if False else txt['chip_start'], _d(data['start_date'], lang), INK, PAPER),
    ]
    ch = Inches(0.95)
    y = Inches(2.3)
    for label, value, vcol, fill in chips:
        _kpi(slide, rail_x, y, rail_w, ch, label, value, value_color=vcol, fill=fill,
             value_size=16 if len(value) < 9 else 11)
        y += ch + Inches(0.12)
    # the equal-weight allocation ring in native form
    _native_donut(slide, rail_x, y + Inches(0.02), rail_w, Inches(1.7),
                  [p['ticker'] or '?' for p in data['positions']],
                  [p['weight'] for p in data['positions']],
                  [GREEN, GREEN_DARK, GREEN_MID, NAVY, GOLD, GRAY_500, GREEN_SOFT])
    return slide


def _slide_performance(prs, idx, txt, lang, data):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _page_chrome(slide, idx, f"{txt['d1_kicker']}", txt['perf_title'], txt['perf_sub'], txt)
    s, m = data['series'], data['metrics']
    cats = _axis_cats(data['dates'])
    _native_line(slide, MARGIN, Inches(2.25), Inches(8.3), Inches(4.5), cats, [
        (txt['perf_title'].split(' ')[-1] if False else 'EEMS', s['eems'], RGBColor(0x9A, 0xA5, 0xB1)),
        ('FTSE', s['vt'], NAVY),
        ('S&P 500', s['spy'], GOLD),
        ('Portfolio', s['port'], GREEN),
    ], num_fmt='0')
    rail_x = MARGIN + Inches(8.6)
    rail_w = SLIDE_W - MARGIN - rail_x
    chips = [
        (txt['chip_total'], _p(m.get('total_return'), lang), GREEN_DARK, GREEN_PALE, False),
        (txt['chip_cagr'], _p(m.get('cagr'), lang), INK, PAPER, False),
        (txt['chip_12m'], _p(m.get('trailing_12m'), lang, signed=True), INK, PAPER, False),
        (txt['chip_vs_eems'], _p(m.get('vs_eems_12m'), lang, signed=True), INK, PAPER, False),
        (txt['chip_sharpe'],
         (f"{m.get('sharpe'):.2f}".replace('.', ',') if m.get('sharpe') is not None else '—'),
         INK, PAPER, False),
        (txt['chip_start'], _d(data['start_date'], lang), INK, PAPER, True),
    ]
    ch, y = Inches(0.72), Inches(2.25)
    for label, value, vcol, fill, small in chips:
        _kpi(slide, rail_x, y, rail_w, ch, label, value, value_color=vcol, fill=fill,
             value_size=14, small=small)
        y += ch + Inches(0.08)
    return slide


def _slide_contributions(prs, idx, txt, lang, data):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _page_chrome(slide, idx, f"{txt['d1_kicker']}", txt['contrib_title'], txt['contrib_sub'], txt)
    ps = sorted(data['positions'], key=lambda q: (q['contribution'] if q['contribution'] is not None else 0),
                reverse=True)
    cats = [p['ticker'] or '?' for p in ps]
    vals = [p['contribution'] or 0 for p in ps]
    rets = [p['ret_pct'] or 0 for p in ps]
    colors = [GREEN if v >= 0 else RED for v in vals]
    _native_bar(slide, MARGIN, Inches(2.25), Inches(8.3), Inches(3.5), cats,
                [(txt['contrib_h_pp'], vals, GREEN)], horiz=True, labels=True, n_fmt='0.0" pp"',
                per_point_colors=colors, gap_width=40)
    table_x = MARGIN + Inches(8.6)
    table_w = SLIDE_W - MARGIN - table_x
    rows = [(p['ticker'], _p(p['ret_pct'], lang, signed=True), _p(p['contribution'], lang, signed=True))
            for p in ps]
    _pptx_table(slide, table_x, Inches(2.3), table_w, (1.4, 1.2, 1.2),
                [txt['contrib_h_ticker'], txt['contrib_h_ret'], txt['contrib_h_pp']], rows,
                row_h=Inches(0.34), size=8.5)
    m = data['metrics']
    _kpi(slide, table_x, Inches(5.35), table_w, Inches(0.9), txt['chip_total'],
         _p(m.get('total_return'), lang), value_color=GREEN_DARK, fill=GREEN_PALE, value_size=17)
    return slide


def _slide_paths(prs, idx, txt, lang, data):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _page_chrome(slide, idx, f"{txt['d1_kicker']}", txt['paths_title'], txt['paths_sub'], txt)
    cats = _axis_cats(data['dates'])
    palette = [GREEN, GREEN_DARK, GREEN_MID, NAVY, GREEN_SOFT, GOLD, GRAY_500]
    series = []
    for k, p in enumerate(data['positions']):
        series.append((p['ticker'] or '?', p['path'], palette[k % len(palette)]))
    _native_line(slide, MARGIN, Inches(2.25), Inches(12.1), Inches(4.35), cats, series, num_fmt='0')
    tf = _tbox(slide, SLIDE_W - MARGIN - Inches(1.6), Inches(1.85), Inches(1.6), Inches(0.3))
    _para(tf, txt['legend_index100'], size=7.5, color=GRAY_400, align=PP_ALIGN.RIGHT, first=True)
    return slide


def _slide_month_heat(prs, idx, txt, lang, data):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _page_chrome(slide, idx, f"{txt['d1_kicker']}", txt['month_title'], txt['month_sub'], txt)
    months_cs = ['led', 'úno', 'bře', 'dub', 'kvě', 'čen', 'čvc', 'srp', 'zář', 'říj', 'lis', 'pro']
    months_en = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
    mlabels = months_cs if lang == 'cs' else months_en
    monthly = data['metrics']['monthly']  # aligned with dates[1:]
    earned = list(data['dates'])[1:]
    years = sorted({d.year for d in earned})
    grid = {}
    for d, v in zip(earned, monthly):
        grid.setdefault(d.year, [None] * 12)[d.month - 1] = v
    headers = ['', *[str(y) for y in years]]
    rows = []
    fills = {}
    for mi in range(12):
        row = [mlabels[mi]]
        for y in years:
            v = grid.get(y, [None] * 12)[mi]
            row.append('' if v is None else (('+' if v >= 0 else '') + f'{v:.1f}'.replace('.', ',')))
            if v is not None:
                t = max(-0.99, min(0.99, v / 30.0))
                if v >= 0:
                    base = GREEN_PALE
                else:
                    base = RED_PALE
                fills[(mi, len(row) - 1)] = base
        rows.append(tuple(row))
    _pptx_table(slide, MARGIN, Inches(2.3), Inches(7.6), (1.1, *[1.5] * len(years)),
                headers, rows, row_h=Inches(0.335), size=8.5, header_size=8,
                cell_fills=fills, align={j: PP_ALIGN.CENTER for j in range(1, len(headers))})
    rail_x = MARGIN + Inches(8.0)
    rail_w = SLIDE_W - MARGIN - rail_x
    m = data['metrics']
    chips = [
        (txt['chip_mean'], _p(m.get('monthly_avg'), lang, signed=True), INK, PAPER),
        (txt['chip_pos_share'], _p(m.get('positive_months'), lang), GREEN_DARK, GREEN_PALE),
        (txt['chip_best'], (f"+{m.get('monthly_best', 0):.1f}".replace('.', ',') +
                            (' / ' if lang == 'en' else ' / ') +
                            f"{m.get('monthly_worst', 0):.1f}".replace('.', ',') + ' %'), INK, PAPER),
        (txt['chip_12m'], _p(m.get('trailing_12m'), lang, signed=True), INK, PAPER),
    ]
    ch, y = Inches(0.95), Inches(2.3)
    for label, value, vcol, fill in chips:
        _kpi(slide, rail_x, y, rail_w, ch, label, value, value_color=vcol, fill=fill, value_size=15)
        y += ch + Inches(0.13)
    return slide


def _slide_distribution(prs, idx, txt, lang, data):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _page_chrome(slide, idx, f"{txt['d2_kicker']}", txt['dist_title'], txt['dist_sub'], txt)
    m = data['metrics']
    monthly = m.get('monthly', [])
    edges = list(range(-30, 31, 5))
    counts = [sum(1 for v in monthly if edges[i] <= v < edges[i + 1] or
                  (i == len(edges) - 2 and v == edges[i + 1]))
              for i in range(len(edges) - 1)]
    bins = [('/' if lang == 'cs' else '/') + f'{edges[i]}' for i in range(len(edges) - 1)]
    bins = [f'{edges[i]}…{edges[i+1]}' for i in range(len(edges) - 1)]
    cols = [GREEN_MID if c == 0 else GREEN_SOFT for c in counts]
    # points: green for positive-centred bins, red-ish for negative
    cols = [GREEN_MID if edges[i] >= 0 else RED_PALE for i in range(len(edges) - 1)]
    _native_bar(slide, MARGIN, Inches(2.3), Inches(8.3), Inches(4.1), bins,
                [(txt['dist_count'], [c or 0 for c in counts], GREEN)],
                labels=True, n_fmt='0', gap_width=25)
    cx = MARGIN
    rail_x = MARGIN + Inches(8.6)
    rail_w = SLIDE_W - MARGIN - rail_x
    chips = [
        (txt['chip_mean'], _p(m.get('monthly_avg'), lang, signed=True)),
        (txt['chip_pos_share'], _p(m.get('positive_months'), lang)),
        (txt['chip_best'], f"+{m.get('monthly_best', 0):.1f}".replace('.', ',') + ' %'),
        (txt['chip_worst_m2'] if 'chip_worst_m2' in txt else txt['dd_chart_title'],
         f"{m.get('monthly_worst', 0):.1f}".replace('.', ',') + ' %'),
    ]
    ch, y = Inches(0.98), Inches(2.3)
    for label, value in chips:
        _kpi(slide, rail_x, y, rail_w, ch, label, value)
        y += ch + Inches(0.14)
    # skew / kurt
    y += Inches(0.02)
    _kpi(slide, rail_x, y, rail_w, Inches(0.95), ('Šikmost / špičatost' if lang == 'cs' else 'Skew / kurtosis'),
         f"{m.get('skew', 0):.2f}".replace('.', ',') +
         (' / ' if lang == 'en' else ' / ') +
         f"{m.get('kurt', 0):.2f}".replace('.', ','),
         value_size=13)
    return slide


def _slide_drawdown(prs, idx, txt, lang, data):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _page_chrome(slide, idx, f"{txt['d2_kicker']}", txt['dd_title'], txt['dd_sub'], txt)
    m = data['metrics']
    cats = _axis_cats(data['dates'])
    _native_area(slide, MARGIN, Inches(2.3), Inches(8.3), Inches(4.2), cats,
                 [(txt['dd_chart_title'], m['dd_series'], RGBColor(0x14, 0x7A, 0x4A))], n_fmt='0',
                 y_min=float(min(m['dd_series'])) * 1.15, y_max=0.0)
    rail_x = MARGIN + Inches(8.6)
    rail_w = SLIDE_W - MARGIN - rail_x
    chips = [
        (txt['chip_maxdd'], _p(m.get('max_dd'), lang), RED, RED_PALE),
        (txt['chip_under'], f"{m.get('underwater_months', 0)} " +
                            ('měsíců' if lang == 'cs' else 'months'), INK, PAPER),
        (txt['chip_ulcer'], f"{m.get('ulcer', 0):.1f}".replace('.', ','), INK, PAPER),
        (txt['chip_calmar'], f"{m.get('calmar'):.2f}".replace('.', ',') if m.get('calmar') else '—', INK, PAPER),
        (txt['chip_sortino'], f"{m.get('sortino'):.2f}".replace('.', ',') if m.get('sortino') else '—', INK, PAPER),
    ]
    ch, y = Inches(0.82), Inches(2.3)
    for label, value, vcol, fill in chips:
        _kpi(slide, rail_x, y, rail_w, ch, label, value, value_color=vcol, fill=fill, value_size=14)
        y += ch + Inches(0.1)
    return slide


def _slide_rolling(prs, idx, txt, lang, data):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _page_chrome(slide, idx, f"{txt['d2_kicker']}", txt['roll_title'], txt['roll_sub'], txt)
    dates = list(data['dates'])

    def rollvol(x):
        arr = np.array(x, dtype=float)
        d = np.diff(arr / 100.0)
        out = np.full(d.size, np.nan)
        for i in range(11, d.size):
            out[i] = d[i - 11:i + 1].std(ddof=1) * math.sqrt(12) * 100
        return out
    rv_p, rv_e = rollvol(data['series']['port']), rollvol(data['series']['eems'])
    valid = [i for i, v in enumerate(rv_p) if not np.isnan(v)]
    v0 = valid[0] if valid else 0
    # diff index i ends at dates[i+1]; labels must line up 1:1 with values
    cats = _axis_cats(dates)[v0 + 1:]
    vals_p = [float(v) for v in rv_p[v0:]]
    vals_e = [float(v) for v in rv_e[v0:]]
    cats = cats[:len(vals_p)]
    vmax = float(max(max(vals_p), max(vals_e)))
    _native_line(slide, MARGIN, Inches(2.3), Inches(9.9), Inches(4.3), cats, [
        ('EEMS', vals_e, RGBColor(0x9A, 0xA5, 0xB1)),
        ('Portfolio', vals_p, GREEN),
    ], num_fmt='0"%"', y_min=0, y_max=vmax * 1.25)
    rail_x = MARGIN + Inches(10.05)
    m = data['metrics']
    _kpi(slide, rail_x, Inches(2.3), Inches(2.6), Inches(0.9),
         txt['chip_vol'], _p(m.get('ann_vol'), lang, signed=False),
         fill=GREEN_PALE, value_color=GREEN_DARK, value_size=17)
    return slide


def _slide_regression(prs, idx, txt, lang, data):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _page_chrome(slide, idx, f"{txt['d2_kicker']}", txt['reg_title'], txt['reg_sub'], txt)
    port = np.diff(np.array(data['series']['port'], dtype=float) / 100.0) * 100
    eems = np.diff(np.array(data['series']['eems'], dtype=float) / 100.0) * 100
    n = min(len(port), len(eems))
    x, y = eems[-n:], port[-n:]
    m = data['metrics']
    beta = m.get('beta') or 0.0
    alpha = m.get('alpha_m') or 0.0
    x0, x1 = float(np.min(x)), float(np.max(x))
    xy_pts = list(zip([round(float(v), 2) for v in x], [round(float(v), 2) for v in y]))
    # the OLS fit line used to be a dense dot series that LibreOffice connected
    # into squiggly lines across the chart - the fit lives in the KPI rail now
    _native_scatter(slide, MARGIN, Inches(2.3), Inches(8.3), Inches(4.3), [
        ('EEMS → ' + ('portfolio' if lang == 'en' else 'pozice'), xy_pts, GREEN, False),
    ], x_min=min(0, x0 * 1.05), x_max=x1 * 1.08, y_min=min(0, min(y) * 1.15),
        y_max=max(y) * 1.2, num_fmt='0.0')
    rail_x = MARGIN + Inches(8.6)
    rail_w = SLIDE_W - MARGIN - rail_x
    chips = [
        (txt['chip_beta'], f"{beta:.2f}".replace('.', ','), INK, PAPER),
        (txt['chip_alpha'], (f"{alpha_n:.1f}".replace('.', ',') + ' %' if (alpha_n := alpha * 12) else '—'), INK, PAPER),
        (txt['chip_r2'], f"{m.get('r2'):.2f}".replace('.', ',') if m.get('r2') else '—', INK, PAPER),
        (txt['chip_tstat'], f"{m.get('tstat'):.1f}".replace('.', ',') if m.get('tstat') else '—', INK, PAPER),
        (txt['chip_td'], _p(m.get('tracking_diff'), lang), GREEN_DARK, GREEN_PALE),
        (txt['chip_te'], _p(m.get('tracking_err'), lang, signed=False), INK, PAPER),
    ]
    ch, y = Inches(0.68), Inches(2.3)
    for label, value, vcol, fill in chips:
        _kpi(slide, rail_x, y, rail_w, ch, label, value, value_color=vcol, fill=fill, value_size=14)
        y += ch + Inches(0.08)
    return slide


def _slide_tails(prs, idx, txt, lang, data):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _page_chrome(slide, idx, f"{txt['d2_kicker']}", txt['tail_title'], txt['tail_sub'], txt)
    m = data['metrics']
    monthly = m.get('monthly', [])
    worst = sorted(float(v) for v in monthly)[:5]
    cats = ['#1', '#2', '#3', '#4', '#5']
    vals = [abs(v) for v in worst]
    colors = [RED] * len(vals)
    _native_bar(slide, MARGIN, Inches(2.3), Inches(8.3), Inches(3.55), cats,
                [(txt['tail_worst_title'], vals, RED)], horiz=True, labels=True,
                n_fmt='0.0" %"', per_point_colors=colors, gap_width=60,
                y_min=0.0, y_max=max(vals) * 1.22)
    tf = _tbox(slide, MARGIN, Inches(6.05), Inches(8.3), Inches(0.4))
    _para(tf, ('Plné pruhy: velikost měsíční ztráty.' if lang == 'cs'
               else 'Bar length: size of the monthly loss.'),
          size=8, color=GRAY_400, first=True)
    rail_x = MARGIN + Inches(8.6)
    rail_w = SLIDE_W - MARGIN - rail_x
    chips = [
        (txt['tail_var95'], _p(m.get('var95'), lang), RED, RED_PALE),
        (txt['tail_cvar95'], _p(m.get('cvar95'), lang), RED, RED_PALE),
        (txt['chip_sortino'], f"{m.get('sortino'):.2f}".replace('.', ',') if m.get('sortino') else '—', INK, PAPER),
        ((f"Roční volatilita" if lang == 'cs' else 'Annualised volatility'),
         _p(m.get('ann_vol'), lang, signed=False), INK, PAPER),
    ]
    ch, y = Inches(0.86), Inches(2.3)
    for label, value, vcol, fill in chips:
        _kpi(slide, rail_x, y, rail_w, ch, label, value, value_color=vcol or INK, fill=fill or PAPER,
             value_size=14)
        y += ch + Inches(0.1)
    return slide


def _slide_forward(prs, idx, txt, lang, data):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _page_chrome(slide, idx, f"{txt['d3_kicker']}", txt['fwd_title'], txt['fwd_sub'], txt)
    m = data['metrics']
    pct = m.get('boot_pct') or {}
    cats = [f'+{kk}' for kk in range(1, 13)]
    _native_line(slide, MARGIN, Inches(2.3), Inches(9.9), Inches(4.2), cats, [
        (txt['fwd_p90'], list(pct.get(90)), RGBColor(0xB5, 0xE0, 0xCC)),
        (txt['fwd_p75'], list(pct.get(75)), GREEN_MID),
        (txt['fwd_p50'], list(pct.get(50)), GREEN),
        (txt['fwd_p25'], list(pct.get(25)), GREEN_MID),
        (txt['fwd_p10'], list(pct.get(10)), RGBColor(0xB5, 0xE0, 0xCC)),
    ], y_min=min(0.0, min(list(pct.get(10))) if pct.get(10) is not None and len(pct.get(10)) else 0.0), num_fmt='+0"%')
    rail_x = MARGIN + Inches(10.05)
    _kpi(slide, rail_x, Inches(2.3), Inches(2.6), Inches(0.9), txt['chip_fwd_median'],
         _p(m.get('med_12m'), lang), fill=GREEN_PALE, value_color=GREEN_DARK, value_size=17)
    _kpi(slide, rail_x, Inches(3.3), Inches(2.6), Inches(0.9), txt['chip_fwd_pos'],
         _p(m.get('prob_pos'), lang, signed=False), fill=GREEN_PALE, value_color=GREEN_DARK,
         value_size=17)
    tf = _tbox(slide, rail_x, Inches(4.4), Inches(2.6), Inches(1.6))
    _para(tf, ('Převzorkovaná historie – ne slib.' if lang == 'cs'
               else 'Resampled history - not a promise.'),
          size=8, color=GRAY_400, line=1.2, first=True)
    return slide


def _slide_benchmarks(prs, idx, txt, lang, data):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _page_chrome(slide, idx, f"{txt['d1_kicker']}", txt['bench_title'], txt['bench_sub'], txt)
    s, m = data['series'], data['metrics']

    def per(x, n=13):
        arr = 1.0 + np.array(x, dtype=float) / 100.0
        return float(arr[-1] / arr[-n] - 1) * 100 if arr.size >= n else None
    rows = [
        ('Portfolio', _p(per(s['port']), lang, signed=True), _p(s['port'][-1], lang, signed=True)),
        ('S&P 500', _p(per(s['spy']), lang, signed=True), _p(s['spy'][-1], lang, signed=True)),
        ('FTSE All-World', _p(per(s['vt']), lang, signed=True), _p(s['vt'][-1], lang, signed=True)),
        ('EEMS', _p(per(s['eems']), lang, signed=True), _p(s['eems'][-1], lang, signed=True)),
    ]
    _pptx_table(slide, MARGIN, Inches(2.3), Inches(5.6), (1.6, 1, 1),
                ['', txt['h_12m'], txt['h_incept']], rows, row_h=Inches(0.42), size=10)
    # correlation matrix of monthly returns
    pm, em_, sm_, vm_ = (np.diff(np.array(s['port']) / 100.0),
                         np.diff(np.array(s['eems']) / 100.0),
                         np.diff(np.array(s['spy']) / 100.0),
                         np.diff(np.array(s['vt']) / 100.0))
    n_corr = min(len(pm), len(em_), len(sm_), len(vm_))
    mat = np.round(np.corrcoef(np.vstack([pm[-n_corr:], em_[-n_corr:], sm_[-n_corr:], vm_[-n_corr:]])), 2)
    labels = ['Port.', 'EEMS', 'S&P', 'FTSE']
    rt = []
    c = {}
    for i in range(4):
        row = [labels[i]] + [f'{mat[i, j]:.2f}'.replace('.', ',') if lang == 'cs' else f'{mat[i, j]:.2f}'
                             for j in range(4)]
        rt.append(tuple(row))
        for j in range(4):
            v = mat[i, j]
            base = GREEN_PALE if v > 0.6 else (PAPER if v > 0.2 else RED_PALE)
            c[(i, j + 1)] = base if i != j else GREEN_SOFT
    _pptx_table(slide, MARGIN, Inches(4.5), Inches(5.6), (1.2, 1, 1, 1, 1),
                [txt['corr_title'], 'Port.', 'EEMS', 'S&P', 'FTSE'], rt,
                row_h=Inches(0.4), size=9.5, cell_fills=c,
                align={j: PP_ALIGN.CENTER for j in range(1, 5)})
    rail_x = MARGIN + Inches(6.6)
    rail_w = SLIDE_W - MARGIN - rail_x
    chips = [
        (txt['chip_beta'], f"{m.get('beta'):.2f}".replace('.', ',') if m.get('beta') else '—'),
        (txt['chip_ir'] if 'chip_ir' in txt else 'IR', f"{m.get('info_ratio', 0):.2f}".replace('.', ',')),
        (txt['chip_te'], _p(m.get('tracking_err'), lang, signed=False)),
    ]
    ch, y = Inches(0.95), Inches(2.3)
    for label, value in chips:
        _kpi(slide, rail_x, y, rail_w, ch, label, value, value_size=15)
        y += ch + Inches(0.15)
    return slide


def _slide_close(prs, idx, txt, lang, data):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _rect(slide, 0, 0, SLIDE_W, SLIDE_H, GREEN_DEEP)
    _rule(slide, MARGIN, Inches(0.9), Inches(0.42), color=WHITE, thickness=0.032)
    tf = _tbox(slide, MARGIN, Inches(1.16), Inches(8), Inches(0.3))
    _para(tf, txt['close_kicker'], size=10, color=MINT_TEXT, bold=True, spc=240, first=True)
    tf = _tbox(slide, MARGIN, Inches(2.3), Inches(10.6), Inches(1.0))
    _para(tf, txt['close_title'], size=34, color=WHITE, bold=True, first=True)
    tf = _tbox(slide, MARGIN, Inches(3.3), Inches(9.4), Inches(0.7))
    _para(tf, txt['close_sub'], size=12, color=MINT_TEXT, line=1.3, first=True)
    y = SLIDE_H - Inches(2.15)
    _rect(slide, MARGIN, y, Inches(4.6), Inches(1.16), GREEN_GHOST, radius=0.06)
    tf = _tbox(slide, MARGIN + Inches(0.28), y + Inches(0.2), Inches(4.1), Inches(0.8))
    _para(tf, txt['accepting'], size=10.5, color=WHITE, bold=True, first=True, space_after=4)
    _para(tf, txt['club'], size=8.5, color=MINT_TEXT)
    tf = _tbox(slide, MARGIN + Inches(5.2), y + Inches(0.3), CONTENT_W - Inches(5.2), Inches(0.6))
    _para(tf, txt['disclaimer'], size=8.5, color=MINT_TEXT, line=1.25, first=True)
    return slide


# ------------------------------------------------------------------
# Entrance
# ------------------------------------------------------------------

def build_pitch_deck(lang: str = 'cs', window_years: Optional[int] = None):
    """Render the deck; returns (BytesIO, filename)."""
    from datetime import date as _date
    txt = _txt(lang)
    data = _collect_full(lang, window_years)
    tracker = data['tracker']
    pipe = data['pipe']
    m = data['metrics']

    prs = Presentation()
    prs.slide_width, prs.slide_height = SLIDE_W, SLIDE_H

    # 01 LIVE THE BOOK
    _slide_cover(prs, txt, lang, data)
    _slide_live_book(prs, 2, txt, lang, data, tracker)
    _slide_live_returns(prs, 3, txt, lang, data, tracker)
    _slide_nav_track(prs, 4, txt, lang, data, tracker)
    _slide_alloc(prs, 5, txt, lang, data, tracker)
    _slide_purchase_log(prs, 6, txt, lang, data)
    _slide_live_paths(prs, 7, txt, lang, data, tracker)

    # 02 RESEARCH FACTORY
    _slide_divider(prs, txt['d2_kicker'], txt['d2_title'], txt['d2_sub'])
    _slide_funnel2(prs, 9, txt, lang, data)
    _slide_factory_monthly(prs, 10, txt, lang, data, pipe)
    _slide_factory_year(prs, 11, txt, lang, data)
    _slide_sector_table(prs, 12, txt, lang, data, None, _ft(lang)['sector_title_all'],
                        _ft(lang)['sector_sub_all'])
    _slide_sector_table(prs, 13, txt, lang, data, ('On Watchlist',),
                        _ft(lang)['sector_title_watch'], _ft(lang)['sector_sub_watch'])
    _slide_sector_compare(prs, 14, txt, lang, data)
    _slide_analysts_ft(prs, 15, txt, lang, data)
    _slide_top_bottom(prs, 16, txt, lang, data, worst=False)
    _slide_top_bottom(prs, 17, txt, lang, data, worst=True)
    _slide_exclusions(prs, 18, txt, lang, data)

    # 03 PERFORMANCE (vote-approved simulation, labelled as such)
    _slide_divider(prs, txt['d1_kicker'], txt['d1_title'],
                   ('Simulace hlasovacího portfolia; živé pozice jsou nahoře.' if lang == 'cs'
                    else 'Simulation of the vote-approved book; live positions are above.'))
    _slide_performance(prs, 20, txt, lang, data)
    _slide_contributions(prs, 21, txt, lang, data)
    _slide_paths(prs, 22, txt, lang, data)

    # 04 RISK
    _slide_divider(prs, txt['d2_kicker'], txt['d2_title'], txt['d2_sub'])
    _slide_month_heat(prs, 24, txt, lang, data)
    _slide_distribution(prs, 25, txt, lang, data)
    _slide_drawdown(prs, 26, txt, lang, data)
    _slide_rolling(prs, 27, txt, lang, data)
    _slide_tails(prs, 28, txt, lang, data)
    _slide_regression(prs, 29, txt, lang, data)
    _slide_benchmarks(prs, 30, txt, lang, data)

    # 05 FORWARD
    _slide_divider(prs, txt['d3_kicker'], txt['d3_title'], txt['d3_sub'])
    _slide_forward(prs, 32, txt, lang, data)
    _slide_close(prs, 33, txt, lang, data)

    stream = io.BytesIO()
    prs.save(stream)
    stream.seek(0)
    filename = f'KI_AM_portfolio_deck_{lang}_{_date.today().isoformat()}.pptx'
    return stream, filename


def _slide_divider(prs, kicker, title, sub):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _rect(slide, 0, 0, SLIDE_W, SLIDE_H, GREEN_DEEP)
    big = '02' if kicker and kicker.upper().find('RISK') >= 0 else '02'
    tf = _tbox(slide, SLIDE_W - Inches(4.6), Inches(0.6), Inches(4.0), Inches(4.2))
    _para(tf, big, size=190, color=GREEN_GHOST, bold=True, align=PP_ALIGN.RIGHT, first=True, line=0.85)
    _rule(slide, MARGIN, Inches(3.06), Inches(0.42), color=WHITE, thickness=0.032)
    tf = _tbox(slide, MARGIN, Inches(3.3), Inches(7.6), Inches(0.3))
    _para(tf, kicker, size=10, color=MINT_TEXT, bold=True, spc=240, first=True)
    tf = _tbox(slide, MARGIN, Inches(3.62), Inches(8.6), Inches(0.75))
    _para(tf, title, size=34, color=WHITE, bold=True, first=True)
    tf = _tbox(slide, MARGIN, Inches(4.5), Inches(6.8), Inches(0.8))
    _para(tf, sub, size=11, color=MINT_TEXT, line=1.25, first=True)
    return slide


# ------------------------------------------------------------------
# Live book - from the club's Portfolio tracker (Patria broker export)
# The tracker file ships with the repo (app/utils/data/portfolio_tracker.xlsx);
# KI_TRACKER_PATH can point at a fresher export.
# ------------------------------------------------------------------

def _tracker_path() -> str:
    import os
    return os.environ.get('KI_TRACKER_PATH') or os.path.join(
        os.path.dirname(__file__), 'data', 'portfolio_tracker.xlsx')


def _load_tracker() -> Dict:
    """Patria export: securities block + cash block + monthly NAV from Perf table."""
    import os
    import pandas as pd
    path = _tracker_path()
    if not os.path.exists(path):
        raise FileNotFoundError(f'Portfolio tracker not found at {path}')
    xl = pd.read_excel(path, sheet_name='Portfolio', header=None)

    positions, cash_czk, nav_czk = [], None, None
    in_sec = False
    for _, row in xl.iterrows():
        c0 = str(row.iloc[0]) if pd.notna(row.iloc[0]) else ''
        if c0 == 'Cenné papíry':
            in_sec = True
        elif in_sec and (c0 == 'Peněžní zůstatky'):
            in_sec = False
        if in_sec and pd.notna(row.iloc[3]) and pd.notna(row.iloc[4]) \
                and c0 and not c0.startswith('Cenné papíry'):
            try:
                positions.append({
                    'name': c0, 'ticker': str(row.iloc[1]), 'market': str(row.iloc[2]),
                    'qty': float(row.iloc[3]), 'avg_cost': float(row.iloc[4]),
                    'mkt_price': float(row.iloc[5]), 'unreal_pct': float(row.iloc[6]) * 100.0,
                    'value_local': float(row.iloc[7]), 'value_czk': float(row.iloc[8]),
                })
            except (TypeError, ValueError):
                pass
        if c0 == 'Peníze celkem':
            cash_czk = float(row.iloc[5])
        if c0 == 'Cenné papíry celkem CZK':
            sec_czk = float(row.iloc[7])

    nav_czk = cash_czk + sec_czk

    # monthly track record from Perf table (recorded statements)
    perf = pd.read_excel(path, sheet_name='Perf table', header=None)
    nav_series, pnl_series = [], []
    for ri, row in perf.iterrows():
        label = str(row.iloc[1]) if pd.notna(row.iloc[1]) else ''
        if label in ('value', 'PnL'):
            # the labelled ROW is the Jan..Dec header; the year row under it holds the numbers
            if ri + 1 >= perf.shape[0]:
                continue
            for ci in range(2, 14):
                mo0 = perf.iloc[ri, ci]
                if pd.isna(mo0) or str(mo0) not in ('Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                                                    'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'):
                    continue
                try:
                    v = float(perf.iloc[ri + 1, ci])
                except (TypeError, ValueError):
                    continue
                if label == 'value':
                    # NAV block values are 100k-scale CZK; the allocation blocks are small
                    if v > 100000:
                        nav_series.append((str(mo0), v))
                else:
                    pnl_series.append((str(mo0), v * 100.0))
    # keep the dated (2026) block: Apr..Aug filled, then None until year end
    nav_series = [(mo, v) for mo, v in nav_series if v is not None]
    nav_map = {mo: v for mo, v in nav_series}
    pnl_map = {mo: v for mo, v in pnl_series}
    return {
        'positions': positions, 'cash_czk': cash_czk, 'nav_czk': nav_czk,
        'sec_czk': sec_czk, 'nav_series': nav_series, 'pnl_series': pnl_series,
        'nav_map': nav_map,
        'pnl_map': dict(pnl_series),
        'export_date': '29. 8. 2026',
    }


def _invested_positions() -> List[Dict]:
    """The invested book: DB purchases reaching back to the actual buy dates."""
    rows = (PortfolioPurchase.query
            .with_entities(PortfolioPurchase.analysis_id, PortfolioPurchase.purchase_date)
            .all())
    out = []
    for aid, bought in rows:
        a = Analysis.query.get(aid)
        if not a:
            continue
        c = Company.query.get(a.company_id)
        pc = (PerformanceCalculation.query.filter_by(analysis_id=aid)
              .order_by(PerformanceCalculation.calculation_date.desc()).first())
        # price at the purchase date (not the analysis date)
        bought_px = (StockPrice.query.filter(StockPrice.company_id == a.company_id,
                                             StockPrice.date <= bought)
                     .order_by(StockPrice.date.desc()).first())
        px = float(bought_px.close_price) if bought_px else float(pc.price_at_analysis) if pc else None
        cur = float(pc.price_current) if pc else None
        ret = (cur / px - 1.0) * 100.0 if cur and px else None
        out.append({
            'ticker': c.ticker_symbol, 'name': c.name, 'bought': bought,
            'entry_px': px, 'cur_px': cur, 'ret_pct': ret,
            'analysis_date': a.analysis_date, 'analysis_id': aid,
        })
    return sorted(out, key=lambda r: r['bought'])


def _sector_stats(statuses: Optional[Tuple[str, ...]] = None) -> List[Dict]:
    """Sector stats with ONE row per analysis - the latest calculation only.

    The join through performance_calculations used to multiply every analysis
    by its daily recalculation rows (630 calc rows for 82 analyses), which
    inflated counts and weighted averages by how often a position was
    re-priced. Returns are now deduplicated per analysis first.
    """
    rows = db.session.query(
        CompanySectorCache.sector,
        PerformanceCalculation.analysis_id,
        func.max(PerformanceCalculation.calculation_date),
        PerformanceCalculation.return_pct,
    ).join(Company, CompanySectorCache.company_id == Company.id) \
     .join(Analysis, Analysis.company_id == Company.id) \
     .join(PerformanceCalculation, PerformanceCalculation.analysis_id == Analysis.id) \
     .group_by(CompanySectorCache.sector, PerformanceCalculation.analysis_id)
    per_analysis = db.session.query(
        PerformanceCalculation.analysis_id,
        PerformanceCalculation.calculation_date,
        PerformanceCalculation.return_pct,
    ).all()
    newest = {}
    for aid, calcd, ret in per_analysis:
        if aid not in newest or calcd > newest[aid][0]:
            newest[aid] = (calcd, ret)
    status_of = {a.id: a.status for a in Analysis.query.with_entities(Analysis.id, Analysis.status).all()}
    sector_of = {}
    for c, sec in db.session.query(Company.id, CompanySectorCache.sector) \
            .join(CompanySectorCache, CompanySectorCache.company_id == Company.id):
        sector_of[c] = sec
    from collections import defaultdict
    grouped = defaultdict(lambda: {'count': 0, 'returns': []})
    for aid, (_calcd, ret) in newest.items():
        sec = sector_of.get(aid)
        if sec is None:
            continue
        if statuses and status_of.get(aid) not in statuses:
            continue
        e = grouped.setdefault(sec, {'count': 0, 'returns': []})
        e['count'] += 1
        if ret is not None:
            e['returns'].append(float(ret))
    out = []
    for sector, e in grouped.items():
        rets = e['returns']
        out.append({
            'sector': sector, 'analyses': e['count'],
            'avg_return': (sum(rets) / len(rets)) if rets else None,
            'stddev': (float(np.std(rets, ddof=1)) if len(rets) > 1 else 0.0),
            'max': max(rets) if rets else None, 'min': min(rets) if rets else None,
        })
    return sorted(out, key=lambda s: -(s['avg_return'] or 0))


def _pipeline_counts() -> Dict:
    """Distinctions per month and status, so the deck can chart the factory."""
    analyses = Analysis.query.all()
    months, approved_m = {}, {}
    for a in analyses:
        if not a.analysis_date:
            continue
        key = a.analysis_date.strftime('%m/%y')
        months[key] = months.get(key, 0) + 1
        if a.status == 'On Watchlist':
            approved_m[key] = approved_m.get(key, 0) + 1
    keys = sorted(months)
    return {
        'keys': keys,
        'total': [months[k] for k in keys],
        'approved': [approved_m.get(k, 0) for k in keys],
        'all_n': len(analyses),
        'watchlist_n': sum(1 for a in analyses if a.status == 'On Watchlist'),
        'purchases_n': PortfolioPurchase.query.count(),
    }


# ------------------------------------------------------------------
# Extra copy for the tracker / research-factory slides (hand-written Czech)
# ------------------------------------------------------------------

_FT = {
    'en': {
        'book_kicker': 'LIVE BOOK', 'book_title': 'The live book',
        'book_sub': 'The Patria export with quantities and average cost, exactly as the broker '
                    'reports it. Invested dates come from the club purchase log.',
        'h_qty': 'Qty', 'h_cost': 'Avg cost', 'h_mkt': 'Price', 'h_pnl': 'P&L',
        'h_value_czk': 'Value (CZK)', 'h_invested': 'Invested',
        'book_ret_title': 'Unrealised P&L by position',
        'book_ret_sub': 'Percent since average cost, as reported by the broker.',
        'nav_kicker': 'TRACK RECORD', 'nav_title': 'NAV, month by month',
        'nav_sub': 'Recorded club statements; the May figure is also linked to the Patria export.',
        'h_month': 'Month', 'h_nav': 'NAV (CZK)', 'h_pnlpct': 'Return',
        'nav_chart': 'NAV (CZK)',
        'alloc_kicker': 'ALLOCATION', 'alloc_title2': 'Where the money sits',
        'alloc_sub2': 'Cash versus the seven operating positions, from the same export.',
        'alloc_cash': 'Cash', 'alloc_pos': 'Positions',
        'log_kicker': 'PURCHASE LOG', 'log_title': 'The full purchase log',
        'log_sub': 'Every investment the club logged, entry price from the price database at the buy date.',
        'live_paths_title': 'Live positions since invested',
        'live_paths_sub': 'Each live position, indexed to 100 on the day the club actually bought.',
        'bin_kicker': 'RESEARCH FACTORY', 'bin_title': 'The research factory',
        'bin_title': 'The research factory',
        'bin_sub': 'From every analysis to the positions the committee actually buys.',
        'funnel_h_analysed': 'analyses', 'funnel_h_watch': 'committee-approved',
        'funnel_h_bought': 'bought',
        'per_title': 'Analyses per month', 'per_sub': 'New analyses each month versus committee approvals.',
        'cum_title': 'Cumulative research output',
        'cum_approved': 'approved', 'cum_total': 'analyses',
        'sector_kicker': 'SECTOR CUTS', 'sector_title_all': 'Every analysis, by sector',
        'sector_title_watch': 'Committee-approved, by sector',
        'sector_sub_all': 'Analysed positions with price data (42 of 131): count, average return, sigma, worst.',
        'sector_sub_watch': 'Committee-approved positions with price data (21): the committee never adds positions without analysis.',
        'h_sector': 'Sector', 'h_n': 'n', 'h_avg': 'Avg return', 'h_std': 'σ', 'h_min': 'Worst',
        'sector_cmp_title': 'Picked by the committee, or just analysed?',
        'sector_cmp_sub': 'Average return per sector: everything analysed versus what the committee approved.',
        'sector_cmp_all': 'all analysed', 'sector_cmp_watch': 'committee-approved',
        'analyst_title': 'The analyst bench', 'analyst_sub': 'Workload and results per analyst.',
        'top_title': 'Ten best research calls', 'top_sub': 'Across every analysed company, by latest return.',
        'bottom_title': 'Ten worst research calls',
        'year_kicker': 'PER YEAR', 'year_title': 'Research volume per year',
        'year_sub': 'Analyses written versus committee-approved, per calendar year.',
        'excl_title': 'What stays out of the book',
        'excl': [
            ('Tobacco, weapons, gambling', 'and companies doing real environmental or social harm'),
            ('"Cursed" sectors', 'chronically low-ROIC industries airlines-style'),
            ('Honesty', 'any history of accounting fraud, integrity failure or governance red flags'),
        ],
    },
    'cs': {
        'book_kicker': 'ŽIVÁ KNIHA', 'book_title': 'Živá kniha (Patria)',
        'book_sub': 'Export z Patrii s počty kusů a průměrnou pořizovací cenou, přesně tak, jak '
                    'hlásí burza. Data nákupů jsou z klubového logu',
        'h_qty': 'Ks', 'h_cost': 'Průměrná nákupní', 'h_mkt': 'Kurz', 'h_pnl': 'P&L',
        'h_value_czk': 'Hodnota (CZK)', 'h_invested': 'Investováno',
        'book_ret_title': 'Nerealizovaný zisk po pozicích',
        'book_ret_sub': 'Procento od průměrné pořizovací ceny, jak ho hlásí Patria.',
        'nav_kicker': 'TRACK RECORD', 'nav_title': 'NAV měsíc po měsíci',
        'nav_sub': 'Zaznamenané výkazy klubu; květnová hodnota navazuje na Patria export.',
        'h_month': 'Měsíc', 'h_nav': 'NAV (CZK)', 'h_pnlpct': 'Výnos',
        'nav_chart': 'NAV (CZK)',
        'alloc_kicker': 'ROZLOŽENÍ', 'alloc_title2': 'Kde leží peníze',
        'alloc_sub2': 'Hotovost proti sedmi provozovaným pozicím, ze stejného exportu.',
        'alloc_cash': 'Hotovost', 'alloc_pos': 'Pozice',
        'log_kicker': 'LOG NÁKUPŮ', 'log_title': 'Kompletní log nákupů',
        'log_sub': 'Každá investice, kterou klub zapsal; vstupní cena z databáze kurzů na nákupní datum.',
        'live_paths_title': 'Živé pozice od investice',
        'live_paths_sub': 'Každá živá pozice v procentech od svého nákupního dne.',
        'bin_kicker': 'VZKUMNÁ TOVÁRNA', 'bin_title': 'Výzkumná továrna',
        'bin_sub': 'Od každé analýzy až k pozicím, které výbor skutečně kupuje.',
        'funnel_h_analysed': 'analýz celkem', 'funnel_h_watch': 'schváleno výborem',
        'funnel_h_bought': 'nakoupeno',
        'per_title': 'Analýzy po měsících', 'per_sub': 'Nové analýzy a výborem schválené pozice každý měsíc.',
        'cum_title': 'Kumulativní výstup výzkumu',
        'cum_approved': 'schváleno', 'cum_total': 'analýz',
        'sector_kicker': 'SEKTOROVÝ ŘEZ', 'sector_title_all': 'Všechny analýzy podle sektorů',
        'sector_title_watch': 'Výborem schválené, podle sektoru',
        'sector_sub_all': 'Analyzované pozice s oceněním (42 z 131): počet, průměrný výnos, rozptyl a nejhorší měsíc.',
        'sector_sub_watch': 'Schválené pozice s oceněním (21): stejná statistika, výbor nepřidává pozice bez analýzy.',
        'h_sector': 'Sektor', 'h_n': 'n', 'h_avg': 'Průměr výnos', 'h_std': 'σ', 'h_min': 'Nejhorší',
        'sector_cmp_title': 'Prošlo výborem, nebo jen analýza?',
        'sector_cmp_sub': 'Průměrný výnos sektoru: vše analyzované versus, co výbor schválil.',
        'sector_cmp_all': 'vše analyzované', 'sector_cmp_watch': 'schváleno výborem',
        'analyst_title': 'Analytická lavice', 'analyst_sub': 'Objem práce a výsledky jednotlivých analytiků.',
        'top_title': 'Deset nejlepších analýz', 'top_sub': 'Napříč všemi analyzovanými firmami, podle nejnovější výnos.',
        'bottom_title': 'Deset nejhorších výzev',
        'year_kicker': 'PO ROCÍCH', 'year_title': 'Objem výzkumu leta', 'year_sub': 'Analyzováno a výborem schvalováno podle kalendářních let.',
        'excl_title': 'Co do knihy nepatří',
        'excl': [
            ('Tabák, zbraně, hazard', 'a firmy, které výrazně škodí životnímu prostředí či společnosti'),
            ('„Prokletá“ odvětví', 'chronicky nízká návratnost kapitálu, stylem aerolinky'),
            ('Poctivost', 'jakákoli historie účetních podvodů, selhání integrity a governance'),
        ],
    },
}


def _ft(lang: str) -> dict:
    return _FT['cs'] if lang == 'cs' else _FT['en']


# ------------------------------------------------------------------
# Live book slides (tracker)
# ------------------------------------------------------------------

def _invert_tracker_by_ticker(tracker: Dict) -> Dict[str, Dict]:
    """Help live positions match the DB companies (NLB vs NLB.L, KAP vs KAP.IL)."""
    out = {}
    for p in tracker['positions']:
        out[p['ticker']] = p
    return out


def _match_company(ticker: str) -> Optional[Company]:
    for t in (ticker, ticker.split('.')[0]):
        c = Company.query.filter(Company.ticker_symbol == t).first()
        if c:
            return c
        c = Company.query.filter(Company.ticker_symbol.like(f'{t}%')).first()
        if c:
            return c
    return None


def _slide_live_book(prs, idx, txt, lang, data, tracker):
    ft = _ft(lang)
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _page_chrome(slide, idx, ft['book_kicker'], ft['book_title'], ft['book_sub'], txt)
    invested = {r['ticker'].split('.')[0]: r['bought'] for r in _invested_positions()}
    rows = []
    for p in tracker['positions']:
        rows.append((p['ticker'], p['name'][:24], f"{p['qty']:g}", _px(p['avg_cost'], lang),
                     _px(p['mkt_price'], lang), _p(p['unreal_pct'], lang, signed=True),
                     _px(p['value_czk'], lang),
                     _d(invested[p['ticker'].split('.')[0]], lang)
                     if p['ticker'].split('.')[0] in invested else '—'))
    _pptx_table(slide, MARGIN, Inches(2.25), Inches(8.6), (1.1, 2.0, 0.8, 1.15, 1.0, 0.9, 1.55, 1.15),
                [txt['h_ticker'], txt['h_name'], ft['h_qty'], ft['h_cost'], ft['h_mkt'],
                 ft['h_pnl'], ft['h_value_czk'], ft['h_invested']], rows,
                row_h=Inches(0.42), size=9)
    rail_x = MARGIN + Inches(8.9)
    rail_w = SLIDE_W - MARGIN - rail_x
    m = data['metrics']
    chips = [
        (ft['h_value_czk'] + ' · ' + ft['alloc_pos'], _px(tracker['sec_czk'], lang), INK, PAPER),
        (ft['alloc_cash'], _px(tracker['cash_czk'], lang), INK, PAPER),
        ('NAV', _px(tracker['nav_czk'], lang), GREEN_DARK, GREEN_PALE),
        (txt['chip_total'] + ' (' + ft['alloc_pos'] + ')',
         _p(sum(p['unreal_pct'] for p in tracker['positions']) / len(tracker['positions']), lang,
            signed=True), GREEN_DARK, GREEN_PALE),
    ]
    ch, y = Inches(0.92), Inches(2.25)
    for label, value, vcol, fill in chips:
        _kpi(slide, rail_x, y, rail_w, ch, label, value, value_color=vcol, fill=fill,
             value_size=15)
        y += ch + Inches(0.11)
    return slide


def _slide_live_returns(prs, idx, txt, lang, data, tracker: Dict):
    ft = _ft(lang)
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _page_chrome(slide, idx, ft['book_kicker'], ft['book_ret_title'], ft['book_ret_sub'], txt)
    ps = sorted(tracker['positions'], key=lambda p: p['unreal_pct'], reverse=True)
    cats = [p['ticker'] for p in ps]
    vals = [float(p['unreal_pct']) for p in ps]
    colors = [GREEN if v >= 0 else RED for v in vals]
    _native_bar(slide, MARGIN, Inches(2.3), Inches(8.3), Inches(4.0), cats,
                [(ft['h_pnl'], vals, GREEN)], horiz=True, labels=True, n_fmt='0.0',
                per_point_colors=colors, gap_width=45, y_min=0.0, y_max=max(vals + [0]) * 1.2)
    rail_x = MARGIN + Inches(8.6)
    rail_w = SLIDE_W - MARGIN - rail_x
    chips = [
        (ft['h_pnl'] + ' — ' + (max(ps, key=lambda p: p['unreal_pct'])['ticker']),
         _p(max(p['unreal_pct'] for p in ps), lang, signed=True), GREEN_DARK, GREEN_PALE),
        (ft['h_pnl'] + ' — ' + (min(ps, key=lambda p: p['unreal_pct'])['ticker']),
         _p(min(p['unreal_pct'] for p in ps), lang, signed=True), RED, RED_PALE),
        (('Úspěšnost' if lang == 'cs' else 'Win rate'),
         _p(data['live_win_rate'], lang), INK, PAPER),
    ]
    ch, y = Inches(0.95), Inches(2.3)
    for label, value, vcol, fill in chips:
        _kpi(slide, rail_x, y, rail_w, ch, label, value, value_color=vcol, fill=fill, value_size=16)
        y += ch + Inches(0.16)
    return slide


def _slide_nav_track(prs, idx, txt, lang, data, tracker: Dict):
    ft = _ft(lang)
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _page_chrome(slide, idx, ft['nav_kicker'], ft['nav_title'], ft['nav_sub'], txt)
    nav = tracker['nav_series']
    pnl = tracker.get('pnl_map', {})
    rows = []
    for mo, v in reversed(nav):
        p = pnl.get(mo)
        bad = p is None or (isinstance(p, float) and math.isnan(p))
        rows.append((mo, _px(v, lang), '—' if bad else _p(p, lang, signed=True)))
    _pptx_table(slide, MARGIN, Inches(2.3), Inches(4.6), (1.0, 1.4, 1.0),
                [ft['h_month'], ft['h_nav'], ft['h_pnlpct']], rows,
                row_h=Inches(0.4), size=10)
    cats = [x[0] for x in nav]
    vals = [x[1] for x in nav]
    _native_line(slide, MARGIN + Inches(4.9), Inches(2.3), Inches(7.6), Inches(3.6), cats, [
        (ft['nav_chart'], vals, GREEN),
    ], num_fmt='#,##0')
    if vals:
        _kpi(slide, MARGIN + Inches(4.9), Inches(6.05), Inches(3.4), Inches(0.85),
             txt['chip_total'], _p((vals[-1] / vals[0] - 1) * 100, lang),
             fill=GREEN_PALE, value_color=GREEN_DARK, value_size=16)
    return slide


def _slide_alloc(prs, idx, txt, lang, data, tracker: Dict):
    ft = _ft(lang)
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _page_chrome(slide, idx, ft['alloc_kicker'], ft['alloc_title2'], ft['alloc_sub2'], txt)
    labels = [p['ticker'] for p in tracker['positions']] + [ft['alloc_cash']]
    vals = [p['value_czk'] for p in tracker['positions']] + [tracker['cash_czk']]
    palette = [GREEN, GREEN_DARK, GREEN_MID, NAVY, GOLD, GRAY_500, GREEN_SOFT, GRAY_400]
    _native_donut(slide, MARGIN, Inches(2.35), Inches(5.2), Inches(4.4), labels, vals, palette)
    grid_x = MARGIN + Inches(5.6)
    grid_w = SLIDE_W - MARGIN - grid_x
    equ = sum(p['value_czk'] for p in tracker['positions'])
    chips = [
        (ft['alloc_pos'], _px(equ, lang), INK, PAPER,
         _p(equ / tracker['nav_czk'] * 100, lang, signed=False)),
        (ft['alloc_cash'], _px(tracker['cash_czk'], lang), INK, PAPER,
         _p(100 - equ / tracker['nav_czk'] * 100, lang, signed=False)),
    ]
    ch, y = Inches(1.05), Inches(2.35)
    for label, value, vcol, fill, share in chips:
        _rect(slide, grid_x, y, grid_w, ch, fill, radius=0.06)
        tf = _tbox(slide, grid_x + Inches(0.2), y + Inches(0.14), grid_w - Inches(1.3), ch - Inches(0.24))
        _para(tf, label, size=8, color=GRAY_500, bold=True, spc=120, first=True, space_after=2)
        _para(tf, value + ' CZK', size=17, color=vcol, bold=True)
        tf2 = _tbox(slide, grid_x + grid_w - Inches(1.15), y + Inches(0.3), Inches(1.0), Inches(0.5))
        _para(tf2, share, size=15, color=GREEN_DARK, bold=True, align=PP_ALIGN.RIGHT, first=True)
        y += ch + Inches(0.2)
    # top positions by NAV share
    top = sorted(tracker['positions'], key=lambda p: -p['value_czk'])[:4]
    tf = _tbox(slide, grid_x, y + Inches(0.1), grid_w, Inches(2.2))
    _para(tf, (ft['h_value_czk']), size=8, color=GRAY_500, bold=True, spc=120, first=True, space_after=4)
    for p in top:
        _para(tf, f"{p['ticker']:<7} {p['value_czk']:,.0f} CZK".replace(',', ' '),
              size=10, color=INK, bold=True, space_after=2)
    return slide


def _slide_purchase_log(prs, idx, txt, lang, data):
    ft = _ft(lang)
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _page_chrome(slide, idx, ft['log_kicker'], ft['log_title'], ft['log_sub'], txt)
    invested = _invested_positions()
    rows = [(inv['ticker'], (inv['name'] or '')[:26], _d(inv['bought'], lang),
             _px(inv['entry_px'], lang), _px(inv['cur_px'], lang),
             _p(inv['ret_pct'], lang, signed=True)) for inv in invested]
    _pptx_table(slide, MARGIN, Inches(2.3), Inches(12.1),
                (1.0, 2.0, 1.1, 1.0, 1.0, 0.9),
                [txt['h_ticker'], txt['h_name'], ft['h_invested'], txt['h_px0'],
                 txt['h_px1'], txt['h_ret']], rows, row_h=Inches(0.4), size=9.5,
                align={2: PP_ALIGN.CENTER, 3: PP_ALIGN.RIGHT, 4: PP_ALIGN.RIGHT, 5: PP_ALIGN.RIGHT})
    return slide


def _slide_live_paths(prs, idx, txt, lang, data, tracker: Dict):
    ft = _ft(lang)
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _page_chrome(slide, idx, ft['live_paths_kicker'] if 'live_paths_kicker' in ft else ft['book_kicker'],
                 ft['live_paths_title'], ft['live_paths_sub'], txt)
    invested = {r['ticker'].split('.')[0]: r for r in _invested_positions()}
    palette = [GREEN, GREEN_DARK, GREEN_MID, NAVY, GOLD, GRAY_500, GREEN_SOFT]
    series, cats_len = [], 0
    for k, p in enumerate(tracker['positions']):
        c = _match_company(p['ticker'])
        if not c or not invested.get(p['ticker']):
            continue
        bought = invested[p['ticker']]['bought']
        rows = StockPrice.query.filter(StockPrice.company_id == c.id,
                                       StockPrice.date >= bought).order_by(StockPrice.date).all()
        # monthly snapshot
        seen, pts = {}, []
        for r in rows:
            key = (r.date.year, r.date.month)
            if key not in seen:
                seen[key] = float(r.close_price)
        if not seen:
            continue
        base = float(rows[0].close_price)
        by_month = {}
        for r in rows:
            by_month[(r.date.year, r.date.month)] = float(r.close_price)
        first_d, last_d = rows[0].date, rows[-1].date
        vals = []
        dcur = first_d
        while (dcur.year, dcur.month) <= (last_d.year, last_d.month):
            key = (dcur.year, dcur.month)
            v = by_month.get(key)
            if v and base:
                vals.append((key, (v / base - 1) * 100.0))
            if dcur.month == 12:
                dcur = dcur.replace(year=dcur.year + 1, month=1)
            else:
                dcur = dcur.replace(month=dcur.month + 1)
        series.append((p['ticker'], vals, palette[k % len(palette)]))
        cats_len = max(cats_len, len(vals))
    # build a common monthly axis across all series
    all_keys = sorted({k for _, vals, _ in series for k, _ in vals})
    cats = [f'{k[0]}/{k[1] % 100}' for k in all_keys]
    def series_vals(vals):
        lookup = dict(vals)
        return [lookup.get(k) for k in all_keys]
    _native_line(slide, MARGIN, Inches(2.3), Inches(12.1), Inches(4.2), cats, [
        (name, series_vals(vals), color) for name, vals, color in series
    ], num_fmt='0')
    return slide


def _slide_funnel2(prs, idx, txt, lang, data):
    return _slide_funnel_core(prs, idx, txt, lang, data, data['pipe'])


def _slide_funnel(prs, idx, txt, lang, data, pipe: Dict = None):
    return _slide_funnel_core(prs, idx, txt, lang, data, pipe)


def _slide_funnel_core(prs, idx, txt, lang, data, pipe: Dict):
    ft = _ft(lang)
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _page_chrome(slide, idx, ft['bin_kicker'], ft['bin_title'], ft['bin_sub'], txt)
    band_h = Inches(1.1)
    steps = [
        (pipe['all_n'], ft['funnel_h_analysed'], INK, PAPER),
        (pipe['watchlist_n'], ft['funnel_h_watch'], GREEN_DARK, GREEN_PALE),
        (pipe['purchases_n'], ft['funnel_h_bought'], GREEN_DARK, GREEN_PALE),
    ]
    w = (CONTENT_W - Inches(0.2) * 2) / 3
    x0 = MARGIN
    for k, (num, label, col, fill) in enumerate(steps):
        x = x0 + k * (w + Inches(0.2))
        _rect(slide, x, Inches(2.3), w, band_h, fill, radius=0.08)
        tf = _tbox(slide, x + Inches(0.28), Inches(2.46), w - Inches(0.5), band_h - Inches(0.3))
        _para(tf, str(num), size=30, color=col, bold=True, first=True, space_after=2)
        _para(tf, label.upper(), size=8.5, color=GRAY_500, bold=True, spc=140)
        if k < 2:
            ar = slide.shapes.add_shape(MSO_SHAPE.RIGHT_ARROW, x + w - Inches(0.08),
                                        Inches(2.79), Inches(0.36), Inches(0.2))
            ar.fill.solid()
            ar.fill.fore_color.rgb = LINE
            ar.line.fill.background()
            ar.shadow.inherit = False
    info = _tbox(slide, MARGIN, Inches(3.7), CONTENT_W, Inches(0.7))
    _para(info, '', size=8, color=GRAY_400)
    return slide


# ------------------------------------------------------------------
# Research factory slides
# ------------------------------------------------------------------

def _slide_factory_monthly(prs, idx, txt, lang, data, pipe: Dict):
    ft = _ft(lang)
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _page_chrome(slide, idx, ft['bin_kicker'], ft['per_title'], ft['per_sub'], txt)
    _native_bar(slide, MARGIN, Inches(2.3), Inches(6.2), Inches(4.0),
                pipe['keys'][-14:], [(ft['funnel_h_analysed'], pipe['total'][-14:], GRAY_500)],
                labels=False, n_fmt='0', gap_width=40)
    _native_line(slide, MARGIN + Inches(6.5), Inches(2.3), Inches(5.9), Inches(4.0),
                 pipe['keys'][-14:], [
                     (ft['funnel_h_analysed'], pipe['total'][-14:], GREEN),
                     (ft['funnel_h_watch'], pipe['approved'][-14:], GOLD),
                 ], num_fmt='0')
    return slide


def _slide_factory_year(prs, idx, txt, lang, data):
    ft = _ft(lang)
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _page_chrome(slide, idx, ft['year_kicker'], ft['year_title'], ft['year_sub'], txt)
    years, year_approved = {}, {}
    for a in Analysis.query.all():
        if not a.analysis_date:
            continue
        years[a.analysis_date.year] = years.get(a.analysis_date.year, 0) + 1
        if a.status == 'On Watchlist':
            year_approved[a.analysis_date.year] = year_approved.get(a.analysis_date.year, 0) + 1
    ks = sorted(years)
    _native_bar(slide, MARGIN, Inches(2.3), Inches(12.1), Inches(3.9), [str(k) for k in ks], [
        (ft['funnel_h_analysed'], [years[k] for k in ks], GREEN_SOFT),
        (ft['funnel_h_watch'], [year_approved.get(k) for k in ks], GREEN),
    ], labels=True, n_fmt='0', gap_width=70, y_min=0, y_max=max(years.values()) * 1.2)
    return slide


def _slide_sector_table(prs, idx, txt, lang, data, statuses, head, sub):
    ft = _ft(lang)
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _page_chrome(slide, idx, ft['sector_kicker'], head, sub, txt)
    stats = _sector_stats(statuses)
    rows = []
    fills = {}
    for k, s in enumerate(stats[:14]):
        rows.append((s['sector'][:26], str(s['analyses']),
                     _p(s['avg_return'], lang, signed=False),
                     f"{s['stddev']:.1f}".replace('.', ','),
                     _p(s['min'], lang, signed=True)))
        fills[(k, 2)] = RED_PALE if s['avg_return'] and s['avg_return'] < 0 else GREEN_PALE
    headers = [ft['h_sector'], ft['h_n'], ft['h_avg'], ft['h_std'], ft['h_min']]
    if not rows:
        rows = [('—', '0', '—', '—', '—')]
    _pptx_table(slide, MARGIN, Inches(2.3), Inches(12.1), (3.0, 0.7, 1.1, 0.9, 1.1),
                headers, rows, row_h=Inches(0.32), size=9, cell_fills=fills,
                align={1: PP_ALIGN.CENTER, 2: PP_ALIGN.RIGHT, 3: PP_ALIGN.RIGHT, 4: PP_ALIGN.RIGHT})
    return slide


def _slide_sector_compare(prs, idx, txt, lang, data):
    ft = _ft(lang)
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _page_chrome(slide, idx, ft['sector_kicker'], ft['sector_cmp_title'], ft['sector_cmp_sub'], txt)
    all_stats = {s['sector']: s for s in _sector_stats()}
    watch_stats = {s['sector']: s for s in _sector_stats(('On Watchlist',))}
    secs = [k for k in all_stats if k in watch_stats][:8]
    secs = sorted(secs, key=lambda k: -(watch_stats[k]['avg_return'] or all_stats[k]['avg_return'] or 0))
    cats = [k[:14] for k in secs]
    s_all = [all_stats[k]['avg_return'] or 0 for k in secs]
    s_watch = [watch_stats[k]['avg_return'] or 0 for k in secs]
    _native_bar(slide, MARGIN, Inches(2.3), Inches(12.1), Inches(4.2), cats, [
        (ft['sector_cmp_watch'], s_watch, GREEN),
        (ft['sector_cmp_all'], s_all, GRAY_500),
    ], labels=False, n_fmt='0.0', gap_width=60)
    return slide


def _slide_top_bottom(prs, idx, txt, lang, data, worst=False):
    ft = _ft(lang)
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    head = ft['bottom_title'] if worst else ft['top_title']
    _page_chrome(slide, idx, ft['sector_kicker'], head, ft['top_sub'], txt)
    raw = db.session.query(
        Analysis.id, Company.name, Company.ticker_symbol,
        PerformanceCalculation.return_pct, Analysis.analysis_date
    ).join(Analysis, Analysis.company_id == Company.id) \
     .join(PerformanceCalculation, PerformanceCalculation.analysis_id == Analysis.id) \
     .filter(Analysis.status == 'On Watchlist').all()
    best = {}
    for aid, name, tk, ret, adate in raw:
        if ret is None:
            continue
        if aid not in best or float(ret) > best[aid][3]:
            best[aid] = (aid, name[:24], tk or '—', float(ret), adate)
    ranked = sorted(best.values(), key=lambda r: r[3], reverse=(not worst))[:10]
    rows = [(r[2], r[1], _d(r[4], lang), _p(r[3], lang, signed=True)) for r in ranked]
    if not rows:
        rows = [('—', '—', '—', '—')]
    _pptx_table(slide, MARGIN, Inches(2.3), Inches(12.1), (1.2, 2.6, 1.3, 1.0),
                [txt['h_ticker'], txt['h_name'], (('Dat. analýzy' if lang == 'cs' else 'Analysis date')), txt['h_ret']], rows,
                row_h=Inches(0.38), size=9.5,
                align={2: PP_ALIGN.CENTER, 3: PP_ALIGN.RIGHT})
    return slide


def _slide_analysts_ft(prs, idx, txt, lang, data):
    ft = _ft(lang)
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _page_chrome(slide, idx, ft['bin_kicker'], ft['analyst_title'], ft['analyst_sub'], txt)
    at = get_analyst_summary_table()
    rows = [(r['name'], str(r['total_analyses']), str(r['approved_analyses']),
             str(r['investments']), _p(r['avg_return'], lang, signed=False)) for r in at['rows'][:9]]
    if not rows:
        rows = [('—', '—', '—', '—', '—')]
    _pptx_table(slide, MARGIN, Inches(2.3), Inches(12.1), (2.6, 1, 1, 1, 1.2),
                [ft['h_sector'][:0] + txt['h_name'], 'ANALÝZ' if lang == 'cs' else 'ANALYSES',
                 ('SCHVÁLENO' if lang == 'cs' else 'APPROVED'), ('REALIZOVÁNO' if lang == 'cs' else 'REALISED'),
                 ('PRŮM. VÝNOS' if lang == 'cs' else 'AVG RETURN')],
                rows, row_h=Inches(0.4), size=10)
    return slide


def _slide_exclusions(prs, idx, txt, lang, data):
    ft = _ft(lang)
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _page_chrome(slide, idx, txt['d2_kicker'], ft['excl_title'], '', txt)
    col_w = (CONTENT_W - Inches(0.3)) / 2
    items = [e for e in txt.get('limits', [])][:0] or ft['excl']
    top = Inches(2.4)
    for k, (head, body) in enumerate(items):
        col = k % 2
        x = MARGIN + col * (col_w + Inches(0.3))
        y = top + (k // 2) * Inches(1.32)
        _rect(slide, x, y, col_w, Inches(1.12), PAPER, radius=0.05)
        _rule(slide, x, y + Inches(0.08), Inches(0.055), color=RED, thickness=0.3)
        tf = _tbox(slide, x + Inches(0.22), y + Inches(0.16), col_w - Inches(0.44), Inches(0.9))
        _para(tf, head, size=10.5, color=RED, bold=True, first=True, space_after=3)
        _para(tf, body, size=9, color=GRAY_700, line=1.18)
    return slide
