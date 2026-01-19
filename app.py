import os
import random
from datetime import datetime, timedelta
import yfinance as yf
import pandas as pd
from flask import Flask, render_template, jsonify, request, abort
from werkzeug.middleware.proxy_fix import ProxyFix
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor

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
import beta_features
from ai_assistant import get_ai_response

app = Flask(__name__)

# --- Configuration ---
SCRAPER_API_KEY = os.environ.get('SCRAPER_API_KEY', 'your-super-secret-key')
app.wsgi_app = ProxyFix(app.wsgi_app, x_prefix=1)
app.config['SESSION_COOKIE_NAME'] = os.environ.get('SESSION_COOKIE_NAME', 'session')
app.config['SESSION_COOKIE_PATH'] = os.environ.get('SESSION_COOKIE_PATH', '/')
app.config['SESSION_COOKIE_SECURE'] = True
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

# --- Constants ---
MIN_AVG_VOLUME = 100000
SMA_SHORT = 50
SMA_LONG = 200
POSITIVE_SENTIMENT_THRESHOLD = 0.2
MAX_TICKERS_TO_SCREEN = 300

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

    # 3. Limit number of tickers to prevent memory overload and timeouts
    if len(candidate_tickers) > MAX_TICKERS_TO_SCREEN:
        print(f"Candidate list is too large ({len(candidate_tickers)}). Screening a random sample of {MAX_TICKERS_TO_SCREEN}.")
        candidate_tickers = random.sample(candidate_tickers, MAX_TICKERS_TO_SCREEN)

    if not candidate_tickers:
        print("No tickers left to screen. Aborting.")
        return {'ticker': None, 'sentiment': None}

    # 4. Batch download historical data
    print(f"Downloading historical data for {len(candidate_tickers)} candidates...")
    end_date = datetime.now()
    start_date = end_date - timedelta(days=SMA_LONG + 50) # Get extra data for rolling averages

    try:
        data = yf.download(candidate_tickers, start=start_date, end=end_date, group_by='ticker', progress=False)
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

    for ticker in candidate_tickers:
        try:
            hist = data[ticker]
            if hist.empty or len(hist.index) < SMA_LONG + 1:
                continue

            avg_volume = hist['Volume'].rolling(window=10).mean().iloc[-1]
            if avg_volume < MIN_AVG_VOLUME:
                continue

            if price_limit:
                current_price = hist['Close'].iloc[-1]
                if current_price > price_limit:
                    continue

            sma50 = hist['Close'].rolling(window=SMA_SHORT).mean()
            sma200 = hist['Close'].rolling(window=SMA_LONG).mean()

            if sma50.iloc[-2] < sma200.iloc[-2] and sma50.iloc[-1] > sma200.iloc[-1]:
                print(f"  + Found Golden Cross Candidate: {ticker}")
                technical_candidates.append(ticker)
        except KeyError:
            pass # Ticker data might not be in the batch
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
            if hist.iloc[-1] > hist.iloc[-2] and hist.iloc[-2] > hist.iloc[-3] and hist.iloc[-3] > hist.iloc[-4]:
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
        if ticker not in recent_picks:
            print(f"Selected fallback candidate: {ticker}")
            return {'ticker': ticker, 'sentiment': None}

    if unique_tickers:
        print(f"Selected ultimate fallback candidate: {unique_tickers[0]}")
        return {'ticker': unique_tickers[0], 'sentiment': None}

    print("--- No suitable stock found in any tier. ---")
    return {'ticker': None, 'sentiment': None}

def find_hot_stock(category_key):
    details = CATEGORIES.get(category_key, {})
    return find_growth_candidate(categories_to_search=details.get('db_categories', []), price_limit=details.get('price_limit'))

def find_best_candidate_from_all():
    return find_growth_candidate(categories_to_search=['sp500', 'penny', 'etf', 'generic_stock', 'bond'])

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

    # Use ThreadPoolExecutor for parallel price fetching
    def fetch_price(holding):
        ticker = holding['ticker']
        cached = get_from_cache(ticker)
        if cached:
            return ticker, cached
        try:
            # Fallback to purchase price if fetch fails
            price = yf.Ticker(ticker).info.get('regularMarketPrice')
            if price:
                set_in_cache(ticker, price)
                return ticker, price
        except:
            pass
        return ticker, holding['purchase_price']

    with ThreadPoolExecutor(max_workers=10) as executor:
        prices = dict(executor.map(fetch_price, holdings))

    total_value = 0
    detailed_holdings = []
    for holding in holdings:
        ticker = holding['ticker']
        current_price = prices.get(ticker, holding['purchase_price'])
        if current_price is None: current_price = holding['purchase_price'] # Safety net

        value = holding['shares'] * current_price
        total_value += value
        detailed_holdings.append({**holding, 'current_price': current_price, 'current_value': value})

    return jsonify({'portfolio_name': portfolio_name, 'cash_balance': summary[0], 'total_invested': summary[1], 'current_market_value': total_value, 'total_assets': summary[0] + total_value, 'holdings': detailed_holdings})

