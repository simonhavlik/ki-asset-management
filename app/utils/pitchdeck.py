"""
Pitch deck export for KI Asset Management.

Builds a presentation-ready PPTX deck from live data - the same loaders the
homepage and the presentation dashboard use - in the club's institutional
design: green #1a9c5e on white, thin hairlines, generous margins, a numbered
slide grid.

The deck is available in English and Czech (lang='en' | 'cs'). The Czech copy
is not a machine translation: wherever the club already phrases something on
the website (app/static/js/i18n.js), that exact wording is reused, and the
rest is written by hand in the same voice.

Usage:
    from app.utils.pitchdeck import build_pitch_deck
    stream, filename = build_pitch_deck('cs')
"""

import io
import math
from datetime import date
from typing import Dict, List, Optional

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm
import numpy as np

from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE
from pptx.oxml.ns import qn

from ..extensions import db
from ..models import Analysis, PerformanceCalculation, PortfolioPurchase, User, BenchmarkPrice
from .performance import get_vote_counts_for_analyses
from .presentation_export import (
    get_analyst_summary_table,
    get_sector_analysis,
    get_growth_timeline,
    generate_portfolio_chart_series,
)

import logging
logger = logging.getLogger(__name__)


def _benchmark_return(ticker: str, start_date, end_date) -> float:
    """Benchmark return over a window - same source and logic as app.main.routes."""
    try:
        start_price = (BenchmarkPrice.query.filter(BenchmarkPrice.ticker == ticker,
                                                   BenchmarkPrice.date <= start_date)
                       .order_by(BenchmarkPrice.date.desc()).first())
        end_price = (BenchmarkPrice.query.filter(BenchmarkPrice.ticker == ticker,
                                                 BenchmarkPrice.date <= end_date)
                     .order_by(BenchmarkPrice.date.desc()).first())
        if not start_price or not end_price or float(start_price.close_price) <= 0:
            return 0.0
        return round((float(end_price.close_price) / float(start_price.close_price) - 1.0) * 100.0, 2)
    except Exception as exc:  # noqa: BLE001
        logger.warning('benchmark %s failed: %s', ticker, exc)
        return 0.0


# ------------------------------------------------------------------
# Design tokens - the club's institutional palette (style.css values)
# ------------------------------------------------------------------

GREEN      = RGBColor(0x1A, 0x9C, 0x5E)
GREEN_DARK = RGBColor(0x14, 0x7A, 0x4A)
GREEN_DEEP = RGBColor(0x0B, 0x4B, 0x2E)
GREEN_GHOST = RGBColor(0x11, 0x63, 0x3D)     # ghost numerals on deep covers
GREEN_PALE = RGBColor(0xE7, 0xF3, 0xEC)
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
MINT_TEXT  = RGBColor(0xCF, 0xE8, 0xDA)      # light copy on the deep covers

SLIDE_W = Inches(13.333)
SLIDE_H = Inches(7.5)
MARGIN = Inches(0.62)
CONTENT_W = SLIDE_W - 2 * MARGIN
FONT = 'Calibri'

# matplotlib hex mirrors of the tokens
M_GREEN, M_GREEN_DARK, M_GOLD, M_NAVY = '#1a9c5e', '#147a4a', '#b8860b', '#2b6cb0'
M_INK, M_GRAY, M_LINE, M_RED = '#0f1419', '#6b7682', '#e1e5e9', '#c53030'

plt.rcParams.update({
    'font.family': 'DejaVu Sans',
    'text.color': M_INK,
    'axes.edgecolor': M_LINE,
    'axes.labelcolor': M_GRAY,
    'xtick.color': M_GRAY,
    'ytick.color': M_GRAY,
    'xtick.labelsize': 8,
    'ytick.labelsize': 8,
    'axes.grid': True,
    'grid.color': M_LINE,
    'grid.alpha': 0.55,
    'grid.linewidth': 0.5,
    'axes.spines.top': False,
    'axes.spines.right': False,
    'axes.spines.left': False,
    'figure.dpi': 200,
    'savefig.dpi': 200,
})


# ------------------------------------------------------------------
# Copy deck
# ------------------------------------------------------------------

CONTENT = {
    'en': {},
    'cs': {},
}

_EN = {
    'club': 'KI Asset Management — Prague Club of Investors',
    'wordmark': 'KI Asset Management',
    'footer_of': 'Prague Club of Investors',
    'cover_kicker': 'CLUB PRESENTATION',
    'cover_title': 'Institutional-grade research.\nStudent-run capital.',
    'cover_sub': 'Founded for one clear purpose: to bridge academic theory and real-world '
                 'investment management. Every figure in this document is computed live from '
                 'the club database - the same numbers the public website shows.',
    'cover_window': 'From the first analysis to today',
    'disclaimer': 'Student research for educational purposes only - not investment advice.',
    'accepting': 'Currently accepting analysts working in Czech only',
    'd1_kicker': 'PERFORMANCE', 'd1_title': 'Performance',
    'd1_sub': 'Returns, risk, and how the portfolio behaves against its indexes.',
    'd2_kicker': 'METHODOLOGY', 'd2_title': 'Methodology',
    'd2_sub': 'How an idea becomes a position - and the rules that keep it safe.',
    'd3_kicker': 'TEAM', 'd3_title': 'Team',
    'd3_sub': 'The people who analyse, challenge and sign off every decision.',
    'kpi_title': 'The club in numbers',
    'kpi_sub': 'Every figure is computed live from the club database.',
    'kpi_win': 'Analysis win rate',
    'kpi_meetings': 'Analytical meetings', 'kpi_members': 'Team members',
    'kpi_approved': 'Approved analyses', 'kpi_positions': 'Positions in portfolio',
    'kpi_return': 'Total return since inception',
    'kpi_funnel': 'From every meeting, only a position that survives a 20-page analysis, an '
                  'opponent review and a unanimous committee vote reaches the portfolio.',
    'perf_title': 'Performance, from day one',
    'perf_sub': 'Monthly portfolio result against its benchmarks, all series indexed to the first '
                'analysis date. Incremental equal-weight rebalancing - same methodology as the website.',
    'chip_12m': 'Trailing 12M return',
    'chip_vs_eems_12': 'vs EEMS, trailing 12M',
    'chip_vs_spy_12': 'vs S&P 500, trailing 12M',
    'chip_start': 'First analysis',
    'legend_port': 'Portfolio', 'legend_spy': 'S&P 500', 'legend_vt': 'FTSE All-World', 'legend_eems': 'EEMS',
    'chart_pct': '% since inception',
    'risk_title': 'Risk, drawdowns and patience',
    'risk_sub': 'Return is half the story. The other half is told by drawdowns - how deep they cut '
                'and how long the way back took.',
    'chip_vol': 'Annualised volatility',
    'chip_dd': 'Deepest drawdown',
    'chip_under': 'Longest underwater spell',
    'chip_worst_m': 'Worst month',
    'chart_dd': 'Portfolio drawdown from peak',
    'chart_roll': 'Rolling 12-month volatility',
    'dev_title': 'Deviation against the index',
    'dev_sub': 'Cumulative excess return over EEMS - the index the portfolio is built to beat. '
               'Computed from monthly differences, annualised.',
    'chip_ir': 'Information ratio vs EEMS',
    'chip_td': 'Annualised tracking difference',
    'chip_te': 'Tracking error, annualised',
    'chip_beta': 'Beta vs S&P 500',
    'chip_g12m': 'Best trailing 12M spread',
    'tbl_returns': 'Returns',
    'col_12m': '12M', 'col_all': 'Since inception',
    'col_port': 'Portfolio', 'col_spy': 'S&P 500', 'col_vt': 'FTSE All-World', 'col_eems': 'EEMS',
    'note_staging': 'The portfolio enters positions gradually, so average exposure in the early '
                    'months is lower than an index invested from inception.',
    'peer_title': 'Indexes with a similar strategy',
    'peer_sub': 'The closest available index to the strategy is EEMS - emerging markets, smaller '
                'and mid-sized companies. Global indexes are shown for context. Calendar-year '
                'returns; every series starts at the first analysis date.',
    'peer_note': 'All series are price returns measured from the same start date - no window picking.',
    'heat_title': 'Monthly returns',
    'heat_sub': 'Month by month since inception, heat-coloured.',
    'chip_pos_m': 'Positive months', 'chip_avg_m': 'Average month',
    'chip_best_m': 'Best month', 'chip_worst_m2': 'Worst month',
    'proc_title': 'How a position is born',
    'proc_sub': 'A multi-stage process - every decision stands on the same four steps and a '
                'unanimous vote.',
    'proc_s1': 'Screening', 'proc_s1d': 'Numbers first: ROIC, margins, growth, then the qualitative picture.',
    'proc_s2': 'The 20-page write-up', 'proc_s2d': 'Business model, competitive advantages, valuation.',
    'proc_s3': 'Opponent review', 'proc_s3d': 'A dedicated opponent challenges the thesis before the committee.',
    'proc_s4': 'Committee vote', 'proc_s4d': 'Presented to the committee; approval requires total consensus.',
    'proc_funnel': 'Approval funnel', 'proc_screened': 'analysed',
    'proc_approved': 'board-approved', 'proc_rate': 'approval rate',
    'proc_funnel_screened': 'analyses on record',
    'proc_funnel_approved': 'committee-approved',
    'proc_funnel_rate': 'approval rate',
    'chart_growth': 'Analyses over time',
    'limits_title': 'The rules that never bend',
    'limits_sub': 'Written down, ratified by the whole club, applied before the first crown moves.',
    'limits': [
        ('Position size', 'max. 10% of the portfolio per position; entry built in steps of max. 5%'),
        ('Sector / region', 'max. 20% per sector, max. 30% per region; 15-25 positions for real diversification'),
        ('Exit discipline', 'soft stop-loss at -20% triggers an independent thesis review; monthly re-checks'),
        ('Liquidity', 'position max. 5x average daily volume; preference for dual-listed securities'),
        ('Cash', 'idle balances sit in interest-bearing accounts (CZK, EUR, USD); more cash at high valuations'),
        ('Consensus', 'every decision needs absolute consensus; one opposing vote blocks the entry'),
    ],
    'alloc_title': 'What we own, and why',
    'alloc_sub': 'One deliberate mix - three engines that rarely fire in the same month.',
    'al_s1': 'SMID caps', 'al_s1d': 'Sub-$25B market caps, thin analyst coverage, structural inefficiencies.',
    'al_s2': 'Emerging markets', 'al_s2d': 'CEE, LATAM and Asia - regional insight Western investors overlook.',
    'al_s3': 'Equity stories', 'al_s3d': 'Special situations and contrarian setups with asymmetric payoff.',
    'al_pillar': 'target allocation',
    'bench_title': 'The analyst bench',
    'bench_sub': 'Research output and results per analyst, straight from the club database.',
    'bench_title2': 'Where the research paid off',
    'sect_title': 'Where the research paid off',
    'team_quote_lead': 'Leading the strategic vision and investment decisions of the club.',
    'team_quote_member': 'Building the platform the whole club runs on - research, portfolio '
                         'and capital in one database.',
    'bench_col_name': 'Analyst', 'bench_col_total': 'Analyses', 'bench_col_approved': 'Approved',
    'bench_col_inv': 'Realised', 'bench_col_ret': 'Avg return',
    'sect_col_sector': 'Sector', 'sect_col_n': 'n', 'sect_col_ret': 'Avg return', 'sect_col_sig': 'Spread',
    'team_title': 'The people behind the results',
    'team_sub': 'Analysis is one voice against another before anything is bought.',
    'team_lead_role': 'President of the investment committee',
    'team_lead_edu': 'CTU & WU Alumni',
    'team_member_role': 'Analyst & Lead Developer',
    'team_member_edu': 'VSE Economics Student',
    'close_title': 'Ready to start your journey?',
    'close_sub': 'Join the Prague Club of Investors for hands-on investment management - real '
                 'capital, real accountability.',
    'close_kicker': 'CONTACT',
    'site': 'ki.havliksimon.eu',
}

