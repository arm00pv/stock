import pandas as pd
import numpy as np
import yfinance as yf
from scipy.stats import linregress
from sklearn.ensemble import IsolationForest
from ai_prediction import StockPredictor
import random
from concurrent.futures import ThreadPoolExecutor

# --- Utilities ---
def fetch_history(tickers, period='6mo'):
    try:
        data = yf.download(tickers, period=period, group_by='ticker', progress=False)
        return data
    except Exception as e:
        print(f"Error fetching history for {tickers}: {e}")
        return None

# --- Smart Signals ---
def calculate_smart_signals(ticker):
    """Calculates RSI and MACD signals."""
    df = fetch_history([ticker], period='1y')
    if df is None or df.empty:
        return {'signal': 'Neutral', 'rsi': 0, 'macd': 0}

    # Handle MultiIndex
    if isinstance(df.columns, pd.MultiIndex):
        df = df[ticker]

    close = df['Close']

    # RSI
    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    current_rsi = rsi.iloc[-1]

    # MACD
    exp1 = close.ewm(span=12, adjust=False).mean()
    exp2 = close.ewm(span=26, adjust=False).mean()
    macd = exp1 - exp2
    signal_line = macd.ewm(span=9, adjust=False).mean()

    signal = 'Neutral'
    if current_rsi < 30:
        signal = 'Buy (Oversold)'
    elif current_rsi > 70:
        signal = 'Sell (Overbought)'
    elif macd.iloc[-1] > signal_line.iloc[-1]:
        signal = 'Buy (MACD Crossover)'
    elif macd.iloc[-1] < signal_line.iloc[-1]:
        signal = 'Sell (MACD Crossover)'

    return {
        'signal': signal,
        'rsi': round(float(current_rsi), 2),
        'macd': round(float(macd.iloc[-1]), 2),
        'ticker': ticker
    }

# --- Market Anomalies ---
def detect_anomalies(tickers):
    """Uses Isolation Forest to detect volume/price anomalies."""
    if not tickers:
        return []

    data = fetch_history(tickers, period='1mo')
    if data is None:
        return []

    anomalies = []

    for ticker in tickers:
        try:
            if isinstance(data.columns, pd.MultiIndex):
                df = data[ticker].copy()
            else:
                df = data.copy() # Single ticker case logic if needed

            if df.empty: continue

            df['Returns'] = df['Close'].pct_change()
            df['Volume_Change'] = df['Volume'].pct_change()
            df.dropna(inplace=True)

            if len(df) < 10: continue

            X = df[['Returns', 'Volume_Change']]
            iso_forest = IsolationForest(contamination=0.05, random_state=42)
            preds = iso_forest.fit_predict(X)

            if preds[-1] == -1: # Last data point is anomaly
                anomalies.append({
                    'ticker': ticker,
                    'reason': 'Unusual Price/Volume Activity',
                    'last_price': float(df['Close'].iloc[-1])
                })
        except Exception as e:
            continue

    return anomalies

# --- Efficient Frontier ---
def simulate_efficient_frontier(tickers):
    """Generates random portfolios to visualize risk vs return."""
    if len(tickers) < 2:
        return {'error': 'Need at least 2 stocks'}

    data = fetch_history(tickers, period='1y')
    if data is None: return {}

    closes = pd.DataFrame()
    for ticker in tickers:
        if isinstance(data.columns, pd.MultiIndex):
            closes[ticker] = data[ticker]['Close']
        else:
            closes[ticker] = data['Close'] # Should not happen with multiple tickers

    closes.dropna(inplace=True)
    daily_returns = closes.pct_change()

    results = []
    num_portfolios = 200 # Reduced for performance

    for _ in range(num_portfolios):
        weights = np.random.random(len(tickers))
        weights /= np.sum(weights)

        portfolio_return = np.sum(daily_returns.mean() * weights) * 252
        portfolio_std_dev = np.sqrt(np.dot(weights.T, np.dot(daily_returns.cov() * 252, weights)))

        results.append({
            'return': round(portfolio_return, 4),
            'risk': round(portfolio_std_dev, 4),
            'weights': {t: round(w, 2) for t, w in zip(tickers, weights)}
        })

    return results

# --- Pattern Scanner ---
def scan_patterns(ticker):
    """Simple pattern scanner."""
    df = fetch_history([ticker], period='3mo')
    if df is None: return []

    if isinstance(df.columns, pd.MultiIndex):
        df = df[ticker]

    patterns = []

    # Double Bottom (Simplified)
    # Check for two local minima roughly equal separated by a peak
    # This is a very basic placeholder logic
    closes = df['Close'].values
    if len(closes) > 20:
        recent_min = np.min(closes[-20:])
        # ... real logic is complex, returning mock for demo if structure fits
        if closes[-1] > recent_min * 1.05:
            patterns.append("Potential Recovery")

    # Double Top (Simplified)
    # Check for two local maxima

    return patterns

# --- Sector Rotation ---
def sector_rotation_analysis():
    """Analyzes sector ETFs for rotation."""
    sectors = {
        'XLK': 'Technology', 'XLF': 'Financials', 'XLV': 'Healthcare',
        'XLE': 'Energy', 'XLI': 'Industrials', 'XLY': 'Consumer Discretionary',
        'XLP': 'Consumer Staples', 'XLU': 'Utilities', 'XLB': 'Materials',
        'XLRE': 'Real Estate'
    }

    data = fetch_history(list(sectors.keys()), period='6mo')
    results = []

    if data is None: return []

    for ticker, name in sectors.items():
        try:
            if isinstance(data.columns, pd.MultiIndex):
                hist = data[ticker]
            else:
                continue # Should be multi

            # Simple momentum: 3-month return
            start = hist['Close'].iloc[0]
            end = hist['Close'].iloc[-1]
            momentum = (end - start) / start

            results.append({
                'sector': name,
                'ticker': ticker,
                'momentum': round(momentum * 100, 2)
            })
        except Exception:
            continue

    results.sort(key=lambda x: x['momentum'], reverse=True)
    return results

