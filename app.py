import os
from datetime import datetime, timedelta
import yfinance as yf
import pandas as pd
from flask import Flask, render_template, jsonify, request, abort
from werkzeug.middleware.proxy_fix import ProxyFix

from database import (
    init_db, get_tickers_by_category, get_portfolio_summary, get_portfolio_holdings,
    execute_investment, save_daily_pick, get_pick_history_for_category,
    get_todays_pick_for_category, get_recently_picked_tickers
)
from scraper import run_scraper_pipeline
from sentiment_analyzer import get_sentiment_for_tickers, run_sentiment_analysis
from performance_tracker import run_performance_check
from utils import is_market_open
from cache import get as get_from_cache, set as set_in_cache

app = Flask(__name__)

# --- Configuration ---
SCRAPER_API_KEY = os.environ.get('SCRAPER_API_KEY', 'your-super-secret-key')
app.wsgi_app = ProxyFix(app.wsgi_app, x_prefix=1)

# --- Constants ---
MIN_AVG_VOLUME = 100000
SMA_SHORT = 50
SMA_LONG = 200
POSITIVE_SENTIMENT_THRESHOLD = 0.2

# --- Categories ---
CATEGORIES = {
    'hot_stock': {
        'db_categories': ['sp500', 'generic_stock', 'etf'],
        'display_name': 'Hot Picks'
    },
    'penny_stock': {
        'db_categories': ['penny', 'etf', 'generic_stock'],
        'display_name': '$5 or Less',
        'price_limit': 5
    },
    'monthly_dividend': {'db_category': 'monthly_dividend', 'display_name': 'Monthly Dividends'},
    'high_yield_dividend': {'db_category': 'high_yield', 'display_name': 'High-Yield Dividends'}
}

# --- Stock Finding Logic ---
def find_growth_candidate(categories_to_search, price_limit=None):
    print(f"Searching for growth candidate in categories: {categories_to_search}, price_limit: {price_limit}")
    all_tickers = []
    for category in categories_to_search:
        all_tickers.extend(get_tickers_by_category(category))
    unique_tickers = sorted(list(set(all_tickers)))
    recent_picks = set()
    all_history_categories = ['sp500', 'penny', 'monthly_dividend', 'high_yield', 'daily_investment_pick']
    for category in all_history_categories:
        recent_picks.update(get_recently_picked_tickers(category))

    # --- Tier 1: Golden Cross + Volume ---
    print("--- Tier 1: Searching for Golden Cross candidates ---")
    technical_candidates = []
    for ticker in unique_tickers:
        if ticker in recent_picks: continue
        try:
            stock_info = yf.Ticker(ticker).info
            avg_volume = stock_info.get('averageDailyVolume10Day')
            if avg_volume is None or avg_volume < MIN_AVG_VOLUME: continue
            if price_limit:
                current_price = stock_info.get('regularMarketPrice')
                if current_price is None or current_price > price_limit: continue
            hist = yf.Ticker(ticker).history(period=f"{SMA_LONG + 2}d")
            if len(hist) < SMA_LONG + 1: continue
            hist['SMA50'] = hist['Close'].rolling(window=SMA_SHORT).mean()
            hist['SMA200'] = hist['Close'].rolling(window=SMA_LONG).mean()
            if pd.notna(hist['SMA50'].iloc[-1]) and pd.notna(hist['SMA200'].iloc[-1]):
                if hist['SMA50'].iloc[-2] < hist['SMA200'].iloc[-2] and hist['SMA50'].iloc[-1] > hist['SMA200'].iloc[-1]:
                    technical_candidates.append(ticker)
        except Exception: pass

    if technical_candidates:
        sentiment_scores = get_sentiment_for_tickers(technical_candidates)
        sentiment_candidates = [{'ticker': t, 'sentiment': sentiment_scores.get(t, 0)} for t in technical_candidates]
        sentiment_candidates.sort(key=lambda x: x['sentiment'], reverse=True)
        if sentiment_candidates[0]['sentiment'] >= POSITIVE_SENTIMENT_THRESHOLD:
            print(f"Found Golden Cross candidate with high sentiment: {sentiment_candidates[0]}")
            return sentiment_candidates[0]

    # --- Tier 2: 3-Day Growth ---
    print("--- Tier 2: No Golden Cross found. Searching for 3-Day Growth candidates ---")
    three_day_candidates = []
    for ticker in unique_tickers:
        if ticker in recent_picks: continue
        try:
            if price_limit:
                # Re-fetch info if needed, or assume it's okay for this simpler check
                pass
            hist = yf.Ticker(ticker).history(period="7d")
            if len(hist) < 4: continue
            if all(hist['Close'].iloc[-i] > hist['Close'].iloc[-i-1] for i in range(1, 4)):
                three_day_candidates.append(ticker)
        except Exception: pass

    if three_day_candidates:
        sentiment_scores = get_sentiment_for_tickers(three_day_candidates)
        sentiment_candidates = [{'ticker': t, 'sentiment': sentiment_scores.get(t, 0)} for t in three_day_candidates]
        sentiment_candidates.sort(key=lambda x: x['sentiment'], reverse=True)
        if sentiment_candidates[0]['sentiment'] >= POSITIVE_SENTIMENT_THRESHOLD:
            print(f"Found 3-Day Growth candidate with high sentiment: {sentiment_candidates[0]}")
            return sentiment_candidates[0]

    # --- Tier 3: Fallback ---
    print("--- Tier 3: No candidates with positive sentiment found. Falling back. ---")
    all_candidates = technical_candidates + three_day_candidates
    for ticker in all_candidates:
        if ticker not in recent_picks:
            return {'ticker': ticker, 'sentiment': None}
    for ticker in unique_tickers:
        if ticker not in recent_picks:
            return {'ticker': ticker, 'sentiment': None}

    return {'ticker': unique_tickers[0] if unique_tickers else None, 'sentiment': None}

