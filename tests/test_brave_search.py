#!/usr/bin/env python3
"""Test Brave Search integration."""
import sys
sys.path.insert(0, '.')

from app.utils.brave_search import search_ticker_via_brave, extract_ticker_with_fallback

def test_brave():
    print("Testing Brave Search integration...")
    # Test with a known company
    company = "Apple"
    result = search_ticker_via_brave(company)
    print(f"Brave search for '{company}': {result}")
    
    # Test with hint
    result_with_hint = search_ticker_via_brave(company, hint="Technology")
    print(f"With hint: {result_with_hint}")
    
    # Test fallback function
    ticker = extract_ticker_with_fallback(company, hint="Technology")
    print(f"Extracted ticker: {ticker}")
    
    # Test with a company that likely has a ticker
    company2 = "Microsoft"
    ticker2 = extract_ticker_with_fallback(company2)
    print(f"Microsoft ticker: {ticker2}")
    
    # Test with a non-English or tricky company
    company3 = "BYD Company"
    ticker3 = extract_ticker_with_fallback(company3, hint="Automotive")
    print(f"BYD ticker: {ticker3}")
    
    # Edge case: empty result
    company4 = "NonexistentCompanyXYZ"
    ticker4 = extract_ticker_with_fallback(company4)
    print(f"Nonexistent company ticker: {ticker4}")

if __name__ == '__main__':
    test_brave()