_CS = {
    'club': 'KI Asset Management — Pražský klub investorů',
    'wordmark': 'KI Asset Management',
    'footer_of': 'Pražský klub investorů',
    'cover_kicker': 'PREZENTACE KLUBU',
    # reuse - the club's own site wording (i18n.js)
    'cover_title': 'Kvalitní analýzy.\nStudentský přístup.',
    'cover_sub': 'Vznikli jsme s jasným cílem: propojit akademickou teorii s reálným investováním. '
                 'Všechna čísla v tomto dokumentu se čtou rovnou z databáze klubu – jsou to ta '
                 'samá čísla, která vidí veřejná verze webu.',
    'cover_window': 'Od první analýzy do dneška',
    'disclaimer': 'Studentský výzkum pouze pro vzdělávací účely — není investiční doporučení.',   # reuse
    'accepting': 'Přijímáme analytiky, kteří pracují v češtině',                                  # reuse
    'd1_kicker': 'VÝKONNOST', 'd1_title': 'Výkonnost',
    'd1_sub': 'Výnosy, rizika a chování portfolia vůči indexům, s nimiž se měří.',
    'd2_kicker': 'METODIKA', 'd2_title': 'Metodika',
    'd2_sub': 'Jak se z nápadu stane pozice – a pravidla, která ji po celou dobu chrání.',
    'd3_kicker': 'TÝM', 'd3_title': 'Tým',
    'd3_sub': 'Lidé, kteří analyzují, kritizují a za každé rozhodnutí ručí.',
    'kpi_title': 'Klub v číslech',
    'kpi_sub': 'Všechny údaje se počítají živě z databáze klubu.',
    'kpi_win': 'Úspěšnost analýz',                                   # reuse
    'kpi_meetings': 'Analytických setkání',                          # reuse
    'kpi_members': 'Členů týmu',                                     # reuse
    'kpi_approved': 'Schválených analýz',                            # reuse
    'kpi_positions': 'Akcií v portfoliu',                            # reuse
    'kpi_return': 'Celkový výnos od začátku',                        # reuse
    'kpi_funnel': 'Ze setkání se do portfolia dostane jen taková pozice, která projde analýzou '
                  'na 20 stran, oponentským posouzením a hlasováním výboru, kde musí panovat '
                  'naprostá shoda.',
    'perf_title': 'Výkonnost od založení',
    'perf_sub': 'Měsíční výsledky portfolia a indexů, přepočtené k datu první analýzy (index 100). '
                'Metodika: inkrementální rovnovážená simulace – tatáž, kterou používá web klubu.',
    'chip_12m': 'Posledních 12 měsíců',
    'chip_vs_eems_12': 'vs EEMS za 12 měsíců',
    'chip_vs_spy_12': 'vs S&P 500 za 12 měsíců',
    'chip_start': 'První analýza',
    'legend_port': 'Portfolio', 'legend_spy': 'S&P 500', 'legend_vt': 'FTSE All-World', 'legend_eems': 'EEMS',
    'chart_pct': '% od založení',
    'risk_title': 'Riziko, propady a trpělivost',
    'risk_sub': 'Výnos je jen polovina příběhu. Druhou polovinu vyprávějí propady – jak hluboko '
                'sahají a jak dlouho trvá, než se portfolio dostane zpět na své maximum.',
    'chip_vol': 'Roční volatilita',
    'chip_dd': 'Nejhlubší propad',
    'chip_under': 'Nejdelší doba pod hladinou',
    'chip_worst_m': 'Nejhorší měsíc',
    'chart_dd': 'Propad portfolia od maxima',
    'chart_roll': 'Rolující 12měsíční volatilita',
    'dev_title': 'Jak daleko od indexu',
    'dev_sub': 'Kumulativní nadvýnos vůči EEMS – indexu, který je strategie klubu nejbližší. '
               'Počítáno z měsíčních rozdílů, přepočteno na roční bázi.',
    'chip_ir': 'Information ratio vůči EEMS',
    'chip_td': 'Roční odchylka vůči EEMS',
    'chip_te': 'Chyba sledování (roční)',
    'chip_beta': 'Citlivost na trh (beta)',          # reuse i18n "market sensitivity"
    'chip_g12m': 'Nejlepší 12M rozdíl',
    'tbl_returns': 'Výnosy',
    'col_12m': '12M', 'col_all': 'Od založení',
    'col_port': 'Portfolio', 'col_spy': 'S&P 500', 'col_vt': 'FTSE All-World', 'col_eems': 'EEMS',
    'note_staging': 'Portfolio do pozic vstupuje postupně, takže v prvních měsících je průměrná '
                    'expozice nižší než u indexu investovaného od začátku.',
    'peer_title': 'Indexy s podobnou strategií',
    'peer_sub': 'Strategicky nejbližší dostupný index je EEMS – rozvíjející se trhy a menší či '
                'střední akcie. Globální indexy uvádíme pro kontext. Výnosy po kalendářních '
                'letech; každá řada začíná datem první analýzy klubu.',
    'peer_note': 'Všechny řady jsou cenové výnosy od téhož data – žádná okna nebyla vybírána.',
    'heat_title': 'Měsíc po měsíci',
    'heat_sub': 'Měsíční výnosy portfolia za celou historii, barevně.',
    'chip_pos_m': 'Kladných měsíců', 'chip_avg_m': 'Průměrný měsíc',
    'chip_best_m': 'Nejlepší měsíc', 'chip_worst_m2': 'Nejhorší měsíc',
    'proc_title': 'Jak se rodí pozice',
    'proc_sub': 'Důsledný vícekrokový proces – každé rozhodnutí stojí na čtyřech stejných krocích '
                'a hlasování celého výboru.',
    'proc_s1': 'Úvodní výběr',
    'proc_s1d': 'Čísla na začátek: ROIC, marže, růst, poté kvalitativní obraz.',
    'proc_s2': 'Analýza na 20 stran',
    'proc_s2d': 'Byznys model, konkurenční výhody a ocenění.',                 # reuse
    'proc_s3': 'Oponentské posouzení',                                          # reuse
    'proc_s3d': 'Vyčleněný oponent rozebírá práci ještě před výborem.',
    'proc_s4': 'Hlasování výboru',                                              # reuse
    'proc_s4d': 'Prezentace výboru; ke schválení je potřeba naprostá shoda.',   # reuse
    'proc_funnel': 'Schvalovací trychtýř', 'proc_screened': 'analyzováno',
    'proc_approved': 'schváleno výborem', 'proc_rate': 'míra schválení',
    'proc_funnel_screened': 'celkem analýz',
    'proc_funnel_approved': 'schváleno výborem',
    'proc_funnel_rate': 'míra schválení',
    'chart_growth': 'Analýzy v čase',
    'limits_title': 'Pevná pravidla',
    'limits_sub': 'Napíšeno, odsouhlaseno celým klubem a platí dřív, než se pohneme s první korunou.',
    'limits': [
        ('Velikost pozice', 'max. 10 % portfolia na jednu pozici; vstup budujeme postupně po max. 5 %'),
        ('Sektor / region', 'max. 20 % na sektor, max. 30 % na region; 15–25 pozic pro skutečnou diverzifikaci'),
        ('Disciplína výstupu', 'měkký stop-loss −20 % spouští nezávislé přezkoumání teze; pozice kontrolujeme každý měsíc'),
        ('Likvidita', 'pozice max. 5× průměrného denního objemu; preferujeme dvojitě kótované tituly'),
        ('Hotovost', 'volné prostředky držíme na úročených účtech (CZK, EUR, USD); při vysokých oceněních více hotovosti'),
        ('Shoda', 'každé rozhodnutí vyžaduje naprostou shodu; jediný nesouhlasný hlas vstup zablokuje'),
    ],
    'alloc_title': 'Do čeho investujeme',                    # reuse
    'alloc_sub': 'Jeden promyšlený mix – tři motory, které ve stejný měsíc zakopnou zřídka.',
    'al_s1': 'Menší a střední firmy',                        # reuse
    'al_s1d': 'Tržní kapitalizace do 25 mld. USD. Pokrytí analytiky je slabé, na hedgeové fondy '
              'malé; strukturální neefektivity vytvářejí příležitosti pro pečlivé analytiky.',
    'al_s2': 'Rozvíjející se trhy',                          # reuse
    'al_s2d': 'Střední a východní Evropa, Latinská Amerika a Asie – lokální vhled, který západní investoři přehlédnou.',  # reuse
    'al_s3': 'Příběhy jednotlivých akcií',                   # reuse
    'al_s3d': 'Speciální situace, tématické investice a kontrární příležitosti – trh je přehlíží, tím vzniká zajímavý poměr rizika a výnosu.',
    'al_pillar': 'cílové rozložení',
    'bench_title': 'Analytická lavice',
    'bench_sub': 'Objem práce a výsledky jednotlivých analytiků, rovnou z databáze klubu.',
    'bench_title2': 'Kde se výzkum vyplatil',
    'sect_title': 'Kde se výzkum vyplatil',
    'team_quote_lead': 'Vedu strategickou vizi a investiční rozhodnutí klubu. Cílem je dát studentům '
                       'zkušenost se správou reálného kapitálu a současně dosahovat nadprůměrných '
                       'výnosů při odpovídajícím riziku.',
    'team_quote_member': 'Vyvíjím systém, na kterém celý klub běží – výzkum, portfolio a kapitál '
                         'jsou v jedné databáze.',
    'bench_col_name': 'Analytik', 'bench_col_total': 'Analýz', 'bench_col_approved': 'Schváleno',
    'bench_col_inv': 'Realizováno', 'bench_col_ret': 'Prům. výnos',
    'sect_col_sector': 'Sektor', 'sect_col_n': 'n', 'sect_col_ret': 'Prům. výnos', 'sect_col_sig': 'Rozptyl',
    'team_title': 'Lidé za výsledky',
    'team_sub': 'Každý návrh je jeden hlas proti jinému – dřív, než se cokoliv nakoupí.',
    'team_lead_role': 'Předseda investičního výboru',        # reuse
    'team_lead_edu': 'Absolvent ČVUT a WU',                  # reuse
    'team_member_role': 'Analytik a hlavní vývojář',         # reuse
    'team_member_edu': 'Student ekonomie na VŠE',            # reuse
    'close_title': 'Chcete začít investovat?',               # reuse
    'close_sub': 'Přidejte se k nám a získejte praktické zkušenosti s řízením investičního '
                 'portfolia. Pracujte s reálnými penězi, učte se od profesionálů a budujte '
                 'svou pověst.',                                            # reuse
    'close_kicker': 'KONTAKT',
    'site': 'ki.havliksimon.eu',
}