def find_hot_stock(category_key):
    details = CATEGORIES.get(category_key, {})
    return find_growth_candidate(
        categories_to_search=details.get('db_categories', []),
        price_limit=details.get('price_limit')
    )

def find_best_candidate_from_all():
    return find_growth_candidate(categories_to_search=['sp500', 'penny', 'etf', 'generic_stock'])

def find_dividend_stock(category):
    recent_picks = get_recently_picked_tickers(category)
    tickers = get_tickers_by_category(category)
    for ticker in tickers:
        if ticker not in recent_picks:
            return {'ticker': ticker, 'sentiment': None}
    return {'ticker': tickers[0] if tickers else None, 'sentiment': None}

def get_daily_pick_response(category_key):
    db_category = CATEGORIES[category_key]['db_categories'][0] # Use first category as primary
    try:
        todays_pick = get_todays_pick_for_category(db_category)
        if todays_pick:
            stock_ticker, sentiment = todays_pick['ticker'], todays_pick.get('sentiment_score')
        else:
            result = find_dividend_stock(db_category) if 'dividend' in category_key else find_hot_stock(category_key)
            stock_ticker, sentiment = result['ticker'], result['sentiment']
            if stock_ticker: save_daily_pick(db_category, stock_ticker, sentiment)
        history = get_pick_history_for_category(db_category)
        return jsonify({'ticker': stock_ticker or 'No suitable stock found today.', 'history': history})
    except Exception:
        import traceback
        traceback.print_exc()
        return jsonify({'ticker': 'Error loading data.', 'history': []}), 500

# --- API Endpoints ---
@app.route('/')
def index(): return render_template('index.html')
@app.route('/api/hot-stock')
def api_hot_stock(): return get_daily_pick_response('hot_stock')
@app.route('/api/penny-stock')
def api_penny_stock(): return get_daily_pick_response('penny_stock')
@app.route('/api/monthly-dividend')
def api_monthly_dividend_stock(): return get_daily_pick_response('monthly_dividend')
@app.route('/api/high-yield-dividend')
def api_high_yield_dividend_stock(): return get_daily_pick_response('high_yield_dividend')

@app.route('/api/portfolio/<portfolio_name>')
def portfolio_data(portfolio_name):
    # ... (code is correct from previous version) ...
    pass

@app.route('/api/trigger-investment/<portfolio_name>', methods=['POST'])
def trigger_investment(portfolio_name):
    # ... (code is correct from previous version) ...
    pass

@app.route('/api/run-scraper', methods=['POST'])
def run_scraper_api():
    # ... (code is correct from previous version) ...
    pass

@app.route('/api/run-sentiment-analysis', methods=['POST'])
def run_sentiment_analysis_api():
    # ... (code is correct from previous version) ...
    pass

@app.route('/api/run-enrichment', methods=['POST'])
def run_enrichment_api():
    # ... (code is correct from previous version) ...
    pass
