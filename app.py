import os
from datetime import datetime, timedelta
# import yfinance as yf
# import pandas as pd
from flask import Flask, render_template, jsonify, request, abort
from werkzeug.middleware.proxy_fix import ProxyFix

from database import (
    init_db, get_tickers_by_category, get_portfolio_summary, get_portfolio_holdings,
    execute_investment, save_daily_pick, get_pick_history_for_category,
    get_todays_pick_for_category, get_recently_picked_tickers
)
# from scraper import run_scraper_pipeline
# from sentiment_analyzer import get_sentiment_for_tickers
# from utils import is_market_open

app = Flask(__name__)

# --- Configuration ---
SCRAPER_API_KEY = os.environ.get('SCRAPER_API_KEY', 'your-super-secret-key')
app.wsgi_app = ProxyFix(app.wsgi_app, x_prefix=1)

# --- Constants ---
MIN_AVG_VOLUME = 100000
SMA_SHORT = 50
SMA_LONG = 200
POSITIVE_SENTIMENT_THRESHOLD = 0.3

# --- Categories ---
CATEGORIES = {
    'hot_stock': {'db_category': 'sp500', 'display_name': 'Hot Stocks'},
    'penny_stock': {'db_category': 'penny', 'display_name': '$5 or Less', 'price_limit': 5},
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

    if not technical_candidates: return {'ticker': None, 'sentiment': None}

    sentiment_scores = get_sentiment_for_tickers(technical_candidates)
    sentiment_candidates = []
    for ticker in technical_candidates:
        score = sentiment_scores.get(ticker)
        if score is not None and score >= POSITIVE_SENTIMENT_THRESHOLD:
            sentiment_candidates.append({'ticker': ticker, 'sentiment': score})

    if not sentiment_candidates:
        ticker = technical_candidates[0]
        return {'ticker': ticker, 'sentiment': sentiment_scores.get(ticker)}

    sentiment_candidates.sort(key=lambda x: x['sentiment'], reverse=True)
    return sentiment_candidates[0]

def find_hot_stock(category_key):
    details = CATEGORIES.get(category_key, {})
    return find_growth_candidate(
        categories_to_search=[details.get('db_category')],
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

# --- Generic Endpoint Logic ---
def get_daily_pick_response(category_key):
    db_category = CATEGORIES[category_key]['db_category']
    try:
        todays_pick = get_todays_pick_for_category(db_category)
        if todays_pick:
            stock_ticker, sentiment = todays_pick['ticker'], todays_pick.get('sentiment_score')
        else:
            result = find_dividend_stock(db_category) if 'dividend' in category_key else find_hot_stock(category_key)
            stock_ticker, sentiment = result['ticker'], result['sentiment']
            if stock_ticker: save_daily_pick(db_category, stock_ticker, sentiment)

        history = get_pick_history_for_category(db_category)
        message = stock_ticker if stock_ticker else 'No suitable stock found today.'
        return jsonify({'ticker': message, 'history': history})
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
    summary = get_portfolio_summary(portfolio_name)
    holdings = get_portfolio_holdings(portfolio_name)
    total_value = 0
    detailed_holdings = []
    for holding in holdings:
        try:
            current_price = yf.Ticker(holding['ticker']).info.get('regularMarketPrice', holding['purchase_price'])
            value = holding['shares'] * current_price
            total_value += value
            detailed_holdings.append({**holding, 'current_price': current_price, 'current_value': value})
        except Exception:
            total_value += holding['shares'] * holding['purchase_price']
            detailed_holdings.append({**holding, 'current_price': holding['purchase_price'], 'current_value': holding['shares'] * holding['purchase_price']})
    return jsonify({'portfolio_name': portfolio_name, 'cash_balance': summary[0], 'total_invested': summary[1], 'current_market_value': total_value, 'total_assets': summary[0] + total_value, 'holdings': detailed_holdings})

@app.route('/api/trigger-investment/<portfolio_name>', methods=['POST'])
def trigger_investment(portfolio_name):
    investment_amount = 5.00
    result = None
    if portfolio_name == 'daily_investment':
        if not is_market_open(): return jsonify({'status': 'success', 'message': 'Market is closed today. No investment made.'})
        result = find_best_candidate_from_all()
        if result and result.get('ticker'): save_daily_pick('daily_investment_pick', result['ticker'], result.get('sentiment'))
    elif portfolio_name == 'main':
        result = find_hot_stock('hot_stock')
    elif portfolio_name == 'monthly_dividend':
        result = find_dividend_stock('monthly_dividend')
    elif portfolio_name == 'high_yield_investment':
        result = find_dividend_stock('high_yield')
    else:
        return jsonify({'status': 'error', 'message': 'Invalid portfolio name.'}), 404

    candidate_ticker = result.get('ticker') if result else None
    if not candidate_ticker: return jsonify({'status': 'error', 'message': f'No suitable stock found for {portfolio_name} portfolio investment.'})

    try:
        price = yf.Ticker(candidate_ticker).info.get('regularMarketPrice')
        if not price or price <= 0: raise ValueError("Invalid price")
    except Exception as e:
        return jsonify({'status': 'error', 'message': f"Could not fetch price for {candidate_ticker}: {e}"})

    shares_to_buy = investment_amount / price
    execute_investment(portfolio_name, candidate_ticker, shares_to_buy, price, investment_amount)
    return jsonify({'status': 'success', 'message': f"Successfully invested ${investment_amount:.2f} in {candidate_ticker} for '{portfolio_name}' portfolio."})

@app.route('/api/run-scraper', methods=['POST'])
def run_scraper_api():
    if request.headers.get('X-API-Key') != SCRAPER_API_KEY: abort(401)
    try:
        run_scraper_pipeline()
        return jsonify({'status': 'success', 'message': 'Scraper pipeline executed successfully.'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': f'An error occurred: {e}'}), 500

@app.route('/api/run-sentiment-analysis', methods=['POST'])
def run_sentiment_analysis_api():
    if request.headers.get('X-API-Key') != SCRAPER_API_KEY: abort(401)
    from sentiment_analyzer import run_sentiment_analysis
    try:
        run_sentiment_analysis()
        return jsonify({'status': 'success', 'message': 'Sentiment analysis executed successfully.'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': f'An error occurred: {e}'}), 500
