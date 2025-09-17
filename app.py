import os
from datetime import datetime, timedelta
import yfinance as yf
import pandas as pd
from flask import Flask, render_template, jsonify, request, abort
from werkzeug.middleware.proxy_fix import ProxyFix
from dotenv import load_dotenv

load_dotenv()

from database import (
    init_db, get_tickers_by_category, get_portfolio_summary, get_portfolio_holdings,
    execute_investment, save_daily_pick, get_pick_history_for_category,
    get_todays_pick_for_category, get_recently_picked_tickers
)
from scraper import run_scraper_pipeline
from sentiment_analyzer import get_sentiment_for_tickers, run_sentiment_analysis
from performance_tracker import run_performance_check
from enricher import run_enrichment
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
    'hot_stock': { 'db_categories': ['sp500', 'generic_stock', 'etf'], 'display_name': 'Hot Picks' },
    'penny_stock': { 'db_categories': ['penny', 'etf', 'generic_stock'], 'display_name': '$5 or Less', 'price_limit': 5 },
    'monthly_dividend': {'db_categories': ['monthly_dividend'], 'display_name': 'Monthly Dividends'},
    'high_yield_dividend': {'db_categories': ['high_yield'], 'display_name': 'High-Yield Dividends'}
}

# --- Stock Finding Logic ---
def find_growth_candidate(categories_to_search, price_limit=None):
    print(f"--- Starting Growth Candidate Search ---")
    print(f"Params: categories={categories_to_search}, price_limit={price_limit}")

    # 1. Fetch all unique tickers from the database
    all_tickers = []
    for category in categories_to_search:
        all_tickers.extend(get_tickers_by_category(category))
    unique_tickers = sorted(list(set(all_tickers)))
    print(f"Found {len(unique_tickers)} unique tickers to screen.")

    # 2. Filter out recently picked tickers
    recent_picks = set()
    all_history_categories = ['sp500', 'penny', 'monthly_dividend', 'high_yield', 'daily_investment_pick']
    for category in all_history_categories:
        recent_picks.update(get_recently_picked_tickers(category))

    candidate_tickers = [t for t in unique_tickers if t not in recent_picks]
    print(f"Screening {len(candidate_tickers)} tickers after removing recent picks.")
    if not candidate_tickers:
        print("No tickers left to screen. Aborting.")
        return {'ticker': None, 'sentiment': None}

    # 3. Batch download historical data
    print("Downloading historical data for all candidates...")
    end_date = datetime.now()
    start_date = end_date - timedelta(days=SMA_LONG + 50) # Get extra data for rolling averages

    try:
        # yfinance can be flaky, so we add a try/except block
        data = yf.download(candidate_tickers, start=start_date, end=end_date, group_by='ticker')
        if data.empty:
            print("yfinance download returned no data.")
            raise ValueError("No data from yfinance")
    except Exception as e:
        print(f"CRITICAL: yfinance download failed: {e}")
        # Fallback to the old method for the first available ticker if batch fails
        for ticker in candidate_tickers:
            if ticker not in recent_picks:
                return {'ticker': ticker, 'sentiment': None}
        return {'ticker': unique_tickers[0] if unique_tickers else None, 'sentiment': None}

    print("Historical data downloaded. Starting analysis...")

    # Tier 1: Golden Cross
    print("\n--- Tier 1: Golden Cross Screen ---")
    technical_candidates = []

    # Using a list comprehension with a loop for clarity
    for ticker in candidate_tickers:
        try:
            hist = data[ticker]
            if hist.empty or len(hist.index) < SMA_LONG + 1:
                # print(f"  - Skipping {ticker}: Not enough historical data ({len(hist.index)} days)")
                continue

            # Volume and Price check
            avg_volume = hist['Volume'].rolling(window=10).mean().iloc[-1]
            if avg_volume < MIN_AVG_VOLUME:
                # print(f"  - Skipping {ticker}: Low volume ({avg_volume:.0f})")
                continue

            if price_limit:
                current_price = hist['Close'].iloc[-1]
                if current_price > price_limit:
                    # print(f"  - Skipping {ticker}: Price ${current_price:.2f} > limit of ${price_limit}")
                    continue

            # SMA Calculation
            sma50 = hist['Close'].rolling(window=SMA_SHORT).mean()
            sma200 = hist['Close'].rolling(window=SMA_LONG).mean()

            # Golden Cross Check
            if sma50.iloc[-2] < sma200.iloc[-2] and sma50.iloc[-1] > sma200.iloc[-1]:
                print(f"  + Found Golden Cross Candidate: {ticker}")
                technical_candidates.append(ticker)

        except KeyError:
            # This happens if a ticker in the batch download fails
            # print(f"  - Skipping {ticker}: Data not found in downloaded batch (likely delisted or invalid).")
            pass
        except Exception as e:
            print(f"  - Error processing {ticker}: {e}")

    if technical_candidates:
        print(f"\nFound {len(technical_candidates)} technical candidates. Analyzing sentiment...")
        sentiment_scores = get_sentiment_for_tickers(technical_candidates)
        sentiment_candidates = [{'ticker': t, 'sentiment': sentiment_scores.get(t, 0)} for t in technical_candidates]
        sentiment_candidates.sort(key=lambda x: x['sentiment'], reverse=True)

        best_candidate = sentiment_candidates[0]
        if best_candidate['sentiment'] >= POSITIVE_SENTIMENT_THRESHOLD:
            print(f"Selected candidate by sentiment: {best_candidate['ticker']} (Score: {best_candidate['sentiment']})")
            return best_candidate
        else:
            print(f"Top candidate {best_candidate['ticker']} did not meet sentiment threshold. Falling back to first technical candidate.")
            return {'ticker': technical_candidates[0], 'sentiment': None}

    # Tier 2: 3-Day Growth
    print("\n--- Tier 2: 3-Day Growth Screen ---")
    three_day_candidates = []
    for ticker in candidate_tickers:
        try:
            hist = data[ticker]['Close']
            if len(hist) < 4: continue
            # Check for 3 consecutive days of closing higher than the previous day
            if hist.iloc[-1] > hist.iloc[-2] and hist.iloc[-2] > hist.iloc[-3] and hist.iloc[-3] > hist.iloc[-4]:
                 # Price check for this tier
                if price_limit and hist.iloc[-1] > price_limit:
                    continue
                print(f"  + Found 3-Day Growth Candidate: {ticker}")
                three_day_candidates.append(ticker)
        except (KeyError, IndexError):
            continue

    if three_day_candidates:
        print(f"Selected candidate by 3-day growth: {three_day_candidates[0]}")
        return {'ticker': three_day_candidates[0], 'sentiment': None}

    # Tier 3: Fallback
    print("\n--- Tier 3: Fallback ---")
    for ticker in candidate_tickers:
        if ticker not in recent_picks: # Redundant check, but safe
            print(f"Selected fallback candidate: {ticker}")
            return {'ticker': ticker, 'sentiment': None}

    # Ultimate fallback
    if unique_tickers:
        print(f"Selected ultimate fallback candidate: {unique_tickers[0]}")
        return {'ticker': unique_tickers[0], 'sentiment': None}

    print("--- No suitable stock found in any tier. ---")
    return {'ticker': None, 'sentiment': None}

