import logging
import requests
import json
from flask import current_app
from typing import Optional

logger = logging.getLogger(__name__)

def classify_stock(company_name: str) -> bool:
    """
    Use DeepSeek API to determine if a company is a publicly traded stock.
    Returns True if it's a stock, False otherwise.
    """
    api_key = current_app.config.get('DEEPSEEK_API_KEY')
    if not api_key:
        logger.debug("DeepSeek API key not configured, skipping classification")
        return True  # fallback: assume it's a stock
    
    prompt = f"Is '{company_name}' a singular publicly traded company (stock) that can be analyzed as an investment? Answer only YES or NO."
    response = call_deepseek(prompt)
    if response:
        return response.strip().upper() == 'YES'
    return True  # fallback

def extract_ticker(company_name: str) -> Optional[str]:
    """
    Use DeepSeek API to extract ticker symbol for a company.
    Returns ticker symbol or None.
    """
    api_key = current_app.config.get('DEEPSEEK_API_KEY')
    if not api_key:
        logger.debug("DeepSeek API key not configured, skipping ticker extraction")
        return None
    
    prompt = f"What is the stock ticker for '{company_name}'? Respond only with the ticker symbol or 'NOT_A_STOCK' if it's not a publicly traded company."
    response = call_deepseek(prompt)
    if response:
        logger.info(f"DeepSeek response for '{company_name}': {response}")
        if response.strip().upper() != 'NOT_A_STOCK':
            ticker = response.strip().upper()
            logger.info(f"DeepSeck extracted ticker {ticker} for {company_name}")
            return ticker
    logger.info(f"DeepSeek could not extract ticker for {company_name}")
    return None

def call_deepseek(prompt: str, max_tokens: int = 10) -> Optional[str]:
    """Make a request to DeepSeek chat completions API."""
    api_key = current_app.config.get('DEEPSEEK_API_KEY')
    if not api_key:
        logger.debug("No DeepSeek API key")
        return None
    
    url = "https://api.deepseek.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "max_tokens": max_tokens,
        "temperature": 0.0
    }
    
    try:
        logger.debug(f"Calling DeepSeek API with prompt: {prompt}")
        resp = requests.post(url, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        response_text = data['choices'][0]['message']['content'].strip()
        logger.debug(f"DeepSeek API response: {response_text}")
        return response_text
    except Exception as e:
        logger.error(f"DeepSeek API error: {e}")
        return None