# --- AI Trade Thesis ---
def generate_trade_thesis(ticker):
    """Synthesizes data into a thesis."""
    signals = calculate_smart_signals(ticker)
    predictor = StockPredictor()
    prediction = predictor.train_and_predict(ticker)

    verdict = "Hold"
    confidence = "Medium"

    if signals['signal'].startswith('Buy') and prediction and prediction > yf.Ticker(ticker).info.get('regularMarketPrice', 0):
        verdict = "Buy"
        confidence = "High"
    elif signals['signal'].startswith('Sell'):
        verdict = "Sell"

    thesis = f"The AI analysis for {ticker} suggests a {verdict} rating. "
    thesis += f"Technical indicators show {signals['signal']}. "
    if prediction:
        thesis += f"AI Price Target (7-day) is ${prediction:.2f}. "

    return {
        'ticker': ticker,
        'verdict': verdict,
        'confidence': confidence,
        'thesis': thesis,
        'details': signals
    }

# --- Pro Details (Mock/Wrapper) ---
def get_pro_details(ticker):
    try:
        t = yf.Ticker(ticker)
        info = t.info
        return {
            'peg_ratio': info.get('pegRatio'),
            'beta': info.get('beta'),
            'f_score': random.randint(1, 9), # Mock F-Score as it requires detailed financials
            'insider_activity': "Low", # Requires paid API usually
            'analyst_rating': info.get('recommendationKey', 'none'),
            'institutional_ownership': info.get('heldPercentInstitutions')
        }
    except:
        return {}

# --- Trending Topics ---
def get_trending_topics():
    # In a real app, this would scrape news. Returning static list for now.
    return [
        {'text': 'Inflation', 'value': 50},
        {'text': 'AI', 'value': 45},
        {'text': 'Earnings', 'value': 40},
        {'text': 'Fed', 'value': 35},
        {'text': 'Recession', 'value': 30}
    ]

# --- Correlation Matrix ---
def get_correlation_matrix(tickers):
    data = fetch_history(tickers, period='1y')
    if data is None: return {}

    closes = pd.DataFrame()
    for t in tickers:
        if isinstance(data.columns, pd.MultiIndex):
            closes[t] = data[t]['Close']

    corr = closes.corr()
    # Convert to format suitable for frontend (e.g. lists of values)
    matrix = []
    labels = list(corr.columns)
    for row in corr.values:
        matrix.append([round(x, 2) for x in row])

    return {'labels': labels, 'matrix': matrix}

# --- Crypto Sentiment ---
def get_crypto_sentiment():
    # Mock
    return {'bitcoin': 'Bullish', 'ethereum': 'Neutral'}

# --- DCF Valuation ---
def calculate_dcf(ticker):
    # Very simplified DCF
    try:
        t = yf.Ticker(ticker)
        info = t.info
        fcf = info.get('freeCashflow')
        if not fcf: return None

        growth_rate = 0.05
        discount_rate = 0.10
        terminal_growth = 0.02

        # 5 year projection
        future_fcf = []
        for i in range(1, 6):
            future_fcf.append(fcf * ((1 + growth_rate) ** i))

        # Terminal Value
        terminal_val = future_fcf[-1] * (1 + terminal_growth) / (discount_rate - terminal_growth)

        # PV
        dcf_val = 0
        for i, val in enumerate(future_fcf):
            dcf_val += val / ((1 + discount_rate) ** (i + 1))

        dcf_val += terminal_val / ((1 + discount_rate) ** 5)

        shares = info.get('sharesOutstanding')
        if shares:
            fair_value = dcf_val / shares
            return round(fair_value, 2)
        return None
    except Exception:
        return None

# --- Stock Comparison ---
def compare_stocks(ticker1, ticker2):
    """Compares two stocks on key metrics."""
    def get_metrics(ticker):
        try:
            info = yf.Ticker(ticker).info
            hist = fetch_history([ticker], period='1y')
            if isinstance(hist.columns, pd.MultiIndex):
                hist = hist[ticker]

            # Calculate volatility (annualized std dev of daily returns)
            returns = hist['Close'].pct_change()
            volatility = returns.std() * np.sqrt(252)

            return {
                'ticker': ticker,
                'price': info.get('regularMarketPrice'),
                'pe_ratio': info.get('trailingPE'),
                'market_cap': info.get('marketCap'),
                'beta': info.get('beta'),
                'volatility': round(volatility * 100, 2),
                '52_week_high': info.get('fiftyTwoWeekHigh'),
                '52_week_low': info.get('fiftyTwoWeekLow')
            }
        except Exception as e:
            return {'ticker': ticker, 'error': str(e)}

    with ThreadPoolExecutor(max_workers=2) as executor:
        t1_metrics = executor.submit(get_metrics, ticker1).result()
        t2_metrics = executor.submit(get_metrics, ticker2).result()

    return {'ticker1': t1_metrics, 'ticker2': t2_metrics}

# --- Chart Data ---
def get_history_data(ticker):
    """Fetches historical closing data for charts."""
    df = fetch_history([ticker], period='1y')
    if df is None or df.empty:
        return {'labels': [], 'data': []}

    if isinstance(df.columns, pd.MultiIndex):
        df = df[ticker]

    df = df.reset_index()
    # Format: labels (dates), data (prices)
    labels = df.iloc[:, 0].dt.strftime('%Y-%m-%d').tolist() # Assume first col is Date
    prices = df['Close'].tolist()

    return {'labels': labels, 'data': prices}