CONTENT['en'] = {k: v for k, v in _EN.items()}
CONTENT['cs'] = {k: v for k, v in _CS.items()}


def _content(lang: str) -> dict:
    return CONTENT.get(lang, CONTENT['en'])


# ------------------------------------------------------------------
# Data layer
# ------------------------------------------------------------------

def _board_approved():
    """Board-approved analyses - same rule the homepage uses (yes votes > no votes)."""
    analyses = Analysis.query.filter_by(status='On Watchlist').all()
    ids = [a.id for a in analyses]
    counts = get_vote_counts_for_analyses(ids)
    approved = [a for a in analyses
                if counts.get(a.id, {'yes': 0, 'no': 0})['yes'] >
                counts.get(a.id, {'yes': 0, 'no': 0})['no']]
    return sorted(approved, key=lambda a: a.analysis_date)


def _metrics_from_series(dates, port_pct, spy_pct, vt_pct, eems_pct):
    """Risk/return metrics off the monthly cumulative series (values in % since inception)."""
    port = np.array(port_pct, dtype=float)
    if len(port) < 3:
        return {}
    p = port / 100.0
    eq = 1.0 + p
    dd = eq / np.maximum.accumulate(eq) - 1.0
    max_dd = float(dd.min())

    spell, current = 0, 0
    for v in dd:
        current = current + 1 if v < -1e-12 else 0
        spell = max(spell, current)

    monthly = np.diff(p)
    n_months = monthly.size
    years_span = n_months / 12.0
    total = float(p[-1])
    cagr = (1.0 + total) ** (1.0 / years_span) - 1.0 if total > -1 else total / years_span
    ann_vol = float(monthly.std(ddof=1) * math.sqrt(12.0))
    sharpe = float((cagr - 0.03) / ann_vol) if ann_vol > 0 else None

    def dm(x):
        return np.diff(np.array(x, dtype=float) / 100.0)

    def period_return(x, n=13):
        """True trailing return over n-1 months, compounded in wealth space."""
        arr = 1.0 + np.array(x, dtype=float) / 100.0
        return float(arr[-1] / arr[-n] - 1.0) * 100.0 if arr.size >= n else None

    em = dm(eems_pct)
    sm = dm(spy_pct)
    pm = monthly
    n_excess = min(pm.size, em.size)
    excess = pm[-n_excess:] - em[-n_excess:]
    td_ann = float(excess.mean() * 12.0)
    te_ann = float(excess.std(ddof=1) * math.sqrt(12.0))
    info_ratio = float(td_ann / te_ann) if te_ann > 1e-9 else None

    n_beta = min(pm.size, sm.size)
    beta = float(np.cov(pm[-n_beta:], sm[-n_beta:])[0, 1] / np.var(sm[-n_beta:])) if n_beta > 3 else None

    tr_port, tr_eems, tr_spy = period_return(port_pct), period_return(eems_pct), period_return(spy_pct)
    spread_12m = (tr_port - tr_eems) if tr_port is not None and tr_eems is not None else None
    spread_spy_12m = (tr_port - tr_spy) if tr_port is not None and tr_spy is not None else None

    return {
        'total_return': total * 100.0,
        'cagr': cagr * 100.0,
        'ann_vol': ann_vol * 100.0,
        'sharpe': sharpe,
        'max_dd': max_dd * 100.0,
        'underwater_months': spell,
        'monthly_avg': float(monthly.mean() * 100.0),
        'monthly_best': float(monthly.max() * 100.0),
        'monthly_worst': float(monthly.min() * 100.0),
        'positive_months': float((monthly > 0).mean() * 100.0),
        'trailing_12m': tr_port,
        'vs_eems_12m': spread_12m,
        'vs_spy_12m': spread_spy_12m,
        'tracking_diff': td_ann * 100.0,
        'tracking_err': te_ann * 100.0,
        'info_ratio': info_ratio,
        'beta': beta,
        'dd_series': dd * 100.0,
        'monthly_series': monthly * 100.0,
    }


def _collect(window_years: Optional[int] = None) -> dict:
    """Load what the deck needs; reuses the same loaders/cache as the site."""
    import pandas as pd

    from ..extensions import db
    from sqlalchemy import func

    approved = _board_approved()
    analysis_ids = [a.id for a in approved]
    series_data = generate_portfolio_chart_series(analysis_ids, years=window_years, method='incremental')
    dates = pd.to_datetime(series_data['dates'])
    start_date = approved[0].analysis_date if approved else date.today()

    spy, vt, eems = [], [], []
    for d in dates:
        cur = d.date()
        spy.append(_benchmark_return('SPY', start_date, cur))
        vt.append(_benchmark_return('VT', start_date, cur))
        eems.append(_benchmark_return('EEMS', start_date, cur))

    # position-level accuracy - same definition the homepage shows
    rets = []
    for aid in analysis_ids:
        perf = (PerformanceCalculation.query.filter_by(analysis_id=aid)
                .order_by(PerformanceCalculation.calculation_date.desc()).first())
        if perf and perf.return_pct is not None:
            rets.append(float(perf.return_pct))
    win_rate = (sum(1 for r in rets if r > 0) / len(rets) * 100.0) if rets else None

    # headline counters - mirrors the public homepage exactly (app.main.routes)
    meetings = db.session.query(func.count(func.distinct(Analysis.analysis_date))).scalar() or 0
    members = User.query.count()
    approved_total = Analysis.query.filter_by(status='On Watchlist').count()

    return {
        'approved': approved,
        'analysed_total': Analysis.query.count(),
        'meetings': meetings,
        'members': members,
        'approved_total': approved_total,
        'positions_count': len(approved),
        'dates': dates,
        'start_date': start_date,
        'series': {'port': series_data['values'], 'spy': spy, 'vt': vt, 'eems': eems},
        'metrics': _metrics_from_series(series_data['dates'], series_data['values'], spy, vt, eems),
        'win_rate': win_rate,
        'analyst_table': get_analyst_summary_table(),
        'sectors': get_sector_analysis(use_cache=True),
        'growth': get_growth_timeline(use_cache=False),
    }


# ------------------------------------------------------------------
# Charts
# ------------------------------------------------------------------