@app.route('/api/trigger-investment/<portfolio_name>', methods=['POST'])
def trigger_investment(portfolio_name):
    try:
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

        price = yf.Ticker(candidate_ticker).info.get('regularMarketPrice')
        if not price or price <= 0:
            print(f"Error: Invalid or zero price ('{price}') received for ticker {candidate_ticker}. Aborting investment.")
            raise ValueError(f"Invalid price for {candidate_ticker}")

        shares_to_buy = investment_amount / price
        execute_investment(portfolio_name, candidate_ticker, shares_to_buy, price, investment_amount)
        print(f"Successfully executed investment of ${investment_amount:.2f} in {candidate_ticker} for '{portfolio_name}' portfolio.")
        return jsonify({'status': 'success', 'message': f"Successfully invested ${investment_amount:.2f} in {candidate_ticker} for '{portfolio_name}' portfolio."})
    except BaseException as e:
        # Using BaseException to catch everything, including SystemExit from libraries
        import traceback
        print(f"--- UNHANDLED EXCEPTION IN trigger_investment ---")
        print(f"Portfolio: {portfolio_name}")
        print(f"Exception Type: {type(e).__name__}")
        print(f"Exception: {e}")
        traceback.print_exc()
        print(f"-------------------------------------------------")
        # Return a generic 500 error, the real details are in the server log
        return jsonify({'status': 'error', 'message': 'An unexpected server error occurred. Check server logs for details.'}), 500

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

# --- Beta Endpoints ---
@app.route('/api/beta/signals/<ticker>')
def beta_signals(ticker):
    return jsonify(beta_features.calculate_smart_signals(ticker))

@app.route('/api/beta/anomalies')
def beta_anomalies():
    # Detect anomalies in recently active tickers or a subset
    tickers = ['AAPL', 'MSFT', 'GOOG', 'AMZN', 'TSLA', 'SPY', 'QQQ', 'NVDA'] # Sample
    return jsonify(beta_features.detect_anomalies(tickers))

@app.route('/api/beta/patterns/<ticker>')
def beta_patterns(ticker):
    return jsonify(beta_features.scan_patterns(ticker))

@app.route('/api/beta/sector-rotation')
def beta_sector_rotation():
    return jsonify(beta_features.sector_rotation_analysis())

@app.route('/api/beta/thesis/<ticker>')
def beta_thesis(ticker):
    return jsonify(beta_features.generate_trade_thesis(ticker))

@app.route('/api/beta/pro/<ticker>')
def beta_pro_details(ticker):
    return jsonify(beta_features.get_pro_details(ticker))

@app.route('/api/beta/trending')
def beta_trending():
    return jsonify(beta_features.get_trending_topics())

@app.route('/api/beta/correlation', methods=['POST'])
def beta_correlation():
    tickers = request.json.get('tickers', [])
    if not tickers: return jsonify({'error': 'No tickers provided'}), 400
    return jsonify(beta_features.get_correlation_matrix(tickers))

@app.route('/api/beta/efficient-frontier', methods=['POST'])
def beta_efficient_frontier():
    tickers = request.json.get('tickers', [])
    if not tickers: return jsonify({'error': 'No tickers provided'}), 400
    return jsonify(beta_features.simulate_efficient_frontier(tickers))

@app.route('/api/beta/compare')
def beta_compare():
    t1 = request.args.get('ticker1')
    t2 = request.args.get('ticker2')
    if not t1 or not t2: return jsonify({'error': 'Missing tickers'}), 400
    return jsonify(beta_features.compare_stocks(t1, t2))

@app.route('/api/history/<ticker>')
def api_history(ticker):
    return jsonify(beta_features.get_history_data(ticker))

@app.route('/api/chat', methods=['POST'])
def chat_endpoint():
    user_message = request.json.get('message', '')
    if not user_message: return jsonify({'response': 'Please say something.'})
    response = get_ai_response(user_message)
    return jsonify({'response': response})