def find_hot_stock(category_key):
    details = CATEGORIES.get(category_key, {})
    return find_growth_candidate(categories_to_search=details.get('db_categories', []), price_limit=details.get('price_limit'))

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
    details = CATEGORIES[category_key]
    db_category = details['db_categories'][0]
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
    except Exception as e:
        return jsonify({'ticker': f'Error: {e}', 'history': []}), 500

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
        ticker = holding['ticker']
        current_price = get_from_cache(ticker)
        if current_price is None:
            try:
                current_price = yf.Ticker(ticker).info.get('regularMarketPrice', holding['purchase_price'])
                if current_price: set_in_cache(ticker, current_price)
            except Exception:
                current_price = holding['purchase_price']
        value = holding['shares'] * current_price
        total_value += value
        detailed_holdings.append({**holding, 'current_price': current_price, 'current_value': value})
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
    try: run_scraper_pipeline(); return jsonify({'status': 'success', 'message': 'Scraper executed.'})
    except Exception as e: return jsonify({'status': 'error', 'message': f'An error occurred: {e}'}), 500

@app.route('/api/run-sentiment-analysis', methods=['POST'])
def run_sentiment_analysis_api():
    if request.headers.get('X-API-Key') != SCRAPER_API_KEY: abort(401)
    try: run_sentiment_analysis(); return jsonify({'status': 'success', 'message': 'Sentiment analysis executed.'})
    except Exception as e: return jsonify({'status': 'error', 'message': f'An error occurred: {e}'}), 500

@app.route('/api/run-enrichment', methods=['POST'])
def run_enrichment_api():
    if request.headers.get('X-API-Key') != SCRAPER_API_KEY: abort(401)
    try: run_enrichment(); return jsonify({'status': 'success', 'message': 'Data enrichment executed.'})
    except Exception as e: return jsonify({'status': 'error', 'message': f'An error occurred: {e}'}), 500
