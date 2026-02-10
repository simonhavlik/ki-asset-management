import yfinance as yf
import pandas as pd
from datetime import date, timedelta
import traceback
import sys

def test_ticker(ticker):
    try:
        print(f'Trying {ticker}...')
        data = yf.download(ticker, start='2024-01-01', end='2025-01-01', progress=False)
        if data.empty:
            print(f'  -> No data')
            return False
        else:
            print(f'  -> Success, shape {data.shape}')
            return True
    except Exception as e:
        print(f'  -> Exception: {e}')
        traceback.print_exc()
        return False

if __name__ == '__main__':
    tickers = ['CAVA', 'BTG', 'ANF', 'PINS', 'AAP', '0700', 'BIDI11', 'BYDDY', 'LULU', 'INPST']
    for t in tickers:
        test_ticker(t)
    # Try with exchange suffixes
    print('\n--- Trying with exchange suffixes ---')
    suffixes = {
        '0700': '0700.HK',
        'BIDI11': 'BIDI11.SA',
        'BYDDY': 'BYDDY.OTC',  # OTC? Actually BYDDY is OTC pink sheet, maybe no suffix
        'INPST': 'INPST.AS',   # InPost is listed on Euronext Amsterdam? Actually ticker is INPST.AS
        'CAVA': 'CAVA',        # already US
        'BTG': 'BTG',          # US
        'ANF': 'ANF',          # US
        'PINS': 'PINS',        # US
        'AAP': 'AAP',          # US
        'LULU': 'LULU',        # US
    }
    for t, suffixed in suffixes.items():
        if suffixed != t:
            test_ticker(suffixed)
    # Also try using yfinance.Ticker to get info
    print('\n--- Checking ticker info ---')
    for t in tickers:
        try:
            tk = yf.Ticker(t)
            info = tk.info
            if info:
                print(f'{t}: {info.get("longName", "N/A")}')
            else:
                print(f'{t}: No info')
        except Exception as e:
            print(f'{t}: Error {e}')