def _finish(fig) -> io.BytesIO:
    buf = io.BytesIO()
    fig.savefig(buf, format='png', facecolor=fig.get_facecolor(), edgecolor='none')
    plt.close(fig)
    buf.seek(0)
    return buf


def _style_axis(ax):
    ax.grid(axis='y', alpha=0.55)
    ax.grid(axis='x', visible=False)
    ax.tick_params(length=0)
    for lbl in ax.get_xticklabels() + ax.get_yticklabels():
        lbl.set_color(M_GRAY)


def _chart_cumulative(data, txt) -> io.BytesIO:
    """Main draw: portfolio vs the three benchmarks, end-labelled without collisions."""
    s = data['series']
    dates = list(data['dates'])
    fig, ax = plt.subplots(figsize=(7.9, 4.3))
    lines = [
        (dates, s['eems'], M_GRAY, 1.2, txt['legend_eems'], False),
        (dates, s['vt'], M_NAVY, 1.2, txt['legend_vt'], False),
        (dates, s['spy'], M_GOLD, 1.2, txt['legend_spy'], False),
        (dates, s['port'], M_GREEN, 2.9, txt['legend_port'], True),
    ]
    # resolve vertical collisions of the end labels, then place them
    ends = sorted(lines, key=lambda t: t[1][-1])
    gap = (max(v[-1] for _, v, *_ in ends) - min(v[-1] for _, v, *_ in ends)) / (len(ends) + 1.5)
    ys = []
    last = None
    for _, vals, *_ in ends:
        y = vals[-1]
        if last is not None and y - last < gap:
            y = last + gap
        ys.append(y)
        last = y
    label_y = dict(zip([id(t) for t in ends], ys))
    for t in lines:
        xd, yd, color, lw, label, bold = t
        ax.plot(xd, yd, color=color, lw=lw, solid_capstyle='round')
        ax.annotate(f"{label}  {yd[-1]:+.1f}%",
                    xy=(xd[-1], label_y[id(t)]), xytext=(6, 0), textcoords='offset points',
                    va='center', fontsize=8, color=color,
                    fontweight='bold' if bold else 'normal')
    ax.axhline(0, color=M_LINE, lw=0.7)
    ax.set_xlim(dates[0], dates[-1] + (dates[-1] - dates[0]) * 0.16)
    ax.set_ylabel(txt['chart_pct'], fontsize=8, color=M_GRAY)
    ax.margins(x=0.0)
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %y'))
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=max(2, len(dates) // 14)))
    _style_axis(ax)
    ax.set_facecolor('white')
    fig.tight_layout(pad=0.6)
    return _finish(fig)


def _chart_drawdown(data) -> io.BytesIO:
    dates, dd = list(data['dates']), data['metrics']['dd_series']
    fig, ax = plt.subplots(figsize=(3.7, 2.35))
    ax.fill_between(dates, dd, 0, color=M_GREEN_DARK, alpha=0.14)
    ax.plot(dates, dd, color=M_GREEN_DARK, lw=1.4)
    i_min = int(np.argmin(dd))
    ax.annotate(f"{dd[i_min]:.1f}%", xy=(dates[i_min], dd[i_min]),
                xytext=(0, 9), textcoords='offset points', ha='center',
                fontsize=8, color=M_GREEN_DARK, fontweight='bold')
    ax.set_ylim(min(dd[1:], default=-0.25) * 1.45, 0.002)
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %y'))
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=max(3, len(dates) // 8)))
    _style_axis(ax)
    fig.tight_layout(pad=0.4)
    return _finish(fig)


def _chart_rolling_vol(data, txt) -> io.BytesIO:
    """Rolling 12M volatility of the portfolio and of EEMS."""
    port = np.array(data['series']['port'], dtype=float)
    eems = np.array(data['series']['eems'], dtype=float)
    if port.size < 14:
        fig, ax = plt.subplots(figsize=(3.7, 2.35))
        ax.text(0.5, 0.5, '—', ha='center', va='center', color=M_GRAY)
        ax.axis('off')
        return _finish(fig)
    dates = list(data['dates'])
    def rollvol(x):
        d = np.diff(x) / 100.0
        out = np.full(d.size, np.nan)
        for i in range(11, d.size):
            out[i] = d[i - 11:i + 1].std(ddof=1) * math.sqrt(12) * 100
        return out
    rv_p, rv_e = rollvol(port), rollvol(eems)
    fig, ax = plt.subplots(figsize=(3.7, 2.35))
    ax.plot(dates[1:], rv_p, color=M_GREEN, lw=1.8, label=txt['legend_port'])
    ax.plot(dates[1:], rv_e, color=M_GRAY, lw=1.1, label=txt['legend_eems'])
    valid = [d for d, v in zip(dates[1:], rv_p) if not np.isnan(v)]
    if valid:
        ax.set_xlim(valid[0], valid[-1])
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %y'))
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=max(3, len(dates) // 8)))
    _style_axis(ax)
    ax.legend(frameon=False, fontsize=7, loc='upper left', ncol=2, handlelength=1.4)
    fig.tight_layout(pad=0.4)
    return _finish(fig)


def _chart_spread(data) -> io.BytesIO:
    """Cumulative portfolio return minus cumulative EEMS return."""
    port = np.array(data['series']['port'], dtype=float)
    eems = np.array(data['series']['eems'], dtype=float)
    spread = port - eems
    dates = list(data['dates'])
    fig, ax = plt.subplots(figsize=(7.9, 3.5))
    ax.fill_between(dates, spread, 0, where=spread >= 0, color=M_GREEN, alpha=0.16, interpolate=True)
    ax.fill_between(dates, spread, 0, where=spread < 0, color=M_RED, alpha=0.12, interpolate=True)
    ax.plot(dates, spread, color=M_GREEN_DARK, lw=2.2)
    ax.axhline(0, color=M_GRAY, lw=0.8)
    ax.annotate(f"{spread[-1]:+.1f} p.p.", xy=(dates[-1], spread[-1]), xytext=(6, 0),
                textcoords='offset points', va='center', fontsize=9,
                color=M_GREEN_DARK, fontweight='bold')
    ax.set_xlim(dates[0], dates[-1] + (dates[-1] - dates[0]) * 0.14)
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %y'))
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=max(2, len(dates) // 14)))
    _style_axis(ax)
    fig.tight_layout(pad=0.6)
    return _finish(fig)


def _chart_yearly_bars(data, txt) -> io.BytesIO:
    """Calendar-year returns, portfolio vs the three indexes."""
    def yearly(x, dates):
        arr, out = {}, {}
        for d, v in zip(dates, x):
            arr.setdefault(d.year, []).append(v)
        for y, vals in arr.items():
            out[y] = vals[-1] - vals[0]
        return out
    dates = list(data['dates'])
    ys = {lbl: yearly(vals, dates) for lbl, vals in (
        (txt['legend_port'], data['series']['port']),
        (txt['legend_eems'], data['series']['eems']),
        (txt['legend_spy'], data['series']['spy']),
        (txt['legend_vt'], data['series']['vt']))}
    years = sorted(set().union(*[set(y) for y in ys.values()]))
    peak = max([(v or 0) for y in ys.values() for v in y.values()] + [0])
    fig, ax = plt.subplots(figsize=(7.9, 3.2))
    ax.set_ylim(min(-25, peak * -0.25), max(20, peak * 1.15))
    width = 0.2
    colors = [M_GREEN, M_GRAY, M_GOLD, M_NAVY]
    for k, (lbl, y) in enumerate(ys.items()):
        offs = (k - 1.5) * width
        vals = [y.get(yy) for yy in years]
        xs = np.arange(len(years)) + offs
        bars = ax.bar(xs, [v or 0 for v in vals], width=width * 0.88, color=colors[k], label=lbl,
                      alpha=1.0 if k == 0 else 0.85)
        for x_, v, b in zip(xs, vals, bars):
            if v is not None:
                txt_color = '#ffffff' if k == 0 else M_GRAY
                ax.annotate(f"{v:+.0f}", xy=(x_, min(b.get_height(), ax.get_ylim()[1]) * 0.985),
                            xytext=(0, -2), textcoords='offset points',
                            ha='center', va='top', fontsize=6.8, color=txt_color)
    ax.set_xticks(range(len(years)))
    ax.set_xticklabels([str(y) for y in years])
    ax.axhline(0, color=M_GRAY, lw=0.8)
    ax.legend(frameon=False, fontsize=7.5, loc='upper left', ncol=4, handlelength=1.2)
    _style_axis(ax)
    fig.tight_layout(pad=0.5)
    return _finish(fig)


def _chart_heatmap(data) -> io.BytesIO:
    monthly, dates = np.array(data['metrics']['monthly_series']), list(data['dates'])
    # monthly[i] is the change from dates[i] to dates[i+1]; bucket by the month being earned
    months_earned = [d.month for d in dates[1:]]
    years_earned = [d.year for d in dates[1:]]
    years = sorted(set(years_earned))
    grid = np.full((12, len(years)), np.nan)
    for mo, yr, val in zip(months_earned, years_earned, monthly):
        grid[mo - 1, years.index(yr)] = val
    fig, ax = plt.subplots(figsize=(7.9, 3.1))
    cmap = LinearSegmentedColormap.from_list('kiam', ['#c53030', '#f5f7f9', '#1a9c5e'])
    vmax = np.nanmax(np.abs(grid)) or 1
    norm = TwoSlopeNorm(vmin=-vmax, vcenter=0, vmax=vmax)
    masked = np.ma.masked_invalid(grid)
    cmap.set_bad('#f5f7f9')
    im = ax.imshow(masked, cmap=cmap, norm=norm, aspect='auto')
    for i in range(12):
        for j in range(len(years)):
            v = grid[i, j]
            if not np.isnan(v):
                ax.text(j, i, f"{v:+.1f}", ha='center', va='center', fontsize=7,
                        color='white' if abs(v) > vmax * 0.55 else M_INK)
    ax.set_xticks(range(len(years)))
    ax.set_xticklabels([str(y) for y in years], fontsize=8)
    mn = ['led', 'úno', 'bře', 'dub', 'kvě', 'čen', 'čvc', 'srp', 'zář', 'říj', 'lis', 'pro']
    ax.set_yticks(range(12))
    ax.set_yticklabels(mn, fontsize=7.5)
    ax.grid(False)
    ax.tick_params(length=0)
    for sp in ax.spines.values():
        sp.set_visible(False)
    fig.tight_layout(pad=0.5)
    return _finish(fig)


def _chart_allocation() -> io.BytesIO:
    fig, ax = plt.subplots(figsize=(3.4, 3.2))
    vals = (60, 30, 10)
    cols = (M_GREEN, M_GREEN_DARK, M_GOLD)
    wedges, _ = ax.pie(vals, colors=cols, startangle=90, counterclock=False,
                       wedgeprops=dict(width=0.34, edgecolor='white', linewidth=2))
    for w, v in zip(wedges, vals):
        ang = (w.theta1 + w.theta2) / 2
        x, y = math.cos(math.radians(ang)) * 0.83, math.sin(math.radians(ang)) * 0.83
        ax.text(x, y, f"{v}%", ha='center', va='center', fontsize=11.5,
                fontweight='bold', color='white' if v >= 30 else M_GOLD)
    ax.text(0, 0.06, '60/30/10', ha='center', va='center', fontsize=13, fontweight='bold', color=M_INK)
    ax.text(0, -0.13, 'SMID · EM · Stories', ha='center', va='center', fontsize=7.5, color=M_GRAY)
    ax.set(aspect='equal')
    ax.axis('off')
    fig.tight_layout(pad=0.2)
    return _finish(fig)


def _chart_growth(data, txt) -> io.BytesIO:
    g = data['growth']
    dts = g['dates']
    fig, ax = plt.subplots(figsize=(4.0, 2.5))
    if not dts:
        ax.text(0.5, 0.5, '—', ha='center', va='center', color=M_GRAY, fontsize=16)
        ax.axis('off')
        fig.tight_layout(pad=0.2)
        return _finish(fig)
    if isinstance(dts[0], str):
        dts = [datetime.strptime(d, '%Y-%m-%d').date() for d in dts]
    ax.plot(dts, g['total_analyses'], color=M_GREEN, lw=2.2, solid_capstyle='round')
    ax.plot(dts, g['approved_analyses'], color=M_GREEN_DARK, lw=1.7, ls=(0, (4, 2)))
    ax.fill_between(dts, g['total_analyses'], color=M_GREEN, alpha=0.08)
    ax.annotate(f"{g['total_analyses'][-1]}", xy=(dts[-1], g['total_analyses'][-1]),
                xytext=(5, 0), textcoords='offset points', fontsize=9, color=M_GREEN,
                fontweight='bold', va='center')
    ax.annotate(f"{g['approved_analyses'][-1]}", xy=(dts[-1], g['approved_analyses'][-1]),
                xytext=(5, 0), textcoords='offset points', fontsize=9, color=M_GREEN_DARK,
                fontweight='bold', va='center')
    ax.set_xlim(dts[0], dts[-1] + (dts[-1] - dts[0]) * 0.12)
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %y'))
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=max(3, len(dts) // 6)))
    _style_axis(ax)
    fig.tight_layout(pad=0.4)
    return _finish(fig)


# ------------------------------------------------------------------
# Slide primitives
# ------------------------------------------------------------------

def _tbox(slide, l, t, w, h, anchor=MSO_ANCHOR.TOP) -> object:
    box = slide.shapes.add_textbox(l, t, w, h)
    tf = box.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    return tf


def _para(tf, text='', size=10, color=INK, bold=False, italic=False, align=PP_ALIGN.LEFT,
          space_after=0, space_before=0, line=1.0, first=False, spc=None, font=FONT):
    p = tf.paragraphs[0] if (first and not tf.paragraphs[0].runs and not tf.paragraphs[0].text) \
        else tf.add_paragraph()
    p.alignment = align
    p.space_before = Pt(space_before)
    p.space_after = Pt(space_after)
    p.line_spacing = line
    for i, chunk in enumerate(str(text).split('\n')):
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
            r.font._rPr.set('spc', str(spc))
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
    """Standard content-slide chrome: kicker, title, subtitle, hairlines, footer."""
    top = Inches(0.55)
    tf = _tbox(slide, MARGIN, top, CONTENT_W, Inches(0.3))
    _para(tf, f"{kicker}", size=10, color=GREEN_DARK, bold=True, spc=200, first=True)
    _rule(slide, MARGIN, top + Inches(0.30), Inches(0.42), color=GREEN, thickness=0.028)
    tf = _tbox(slide, MARGIN, top + Inches(0.42), CONTENT_W, Inches(0.42))
    _para(tf, title, size=23, color=INK, bold=True, first=True)
    if subtitle:
        tf = _tbox(slide, MARGIN, top + Inches(0.92), CONTENT_W * 0.92, Inches(0.55))
        _para(tf, subtitle, size=10.5, color=GRAY_500, line=1.18, first=True)
    # footer
    _rule(slide, MARGIN, SLIDE_H - Inches(0.5), CONTENT_W, color=LINE_SOFT)
    tf = _tbox(slide, MARGIN, SLIDE_H - Inches(0.42), Inches(6.4), Inches(0.25))
    _para(tf, txt['club'], size=7.5, color=GRAY_400, first=True)
    tf = _tbox(slide, SLIDE_W - MARGIN - Inches(1.2), SLIDE_H - Inches(0.42), Inches(1.2), Inches(0.25))
    _para(tf, f"{idx:02d}", size=7.5, color=GRAY_400, bold=True, align=PP_ALIGN.RIGHT, first=True)
    _badge(slide, SLIDE_W - MARGIN - Inches(1.55), SLIDE_H - Inches(0.44), Inches(0.28), Inches(0.17),
           GREEN_PALE, 'KI', size=6, radius=0.35)


def _kpi_card(slide, l, t, w, h, label, value, note=None, accent=GREEN, value_color=INK,
              fill=PAPER, value_size=21):
    _rect(slide, l, t, w, h, fill, radius=0.06)
    tf = _tbox(slide, l + Inches(0.14), t + Inches(0.12), w - Inches(0.28), h - Inches(0.2))
    _para(tf, label, size=7.5, color=GRAY_500, bold=True, spc=120, first=True, space_after=3)
    _para(tf, value, size=value_size, color=value_color, bold=True, line=0.95)
    if note:
        _para(tf, note, size=7.5, color=GRAY_400, line=1.05, space_before=2)


def _table(slide, l, t, w, col_widths, headers, rows, row_h=Inches(0.3), header_h=Inches(0.3),
           font_size=9, align_map=None):
    n_rows, n_cols = len(rows) + 1, len(headers)
    gf = slide.shapes.add_table(n_rows, n_cols, l, t, w, header_h + row_h * len(rows))
    tbl = gf.table
    tbl.first_row = False
    tbl.horz_banding = False
    total = sum(col_widths)
    for i, cw in enumerate(col_widths):
        tbl.columns[i].width = Emu(int(w * cw / total))
    tbl.rows[0].height = header_h
    for j, htext in enumerate(headers):
        cell = tbl.cell(0, j)
        cell.fill.solid()
        cell.fill.fore_color.rgb = WHITE
        cell.vertical_anchor = MSO_ANCHOR.MIDDLE
        cell.margin_left = cell.margin_right = Inches(0.08)
        cell.margin_top = cell.margin_bottom = Inches(0.02)
        _para(cell.text_frame, htext.upper(), size=7.5, color=GRAY_500, bold=True, spc=100,
              first=True, align=PP_ALIGN.LEFT if j == 0 else PP_ALIGN.RIGHT)
        _cell_border(cell, edge='bottom', color=GREEN, width_pt=1.4)
    for r_i, row in enumerate(rows, start=1):
        tbl.rows[r_i].height = row_h
        for c_i, val in enumerate(row):
            cell = tbl.cell(r_i, c_i)
            cell.fill.solid()
            cell.fill.fore_color.rgb = WHITE if r_i % 2 else PAPER
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            cell.margin_left = cell.margin_right = Inches(0.08)
            cell.margin_top = cell.margin_bottom = Inches(0.02)
            al = (align_map or {}).get(c_i, PP_ALIGN.LEFT if c_i == 0 else PP_ALIGN.RIGHT)
            _para(cell.text_frame, str(val), size=font_size, color=INK, first=True, align=al,
                  bold=(c_i == 0))
            _cell_border(cell, edge='bottom', color=LINE_SOFT, width_pt=0.75)
    return tbl


_TCPR_LINE_ORDER = ['a:lnL', 'a:lnR', 'a:lnT', 'a:lnB', 'a:lnTlToBr', 'a:lnBlToTr']


def _cell_border(cell, edge='bottom', color=LINE, width_pt=0.75):
    """Set one border edge of a table cell (python-pptx has no API for it)."""
    order = _TCPR_LINE_ORDER
    tag_map = {'left': 'a:lnL', 'right': 'a:lnR', 'top': 'a:lnT', 'bottom': 'a:lnB'}
    tag = tag_map[edge]
    tcPr = cell._tc.get_or_add_tcPr()
    ln = tcPr.find(qn(tag))
    if ln is None:
        ln = tcPr.makeelement(qn(tag), {})
        pos = order.index(tag)
        insert_at = len(tcPr)
        for i, child in enumerate(list(tcPr)):
            child_name = child.tag.split('}')[-1]
            prefixed = f'a:{child_name}'
            if prefixed in order and order.index(prefixed) > pos:
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


# ------------------------------------------------------------------
# Slides
# ------------------------------------------------------------------

def _fmt(v, lang, signed=False, pct=True):
    """Number formatting: Czech uses a decimal comma."""
    if v is None:
        return '—'
    s = f"{v:+.1f}" if signed else f"{v:.1f}"
    s = s.rstrip('.0').rstrip('.') if s.endswith('.0') else s
    if lang == 'cs':
        s = s.replace('.', ',')
    return f"{s} %".replace('%', '') + '%' if pct else s


def _pct(v, lang, signed=True):
    if v is None:
        return '—'
    s = f"{v:+.1f}" if signed else f"{v:.1f}"
    if s.endswith('.0'):
        s = s[:-2]
    return (s.replace('.', ',') + ' %') if lang == 'cs' else (s + '%')


def _date_gap(d0, d1=date.today()):
    return f"{d0.day:02d}. {d0.month:02d}. {d0.year} – {d1.day:02d}. {d1.month:02d}. {d1.year}"


def _slide_cover(prs, txt, lang, data):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _rect(slide, 0, 0, SLIDE_W, SLIDE_H, GREEN_DEEP)
    # quiet texture: thin vertical hairline rail on the left
    _rule(slide, MARGIN, Inches(0.62), Inches(0.9), color=GREEN_GHOST, thickness=0.014)
    tf = _tbox(slide, MARGIN, Inches(0.5), Inches(6), Inches(0.3))
    _para(tf, txt['wordmark'].upper(), size=11, color=WHITE, bold=True, spc=280, first=True)
    tf = _tbox(slide, MARGIN, Inches(2.35), Inches(10.4), Inches(2.6))
    _para(tf, txt['cover_title'], size=40, color=WHITE, bold=True, line=1.04, first=True)
    tf = _tbox(slide, MARGIN, Inches(4.45), Inches(7.6), Inches(0.9))
    _para(tf, txt['cover_sub'], size=12, color=MINT_TEXT, line=1.3, first=True)
    # bottom meta band
    _rule(slide, MARGIN, SLIDE_H - Inches(1.06), CONTENT_W, color=GREEN_GHOST, thickness=0.012)
    tf = _tbox(slide, MARGIN, SLIDE_H - Inches(0.86), Inches(7), Inches(0.5))
    _para(tf, txt['cover_kicker'], size=9, color=MINT_TEXT, bold=True, spc=220, first=True, space_after=2)
    _para(tf, f"{txt['cover_window']}: {_date_gap(data['start_date'])}", size=9.5, color=WHITE, bold=True)
    m = data['metrics']
    pnl = _pct(m.get('total_return') if m else None, lang)
    tf = _tbox(slide, SLIDE_W - MARGIN - Inches(4.2), SLIDE_H - Inches(0.86), Inches(4.2), Inches(0.5))
    _para(tf, txt['kpi_return'].upper(), size=8, color=MINT_TEXT, bold=True, spc=160,
          align=PP_ALIGN.RIGHT, first=True, space_after=2)
    _para(tf, pnl, size=17, color=WHITE, bold=True, align=PP_ALIGN.RIGHT)
    return slide


def _slide_divider(prs, num, kicker, title, sub):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _rect(slide, 0, 0, SLIDE_W, SLIDE_H, GREEN_DEEP)
    tf = _tbox(slide, SLIDE_W - Inches(4.6), Inches(0.6), Inches(4.0), Inches(4.2))
    _para(tf, num, size=190, color=GREEN_GHOST, bold=True, align=PP_ALIGN.RIGHT, first=True, line=0.85)
    _rule(slide, MARGIN, Inches(3.06), Inches(0.42), color=WHITE, thickness=0.032)
    tf = _tbox(slide, MARGIN, Inches(3.3), Inches(7.6), Inches(0.3))
    _para(tf, kicker, size=10, color=MINT_TEXT, bold=True, spc=240, first=True)
    tf = _tbox(slide, MARGIN, Inches(3.62), Inches(8.6), Inches(0.75))
    _para(tf, title, size=34, color=WHITE, bold=True, first=True)
    tf = _tbox(slide, MARGIN, Inches(4.5), Inches(6.8), Inches(0.8))
    _para(tf, sub, size=11, color=MINT_TEXT, line=1.25, first=True)
    return slide


def _slide_kpis(prs, idx, txt, lang, data):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _page_chrome(slide, idx, f"01 · {txt['club']}", txt['kpi_title'], txt['kpi_sub'], txt)
    m = data['metrics']
    top, h = Inches(2.15), Inches(1.42)
    w = (CONTENT_W - Inches(0.25) * 5) / 6
    cards = [
        (txt['kpi_meetings'], str(data['meetings']), None),
        (txt['kpi_members'], str(data['members']), None),
        (txt['kpi_approved'], str(data['approved_total']), None),
        (txt['kpi_positions'], str(data['positions_count']), None),
        (txt['kpi_return'], _pct(m.get('total_return'), lang, signed=False), GREEN_DARK),
        (txt['kpi_win'], _pct(data['win_rate'], lang, signed=False), GREEN_DARK),
    ]
    x = MARGIN
    for label, value, vcol in cards:
        _kpi_card(slide, x, top, w, h, label, value, value_color=vcol or INK)
        x += w + Inches(0.25)
    # the funnel sentence as a quiet band under the cards
    band_top = top + h + Inches(0.3)
    _rect(slide, MARGIN, band_top, CONTENT_W, Inches(0.66), GREEN_PALE, radius=0.12)
    tf = _tbox(slide, MARGIN + Inches(0.24), band_top + Inches(0.1), CONTENT_W - Inches(0.48), Inches(0.46))
    _para(tf, txt['kpi_funnel'], size=9.5, color=GREEN_DARK, line=1.2, first=True)
    # research output per year (deltas, not cumulative)
    g = data['growth']
    per_year = {}
    for d, t in zip(g['dates'], g['total_analyses']):
        per_year[getattr(d, 'year', None)] = t
    years = sorted({k for k in per_year if k})
    deltas = []
    prev = 0
    for y in years:
        deltas.append((y, per_year[y] - prev))
        prev = per_year[y]
    foot_top = band_top + Inches(1.06)
    tf = _tbox(slide, MARGIN, foot_top, CONTENT_W, Inches(0.3))
    _para(tf, txt['chart_growth'], size=8, color=GRAY_500, bold=True, spc=140, first=True)
    col_w = CONTENT_W / max(len(years), 1)
    x = MARGIN
    for y, delta in deltas:
        tf = _tbox(slide, x, foot_top + Inches(0.26), col_w, Inches(0.5))
        _para(tf, str(delta), size=16, color=INK, bold=True, first=True, space_after=1)
        _para(tf, str(y), size=7.5, color=GRAY_400, bold=True, spc=100)
        x += col_w
    return slide


def _slide_performance(prs, idx, txt, lang, data):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _page_chrome(slide, idx, f"01 · {txt['d1_kicker']}", txt['perf_title'], txt['perf_sub'], txt)
    m = data['metrics']
    img = _chart_cumulative(data, txt)
    top = Inches(2.3)
    photo = slide.shapes.add_picture(img, MARGIN, top, width=Inches(8.0))
    photo.top = Emu(int(top + (Inches(4.55) - photo.height) / 2))
    rail_x = MARGIN + Inches(8.25)
    rail_w = CONTENT_W - Inches(8.25)
    chips = [
        (txt['chip_12m'], _pct(m.get('trailing_12m'), lang), (m.get('trailing_12m') or 0) >= 0, False),
        (txt['chip_vs_eems_12'], _pct(m.get('vs_eems_12m'), lang), (m.get('vs_eems_12m') or 0) >= 0, False),
        (txt['chip_vs_spy_12'], _pct(m.get('vs_spy_12m'), lang), (m.get('vs_spy_12m') or 0) >= 0, False),
        (txt['chip_start'], _date_gap(data['start_date']), True, True),
    ]
    ch = Inches(0.98)
    y = top + Inches(0.1)
    for label, value, good, small in chips:
        _kpi_card(slide, rail_x, y, rail_w, ch, label, value,
                  value_color=(GREEN_DARK if good else RED) if not small else INK,
                  fill=(GREEN_PALE if good else PAPER) if not small else PAPER,
                  value_size=11 if small else 15)
        y += ch + Inches(0.14)
    return slide


def _slide_risk(prs, idx, txt, lang, data):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _page_chrome(slide, idx, f"01 · {txt['d1_kicker']}", txt['risk_title'], txt['risk_sub'], txt)
    m = data['metrics']
    img_dd = _chart_drawdown(data)
    img_rv = _chart_rolling_vol(data, txt)
    top = Inches(2.35)
    slide.shapes.add_picture(img_dd, MARGIN, top, width=Inches(3.55))
    slide.shapes.add_picture(img_rv, MARGIN + Inches(3.75), top, width=Inches(3.55))
    rail_x = MARGIN + Inches(7.55)
    rail_w = SLIDE_W - MARGIN - rail_x
    ch = Inches(0.95)
    y = top + Inches(0.05)
    chips = [
        (txt['chip_vol'], _pct(m.get('ann_vol'), lang, signed=False)),
        (txt['chip_dd'], _pct(m.get('max_dd'), lang)),
        (txt['chip_under'], (f"{m.get('underwater_months','-')} " + ('měsíců' if lang == 'cs' else 'months')) if m else '—'),
        (txt['chip_worst_m'], _pct(m.get('monthly_worst'), lang)),
    ]
    for label, value in chips:
        _kpi_card(slide, rail_x, y, rail_w, ch, label, value,
                  value_color=RED if (label in (txt['chip_dd'], txt['chip_worst_m'])) else INK)
        y += ch + Inches(0.16)
    return slide


def _slide_deviation(prs, idx, txt, lang, data):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _page_chrome(slide, idx, f"01 · {txt['d1_kicker']}", txt['dev_title'], txt['dev_sub'], txt)
    m = data['metrics']
    img = _chart_spread(data)
    top = Inches(2.28)
    pic = slide.shapes.add_picture(img, MARGIN, top, width=Inches(8.0))
    if pic.height > Inches(3.62):
        slide.shapes[-1].height = Inches(3.62)
    rail_x = MARGIN + Inches(8.25)
    rail_w = CONTENT_W - Inches(8.25)
    ch, y = Inches(0.82), top + Inches(0.1)
    for label, value in (
        (txt['chip_ir'], f"{m.get('info_ratio'):.2f}" if m.get('info_ratio') is not None else '—'),
        (txt['chip_td'], _pct(m.get('tracking_diff'), lang)),
        (txt['chip_te'], _pct(m.get('tracking_err'), lang, signed=False)),
        (txt['chip_beta'], f"{m.get('beta'):.2f}" if m.get('beta') is not None else '—'),
    ):
        _kpi_card(slide, rail_x, y, rail_w, ch, label, value, value_size=14)
        y += ch + Inches(0.12)
    # honest returns table
    s = data['series']
    dates = list(data['dates'])
    def ret_window(xs, n):
        arr = np.array(xs, dtype=float)
        return float(arr[-1] - arr[-n]) if arr.size >= n else None
    rows = []
    for label, xs in ((txt['col_port'], s['port']), (txt['col_spy'], s['spy']),
                      (txt['col_vt'], s['vt']), (txt['col_eems'], s['eems'])):
        rows.append((label, _pct(ret_window(xs, 13), lang, signed=False),
                     _pct(float(xs[-1]), lang, signed=False)))
    _table(slide, rail_x, y + Inches(0.05), rail_w,
           (1.5, 0.9, 0.9), [txt['tbl_returns'], txt['col_12m'], txt['col_all']], rows,
           row_h=Inches(0.27), font_size=8)
    return slide


def _slide_peers(prs, idx, txt, lang, data):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _page_chrome(slide, idx, f"01 · {txt['d1_kicker']}", txt['peer_title'], txt['peer_sub'], txt)
    img = _chart_yearly_bars(data, txt)
    top = Inches(2.5)
    slide.shapes.add_picture(img, MARGIN, top, width=Inches(8.55))
    rail_x = MARGIN + Inches(8.85)
    rail_w = SLIDE_W - MARGIN - rail_x
    tf = _tbox(slide, rail_x, top + Inches(0.2), rail_w, Inches(2.6))
    _para(tf, txt['legend_eems'] + ' — ' + (txt['al_s2'] if lang == 'cs' else 'Emerging markets, SMID'),
          size=9, color=GREEN_DARK, bold=True, first=True, space_after=4)
    _para(tf, txt['note_staging'], size=8.5, color=GRAY_400, line=1.2, space_after=10)
    m = data['metrics']
    _para(tf, txt['peer_note'], size=8.5, color=GRAY_400, line=1.2, space_after=10)
    chip_rows = [
        (txt['chip_12m'], _pct(m.get('trailing_12m'), lang)),
        (txt['kpi_return'], _pct(m.get('total_return'), lang, signed=False)),
    ]
    y = Inches(5.3)
    for label, value in chip_rows:
        _kpi_card(slide, rail_x, y, rail_w, Inches(0.8), label, value, value_size=15)
        y += Inches(0.95)
    return slide


def _slide_heatmap(prs, idx, txt, lang, data):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _page_chrome(slide, idx, f"01 · {txt['d1_kicker']}", txt['heat_title'], txt['heat_sub'], txt)
    m = data['metrics']
    img = _chart_heatmap(data)
    top = Inches(2.6)
    slide.shapes.add_picture(img, MARGIN, top, width=Inches(8.55))
    rail_x = MARGIN + Inches(8.85)
    rail_w = SLIDE_W - MARGIN - rail_x
    y = top + Inches(0.02)
    ch = Inches(0.86)
    for label, value, vcol in (
        (txt['chip_pos_m'], _pct(m.get('positive_months'), lang, signed=False), GREEN_DARK),
        (txt['chip_avg_m'], _pct(m.get('monthly_avg'), lang), INK),
        (txt['chip_best_m'], _pct(m.get('monthly_best'), lang), GREEN_DARK),
        (txt['chip_worst_m2'], _pct(m.get('monthly_worst'), lang), RED),
    ):
        _kpi_card(slide, rail_x, y, rail_w, ch, label, value, value_color=vcol, value_size=15,
                  fill=GREEN_PALE if vcol == GREEN_DARK else PAPER)
        y += ch + Inches(0.11)
    return slide


def _slide_process(prs, idx, txt, lang, data):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _page_chrome(slide, idx, f"02 · {txt['d2_kicker']}", txt['proc_title'], txt['proc_sub'], txt)
    # funnel band
    top = Inches(2.2)
    band_h = Inches(1.06)
    _rect(slide, MARGIN, top, CONTENT_W, band_h, PAPER, radius=0.08)
    n_all = data['analysed_total']
    n_ok = data['approved_total']
    rate = round(100.0 * n_ok / n_all) if n_all else 0
    funnel = [(n_all, txt['proc_funnel_screened'], INK),
              (n_ok, txt['proc_funnel_approved'], GREEN_DARK),
              (rate, txt['proc_funnel_rate'], GREEN_DARK)]
    seg_w = CONTENT_W / 3
    x = MARGIN
    for k, (num, label, col) in enumerate(funnel):
        tf = _tbox(slide, x + Inches(0.26), top + Inches(0.16), seg_w - Inches(0.5), Inches(0.8),
                   anchor=MSO_ANCHOR.MIDDLE)
        _para(tf, str(num) + (' %' if k == 2 else ''), size=26, color=col, bold=True, first=True, space_after=2)
        _para(tf, label.upper(), size=8, color=GRAY_500, bold=True, spc=140)
        if k < 2:
            ar = slide.shapes.add_shape(MSO_SHAPE.RIGHT_ARROW, x + seg_w - Inches(0.12), top + Inches(0.44),
                                        Inches(0.24), Inches(0.16))
            ar.fill.solid()
            ar.fill.fore_color.rgb = LINE
            ar.line.fill.background()
            ar.shadow.inherit = False
        x += seg_w
    # four steps
    step_top = top + band_h + Inches(0.32)
    step_w = (CONTENT_W - Inches(0.22) * 3) / 4
    x = MARGIN
    for k, (st, sd) in enumerate((
        (txt['proc_s1'], txt['proc_s1d']), (txt['proc_s2'], txt['proc_s2d']),
        (txt['proc_s3'], txt['proc_s3d']), (txt['proc_s4'], txt['proc_s4d']),
    )):
        _rect(slide, x, step_top, step_w, Inches(2.25), WHITE, radius=0.05)
        num_bg = _badge(slide, x + Inches(0.14), step_top + Inches(0.16), Inches(0.42), Inches(0.42),
                        GREEN_PALE, str(k + 1), size=13, radius=0.5)
        tf = _tbox(slide, x + Inches(0.16), step_top + Inches(0.72), step_w - Inches(0.32), Inches(1.4))
        _para(tf, st, size=11.5, color=INK, bold=True, first=True, space_after=3, line=1.0)
        _para(tf, sd, size=8.5, color=GRAY_500, line=1.18)
        # step connector hairline
        if k < 3:
            _rule(slide, x + step_w, step_top + Inches(1.1), Inches(0.22), color=LINE, thickness=0.012)
        x += step_w + Inches(0.22)
    # growth chart bottom left
    img = _chart_growth(data, txt)
    gy = step_top + Inches(2.5)
    slide.shapes.add_picture(img, MARGIN, gy, height=Inches(1.7))
    if gy + Inches(1.7) > SLIDE_H - Inches(0.75):
        return slide
    return slide


def _slide_limits(prs, idx, txt, lang, data):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _page_chrome(slide, idx, f"02 · {txt['d2_kicker']}", txt['limits_title'], txt['limits_sub'], txt)
    col_w = (CONTENT_W - Inches(0.3)) / 2
    rows = txt['limits']
    top = Inches(2.3)
    for k, (head, body) in enumerate(rows):
        col = k % 2
        x = MARGIN + col * (col_w + Inches(0.3))
        y = top + (k // 2) * Inches(1.42)
        h = Inches(1.24)
        _rect(slide, x, y, col_w, h, PAPER if k % 2 == 0 else WHITE, radius=0.05)
        _rule(slide, x, y + Inches(0.08), Inches(0.055) + Inches(0.0), color=GREEN, thickness=0.36)
        tf = _tbox(slide, x + Inches(0.22), y + Inches(0.15), col_w - Inches(0.44), h - Inches(0.3))
        _para(tf, head, size=10.5, color=GREEN_DARK, bold=True, first=True, space_after=3)
        _para(tf, body, size=9, color=GRAY_700, line=1.18)
    return slide


def _slide_allocation(prs, idx, txt, lang, data):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _page_chrome(slide, idx, f"02 · {txt['d2_kicker']}", txt['alloc_title'], txt['alloc_sub'], txt)
    img = _chart_allocation()
    top = Inches(2.45)
    pic = slide.shapes.add_picture(img, MARGIN, top, height=Inches(3.55))
    rail_x = MARGIN + Inches(3.7)
    rail_w = SLIDE_W - MARGIN - rail_x
    pillars = [(txt['al_s1'], '60', txt['al_s1d']), (txt['al_s2'], '30', txt['al_s2d']),
               (txt['al_s3'], '10', txt['al_s3d'])]
    y = top
    for name, wh, body in pillars:
        h = Inches(1.32)
        _rect(slide, rail_x, y, rail_w, h, PAPER, radius=0.06)
        tf = _tbox(slide, rail_x + Inches(0.2), y + Inches(0.16), rail_w - Inches(1.15), h - Inches(0.3))
        _para(tf, name, size=11, color=INK, bold=True, first=True, space_after=3)
        _para(tf, body, size=8.5, color=GRAY_500, line=1.18)
        tf2 = _tbox(slide, rail_x + rail_w - Inches(1.05), y + Inches(0.16), Inches(0.9), h - Inches(0.3))
        _para(tf2, wh + '%', size=19, color=GREEN_DARK, bold=True, align=PP_ALIGN.RIGHT, first=True)
        _para(tf2, txt['al_pillar'], size=6.5, color=GRAY_400, bold=True, spc=90, align=PP_ALIGN.RIGHT)
        y += h + Inches(0.2)
    return slide


def _slide_bench(prs, idx, txt, lang, data):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _page_chrome(slide, idx, f"02 · {txt['d2_kicker']}", txt['bench_title'], txt['bench_sub'], txt)
    top, half_w = Inches(2.4), (CONTENT_W - Inches(0.5)) / 2
    tf = _tbox(slide, MARGIN, top - Inches(0.06), half_w, Inches(0.3))
    _para(tf, txt['bench_title2'], size=9, color=GRAY_500, bold=True, spc=140, first=True)
    at = data['analyst_table']
    rows = [(r['name'], str(r['total_analyses']), str(r['approved_analyses']),
             str(r['investments']), _pct(r['avg_return'], lang, signed=False)) for r in at['rows'][:8]]
    if not rows:
        rows = [('—', '—', '—', '—', '—')]
    _table(slide, MARGIN, top + Inches(0.22), half_w, (2.4, 1, 1, 1, 1),
           [txt['bench_col_name'], txt['bench_col_total'], txt['bench_col_approved'],
            txt['bench_col_inv'], txt['bench_col_ret']], rows, row_h=Inches(0.32), font_size=9)
    sec_x = MARGIN + half_w + Inches(0.5)
    rows2 = []
    for r in data['sectors'].get('best_sectors', {}).get('rows', [])[:8]:
        rows2.append((r['sector'], str(r['count']), _pct(r['avg_return'], lang, signed=False), _pct(r['stddev'], lang, signed=False)))
    if not rows2:
        rows2 = [('—', '—', '—', '—')]
    tf = _tbox(slide, sec_x, top - Inches(0.06), half_w, Inches(0.3))
    _para(tf, txt['sect_title'], size=9, color=GRAY_500, bold=True, spc=140, first=True)
    _table(slide, sec_x, top + Inches(0.22), half_w, (2.4, 0.7, 1, 1),
           [txt['sect_col_sector'], txt['sect_col_n'], txt['sect_col_ret'], txt['sect_col_sig']],
           rows2, row_h=Inches(0.32), font_size=9)
    return slide


def _slide_team(prs, idx, txt, lang, data):
    import os
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _page_chrome(slide, idx, f"03 · {txt['d3_kicker']}", txt['team_title'], txt['team_sub'], txt)
    static_root = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static')
    people = [
        ('images/team-leader.jpg', 'Adam Kolomazník', txt['team_lead_role'], txt['team_lead_edu']),
        ('images/team-member.jpg', 'Šimon Havlík', txt['team_member_role'], txt['team_member_edu']),
    ]
    top, card_w = Inches(2.35), (CONTENT_W - Inches(0.42)) / 2
    x = MARGIN
    for img_path, name, role, edu in people:
        h = Inches(4.3)
        _rect(slide, x, top, card_w, h, WHITE, radius=0.03)
        photo = None
        full = os.path.join(static_root, img_path)
        if os.path.exists(full):
            photo = slide.shapes.add_picture(full, x, top, width=card_w)
            crop_box = Inches(2.45 * card_w / Inches(1.0)) if False else None
            # keep the face: crop the portrait to a 4:3 window anchored on the face
            w0, h0 = photo.image.size
            target_ratio = 4.0 / 2.6
            full_ratio = w0 / h0
            if full_ratio > target_ratio:
                cut = w0 - h0 * target_ratio
                photo.crop_left = (cut / 2) / w0
                photo.crop_right = (cut / 2) / w0
                if name == 'Adam Kolomazník':
                    pass
            else:
                cut = h0 - w0 / target_ratio
                photo.crop_top = (0.04 * h0) / h0 + (cut / w0) * 0 if False else (cut * 0.2) / h0
                photo.crop_bottom = (cut * 0.8) / h0
            photo.height = Inches(2.45)
        tf = _tbox(slide, x + Inches(0.3), top + Inches(2.72), card_w - Inches(0.6), h - Inches(2.9))
        _para(tf, name, size=15, color=INK, bold=True, first=True, space_after=2)
        _para(tf, role, size=9.5, color=GREEN_DARK, bold=True, spc=60, space_after=2)
        _para(tf, edu, size=9, color=GRAY_500, space_after=8)
        _para(tf, txt['team_quote_lead'] if role == txt['team_lead_role'] else txt['team_quote_member'],
              size=8.5, color=GRAY_400, italic=False, line=1.2)
        x += card_w + Inches(0.42)
    return slide


def _slide_closing(prs, idx, txt, lang, data):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _rect(slide, 0, 0, SLIDE_W, SLIDE_H, GREEN_DEEP)
    _rule(slide, MARGIN, Inches(0.9), Inches(0.42), color=WHITE, thickness=0.032)
    tf = _tbox(slide, MARGIN, Inches(1.16), Inches(8), Inches(0.3))
    _para(tf, txt['close_kicker'], size=10, color=MINT_TEXT, bold=True, spc=240, first=True)
    tf = _tbox(slide, MARGIN, Inches(2.15), Inches(10.6), Inches(1.1))
    _para(tf, txt['close_title'], size=32, color=WHITE, bold=True, first=True)
    tf = _tbox(slide, MARGIN, Inches(3.15), Inches(8.4), Inches(0.9))
    _para(tf, txt['close_sub'], size=12, color=MINT_TEXT, line=1.3, first=True)
    # contact band
    hold_x = MARGIN
    y = SLIDE_H - Inches(2.35)
    _rect(slide, hold_x, y, Inches(4.6), Inches(1.3), GREEN_GHOST, radius=0.06)
    tf = _tbox(slide, hold_x + Inches(0.28), y + Inches(0.2), Inches(4.1), Inches(0.95))
    _para(tf, txt['site'], size=15, color=WHITE, bold=True, first=True, space_after=4)
    _para(tf, txt['accepting'], size=9, color=MINT_TEXT, line=1.15)
    # disclaimer rail
    tf = _tbox(slide, MARGIN + Inches(5.1), y + Inches(0.32), CONTENT_W - Inches(5.1), Inches(0.72))
    _para(tf, txt['disclaimer'], size=8.5, color=MINT_TEXT, line=1.25, first=True)
    _para(tf, txt['club'], size=8.5, color=WHITE, bold=True, space_before=6)
    # quiet page mark
    tf = _tbox(slide, SLIDE_W - MARGIN - Inches(1.0), SLIDE_H - Inches(0.5), Inches(1.0), Inches(0.3))
    _para(tf, f"{idx:02d}", size=8, color=MINT_TEXT, bold=True, align=PP_ALIGN.RIGHT, first=True)
    return slide


# ------------------------------------------------------------------
# Entrance
# ------------------------------------------------------------------

def build_pitch_deck(lang: str = 'cs', window_years: Optional[int] = None) -> tuple:
    """Render the deck; returns (BytesIO, filename)."""
    txt = _content(lang)
    data = _collect(window_years)
    m = data.get('metrics') or {}

    prs = Presentation()
    prs.slide_width, prs.slide_height = SLIDE_W, SLIDE_H

    counter = {'n': 0}

    def numbered(builder, *args, **kw):
        counter['n'] += 1
        return builder(*args, idx=counter['n'], **kw)

    _slide_cover(prs, txt, lang, data)                                          # 1
    _slide_divider(prs, '01', txt['d1_kicker'], txt['d1_title'], txt['d1_sub'])  # 2
    _slide_kpis(prs, 3, txt, lang, data)
    _slide_performance(prs, 4, txt, lang, data)
    _slide_risk(prs, 5, txt, lang, data)
    _slide_deviation(prs, 6, txt, lang, data)
    _slide_peers(prs, 7, txt, lang, data)
    _slide_heatmap(prs, 8, txt, lang, data)
    _slide_divider(prs, '02', txt['d2_kicker'], txt['d2_title'], txt['d2_sub'])  # 9
    _slide_process(prs, 10, txt, lang, data)
    _slide_limits(prs, 11, txt, lang, data)
    _slide_allocation(prs, 12, txt, lang, data)
    _slide_bench(prs, 13, txt, lang, data)
    _slide_divider(prs, '03', txt['d3_kicker'], txt['d3_title'], txt['d3_sub'])  # 14
    _slide_team(prs, 15, txt, lang, data)
    _slide_closing(prs, 16, txt, lang, data)

    stream = io.BytesIO()
    prs.save(stream)
    stream.seek(0)
    stamp = date.today().isoformat()
    filename = f"KI_AM_pitch_deck_{lang}_{stamp}.pptx"
    return stream, filename
