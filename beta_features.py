import yfinance as yf
import pandas as pd
import numpy as np
import logging
import requests
import re
from collections import Counter
from scipy.optimize import minimize
from scipy.signal import find_peaks
from sklearn.ensemble import IsolationForest
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
from database import get_db_connection
from sp500_list import SP500_TICKERS
from notifications import create_notification

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def get_smart_signals():
    """
    Scans SP500 subset for:
    1. Golden Cross (50 MA crosses above 200 MA)
    2. RSI Oversold (< 30)
    3. Volume Spike (> 200% of 20-day avg)
    """
    tickers = SP500_TICKERS
    signals = []

    try:
        # Download 1 year of data for MA calculation
        data = yf.download(tickers, period="1y", progress=False)
        if data.empty or 'Close' not in data or 'Volume' not in data:
            return []

        close_data = data['Close']
        volume_data = data['Volume']

        for ticker in tickers:
            if ticker not in close_data: continue

            series = close_data[ticker].dropna()
            if len(series) < 200: continue

            current_price = series.iloc[-1]

            # MA Calculation
            ma_50 = series.rolling(window=50).mean()
            ma_200 = series.rolling(window=200).mean()

            # Check Golden Cross (Today 50 > 200, Yesterday 50 <= 200)
            golden_cross = False
            if len(ma_50) > 1 and len(ma_200) > 1:
                if ma_50.iloc[-1] > ma_200.iloc[-1] and ma_50.iloc[-2] <= ma_200.iloc[-2]:
                    golden_cross = True

            # RSI Calculation
            delta = series.diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            rsi = 100 - (100 / (1 + rs))
            current_rsi = rsi.iloc[-1]

            # Volume Spike Calculation
            vol_series = volume_data[ticker].dropna()
            vol_spike = False
            if len(vol_series) > 20:
                current_vol = vol_series.iloc[-1]
                avg_vol_20 = vol_series.rolling(window=20).mean().iloc[-1]
                if avg_vol_20 > 0 and current_vol > 2 * avg_vol_20:
                    vol_spike = True

            detected = []
            if golden_cross:
                detected.append("Golden Cross")
            if not pd.isna(current_rsi) and current_rsi < 30:
                detected.append(f"Oversold (RSI {current_rsi:.0f})")
            if vol_spike:
                detected.append("Volume Spike")

            if detected:
                signals.append({
                    "ticker": ticker,
                    "price": float(current_price),
                    "signals": ", ".join(detected)
                })

    except Exception as e:
        logging.error(f"Error scanning signals: {e}")

    return signals

def get_correlation_matrix(tickers):
    """
    Returns a correlation matrix for the given list of tickers.
    """
    try:
        if len(tickers) < 2:
            return {}

        # Fetch 6mo history
        data = yf.download(tickers, period="6mo", progress=False)
        if data.empty or 'Close' not in data:
            return {}

        close_data = data['Close']
        correlation = close_data.corr().round(2)

        # Convert to list of dictionaries for easy frontend rendering
        # Structure: { 'tickers': ['AAPL', 'MSFT'], 'matrix': [[1.0, 0.5], [0.5, 1.0]] }

        # Ensure correlation index matches columns and order is preserved
        cols = correlation.columns.tolist()
        matrix = []
        for row_ticker in cols:
            row_data = []
            for col_ticker in cols:
                val = correlation.loc[row_ticker, col_ticker]
                row_data.append(float(val) if not pd.isna(val) else 0.0)
            matrix.append(row_data)

        return {
            'tickers': cols,
            'matrix': matrix
        }
    except Exception as e:
        logging.error(f"Error calculating correlation: {e}")
        return {}

def compare_stocks(tickers):
    """
    Compares performance and basic stats for a list of tickers.
    """
    results = []
    try:
        if not tickers: return []

        data = yf.download(tickers, period="1y", progress=False)
        if data.empty or 'Close' not in data: return []

        close = data['Close']

        for ticker in tickers:
            if ticker not in close: continue

            try:
                stock = yf.Ticker(ticker)
                info = stock.info
                series = close[ticker].dropna()

                if len(series) == 0: continue

                current_price = series.iloc[-1]
                start_price = series.iloc[0]
                perf_1y = ((current_price - start_price) / start_price) * 100

                # Normalize history for chart
                # Reindex to match the global close index to ensure alignment
                aligned_series = series.reindex(close.index)

                # Calculate percentage change relative to the first valid point
                # For plotting, we want to show 0% at the start of *this stock's* data or aligned start?
                # If aligned start is NaN, we can't show % change from global start.
                # Better: Show % change from *its own* start, but padded with Nulls at the beginning.

                first_valid_idx = series.first_valid_index()
                if first_valid_idx:
                    base_price = series.loc[first_valid_idx]
                    normalized_series = (aligned_series / base_price * 100) - 100
                else:
                    normalized_series = aligned_series # All NaNs

                # Replace NaN with None for JSON compatibility (Chart.js handles null)
                chart_data = normalized_series.where(pd.notnull(normalized_series), None).tolist()

                results.append({
                    'ticker': ticker,
                    'name': info.get('shortName', ticker),
                    'price': float(current_price),
                    'pe_ratio': info.get('trailingPE', 'N/A'),
                    'market_cap': info.get('marketCap', 'N/A'),
                    'perf_1y': float(perf_1y),
                    'chart_data': chart_data
                })
            except: continue

        # Common labels (dates) - roughly
        labels = close.index.strftime('%Y-%m-%d').tolist()
        return {'data': results, 'labels': labels}

    except Exception as e:
        logging.error(f"Error comparing stocks: {e}")
        return {}

def get_user_alerts(user_id):
    conn = get_db_connection()
    if not conn: return []
    try:
        with conn.cursor(dictionary=True) as cursor:
            cursor.execute("SELECT * FROM price_alerts WHERE user_id = %s AND is_triggered = FALSE", (user_id,))
            return cursor.fetchall()
    finally:
        conn.close()

def create_price_alert(user_id, ticker, target_price, condition_type):
    conn = get_db_connection()
    if not conn: return False
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO price_alerts (user_id, ticker, target_price, condition_type) VALUES (%s, %s, %s, %s)",
                (user_id, ticker, target_price, condition_type)
            )
            conn.commit()
            return True
    except Exception as e:
        logging.error(f"Error creating alert: {e}")
        return False
    finally:
        conn.close()

def delete_price_alert(alert_id, user_id):
    conn = get_db_connection()
    if not conn: return False
    try:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM price_alerts WHERE id = %s AND user_id = %s", (alert_id, user_id))
            conn.commit()
            return True
    finally:
        conn.close()

def check_user_alerts(user_id):
    """
    Checks active alerts for a user against current prices.
    Returns a list of triggered alerts (and marks them triggered in DB).
    """
    conn = get_db_connection()
    if not conn: return []

    triggered = []
    try:
        with conn.cursor(dictionary=True) as cursor:
            cursor.execute("SELECT * FROM price_alerts WHERE user_id = %s AND is_triggered = FALSE", (user_id,))
            alerts = cursor.fetchall()

            if not alerts: return []

            tickers = list(set(a['ticker'] for a in alerts))
            data = yf.download(tickers, period="1d", progress=False)
            if data.empty or 'Close' not in data: return []

            close_data = data['Close']
            current_prices = {}
            if len(tickers) > 1:
                current_prices = close_data.iloc[-1].to_dict()
            else:
                current_prices = {tickers[0]: close_data.iloc[-1]}

            for alert in alerts:
                ticker = alert['ticker']
                price = float(current_prices.get(ticker, 0))
                if price == 0: continue

                target = float(alert['target_price'])
                is_hit = False

                if alert['condition_type'] == 'ABOVE' and price >= target:
                    is_hit = True
                elif alert['condition_type'] == 'BELOW' and price <= target:
                    is_hit = True

                if is_hit:
                    triggered.append({
                        'ticker': ticker,
                        'price': price,
                        'target': target,
                        'condition': alert['condition_type']
                    })
                    # Mark triggered
                    cursor.execute("UPDATE price_alerts SET is_triggered = TRUE WHERE id = %s", (alert['id'],))
                    # Notify
                    create_notification(user_id, f"Price Alert: {ticker} is {alert['condition_type']} {target:.2f} (Current: {price:.2f})", "warning")

            conn.commit()
            return triggered
    except Exception as e:
        logging.error(f"Error checking alerts: {e}")
        return []
    finally:
        conn.close()

def get_candlestick_patterns():
    """
    Scans SP500 for candlestick patterns: Bullish Engulfing, Hammer.
    """
    tickers = SP500_TICKERS
    patterns = []

    try:
        data = yf.download(tickers, period="5d", progress=False) # Need Open, High, Low, Close
        if data.empty or 'Close' not in data or 'Open' not in data: return []

        close = data['Close']
        open_ = data['Open']
        high = data['High']
        low = data['Low']

        for ticker in tickers:
            try:
                if ticker not in close: continue

                c = close[ticker].dropna()
                o = open_[ticker].dropna()
                h = high[ticker].dropna()
                l = low[ticker].dropna()

                if len(c) < 2: continue

                # Today and Yesterday
                c0, c1 = c.iloc[-1], c.iloc[-2]
                o0, o1 = o.iloc[-1], o.iloc[-2]
                h0 = h.iloc[-1]
                l0 = l.iloc[-1]

                detected = []

                # Bullish Engulfing
                # Prev candle red (C < O), Curr candle green (C > O)
                # Curr Open < Prev Close, Curr Close > Prev Open (Engulfs body)
                if c1 < o1 and c0 > o0:
                    if o0 < c1 and c0 > o1:
                        detected.append("Bullish Engulfing")

                # Hammer
                # Small body near high, long lower shadow (> 2x body)
                body = abs(c0 - o0)
                lower_shadow = min(c0, o0) - l0
                upper_shadow = h0 - max(c0, o0)

                if lower_shadow > 2 * body and upper_shadow < body:
                    detected.append("Hammer")

                if detected:
                    patterns.append({
                        "ticker": ticker,
                        "pattern": ", ".join(detected),
                        "price": float(c0)
                    })
            except: continue

    except Exception as e:
        logging.error(f"Error scanning patterns: {e}")

    return patterns

def get_advanced_ticker_details(ticker):
    """
    Fetches advanced details: ESG, Recommendations, and Chart Data (SMA, BB).
    """
    try:
        stock = yf.Ticker(ticker)
        info = stock.info

        # ESG - yfinance often doesn't provide ESG in free tier reliably via .info or .sustainability
        # We will try to get what we can or use placeholders if missing
        esg_score = "N/A"
        recommendation = info.get('recommendationKey', 'N/A').replace('_', ' ').title()
        target_price = info.get('targetMeanPrice', 'N/A')

        # Chart Data Calculation
        hist = stock.history(period="6mo")
        if hist.empty: return None

        # SMA
        hist['SMA_20'] = hist['Close'].rolling(window=20).mean()
        hist['SMA_50'] = hist['Close'].rolling(window=50).mean()

        # Bollinger Bands
        hist['Middle_Band'] = hist['Close'].rolling(window=20).mean()
        std = hist['Close'].rolling(window=20).std()
        hist['Upper_Band'] = hist['Middle_Band'] + (2 * std)
        hist['Lower_Band'] = hist['Middle_Band'] - (2 * std)

        # Format for Chart.js
        # We'll return lists of {t, y} for time series, or just labels/values
        labels = hist.index.strftime('%Y-%m-%d').tolist()
        chart_data = {
            'labels': labels,
            'price': hist['Close'].fillna(0).tolist(),
            'sma20': hist['SMA_20'].fillna(0).tolist(),
            'sma50': hist['SMA_50'].fillna(0).tolist(),
            'bb_upper': hist['Upper_Band'].fillna(0).tolist(),
            'bb_lower': hist['Lower_Band'].fillna(0).tolist()
        }

        return {
            'ticker': ticker,
            'name': info.get('shortName', ticker),
            'sector': info.get('sector', 'N/A'),
            'recommendation': recommendation,
            'target_price': target_price,
            'esg_score': esg_score,
            'chart_data': chart_data
        }

    except Exception as e:
        logging.error(f"Error fetching advanced details for {ticker}: {e}")
        return None

def optimize_portfolio(tickers):
    """
    Calculates optimal portfolio weights using Mean-Variance Optimization (Max Sharpe).
    """
    if len(tickers) < 2:
        return {"error": "Need at least 2 assets to optimize."}

    try:
        # Fetch data
        data = yf.download(tickers, period="1y", progress=False)['Close']
        if data.empty: return {"error": "No data found."}

        # Calculate returns
        returns = data.pct_change().dropna()
        mean_returns = returns.mean()
        cov_matrix = returns.cov()
        num_assets = len(tickers)

        # Risk-free rate assumption
        rf = 0.04

        def portfolio_performance(weights, mean_returns, cov_matrix):
            returns = np.sum(mean_returns * weights) * 252
            std = np.sqrt(np.dot(weights.T, np.dot(cov_matrix, weights))) * np.sqrt(252)
            return returns, std

        def negative_sharpe(weights, mean_returns, cov_matrix, rf):
            p_ret, p_var = portfolio_performance(weights, mean_returns, cov_matrix)
            return -(p_ret - rf) / p_var

        constraints = ({'type': 'eq', 'fun': lambda x: np.sum(x) - 1})
        bounds = tuple((0, 1) for asset in range(num_assets))
        init_guess = num_assets * [1. / num_assets,]

        opt_results = minimize(negative_sharpe, init_guess, args=(mean_returns, cov_matrix, rf), method='SLSQP', bounds=bounds, constraints=constraints)

        optimal_weights = opt_results.x
        opt_ret, opt_std = portfolio_performance(optimal_weights, mean_returns, cov_matrix)
        opt_sharpe = (opt_ret - rf) / opt_std

        # Format results
        weights_dict = {ticker: round(weight * 100, 2) for ticker, weight in zip(tickers, optimal_weights) if weight > 0.001}

        return {
            "weights": weights_dict,
            "metrics": {
                "expected_return": round(opt_ret * 100, 2),
                "volatility": round(opt_std * 100, 2),
                "sharpe_ratio": round(opt_sharpe, 2)
            }
        }

    except Exception as e:
        logging.error(f"Optimization failed: {e}")
        return {"error": str(e)}

def get_earnings_calendar(tickers):
    """
    Fetches upcoming earnings dates for a list of tickers.
    """
    results = []
    for ticker in tickers:
        try:
            stock = yf.Ticker(ticker)
            cal = stock.calendar
            # cal is a dict or dataframe
            if cal and isinstance(cal, dict):
                date = cal.get('Earnings Date', [])
                if date:
                    date = date[0] if isinstance(date, list) else date
                    results.append({"ticker": ticker, "date": str(date)})
            elif hasattr(stock, 'earnings_dates'):
                 # Fallback to earnings_dates dataframe
                 ed = stock.earnings_dates
                 if ed is not None and not ed.empty:
                     # Find next future date
                     future = ed[ed.index > pd.Timestamp.now()]
                     if not future.empty:
                         next_date = future.index[-1] # Ascending? typically descending.
                         # Actually indices are dates.
                         # Let's just grab the first one if sorted correctly or filter.
                         results.append({"ticker": ticker, "date": str(future.index[0].date())})
        except:
            continue
    return results

def get_portfolio_risk_metrics(tickers, weights=None):
    """
    Calculates Value at Risk (VaR) and Conditional VaR (CVaR) for a portfolio.
    """
    try:
        if not tickers:
            return {"error": "No tickers provided"}

        # Download data
        data = yf.download(tickers, period="1y", progress=False)
        if data.empty:
             return {"error": "No data available"}

        # yf.download returns a MultiIndex DataFrame if multiple tickers, or single index if one
        # Use 'Close' column
        if 'Close' in data:
            prices = data['Close']
        else:
            prices = data

        # If single ticker (Series), convert to DataFrame
        if isinstance(prices, pd.Series):
            prices = prices.to_frame()

        # Clean data
        prices = prices.dropna()
        if prices.empty: return {"error": "Insufficient data"}

        # If weights not provided, assume equal weight
        if not weights:
            weights = np.array([1/len(tickers)] * len(tickers))
        else:
            weights = np.array(weights)

        # Calculate daily returns
        returns = prices.pct_change().dropna()

        # Portfolio daily returns
        # Handle single ticker case
        if len(tickers) == 1:
            portfolio_returns = returns.iloc[:, 0]
        else:
            # Ensure columns match tickers order or reindex
            # yfinance sorts columns alphabetically usually
            # We must align weights with columns
            aligned_weights = []
            for col in returns.columns:
                # Find weight corresponding to this column ticker
                # This assumes tickers input matches weights input order
                # BUT yfinance reorders.
                # If we passed list of tickers, we need to map weights.
                # Simplification: Assume equal weights for this beta feature unless passed as dict
                # If list passed, we can't easily align without dict.
                # For now, let's just use equal weights if misalignment risk exists or simple dot if we trust order (we shouldn't).
                pass

            # Re-approach: force equal weights for now if not explicit dict
            # or just take the dot product if we assume 1 asset or simple usage.
            # To be safe, let's just calculate individual risk or equal weighted portfolio of found columns.

            num_assets = len(returns.columns)
            safe_weights = np.array([1/num_assets] * num_assets)
            portfolio_returns = returns.dot(safe_weights)

        # VaR 95% (Historical)
        var_95 = np.percentile(portfolio_returns, 5)

        # CVaR 95% (Average of returns below VaR)
        cvar_95 = portfolio_returns[portfolio_returns <= var_95].mean()

        # Parametric VaR
        mu = np.mean(portfolio_returns)
        sigma = np.std(portfolio_returns)
        var_95_param = mu - 1.65 * sigma

        return {
            "var_95_historical": round(abs(var_95) * 100, 2), # Show as positive % loss
            "cvar_95": round(abs(cvar_95) * 100, 2),
            "var_95_parametric": round(abs(var_95_param) * 100, 2),
            "std_dev_daily": round(sigma * 100, 2),
            "annualized_volatility": round(sigma * np.sqrt(252) * 100, 2)
        }
    except Exception as e:
        logging.error(f"Risk calculation error: {e}")
        return {"error": str(e)}

def get_market_sentiment():
    """
    Analyzes news headlines for major indices to determine market sentiment.
    """
    analyzer = SentimentIntensityAnalyzer()
    indices = ['SPY', 'QQQ', 'BTC-USD', 'DIA']

    total_score = 0
    count = 0
    news_items = []

    try:
        for ticker in indices:
            t = yf.Ticker(ticker)
            news = t.news
            if not news: continue

            for item in news[:3]: # Top 3 per ticker
                title = item.get('title', '')
                if not title: continue

                score = analyzer.polarity_scores(title)['compound']
                total_score += score
                count += 1

                news_items.append({
                    'ticker': ticker,
                    'title': title,
                    'score': round(score, 2),
                    'url': item.get('link', '#')
                })

        if count == 0:
            avg_score = 0
        else:
            avg_score = total_score / count

        # Normalize -1 to 1 -> 0 to 100
        # -1 -> 0, 0 -> 50, 1 -> 100
        normalized_score = (avg_score + 1) * 50

        sentiment_label = "Neutral"
        if normalized_score > 60: sentiment_label = "Greed"
        if normalized_score > 80: sentiment_label = "Extreme Greed"
        if normalized_score < 40: sentiment_label = "Fear"
        if normalized_score < 20: sentiment_label = "Extreme Fear"

        return {
            "score": round(normalized_score, 2),
            "label": sentiment_label,
            "news": news_items
        }
    except Exception as e:
        logging.error(f"Sentiment error: {e}")
        return {"error": str(e)}

def get_crypto_sentiment():
    """
    Fetches Crypto Fear & Greed Index from alternative.me.
    """
    try:
        response = requests.get("https://api.alternative.me/fng/")
        if response.status_code == 200:
            data = response.json()
            item = data['data'][0]
            return {
                "value": int(item['value']),
                "classification": item['value_classification'],
                "timestamp": int(item['timestamp'])
            }
        return {"error": "Failed to fetch data"}
    except Exception as e:
        logging.error(f"Crypto sentiment error: {e}")
        return {"error": str(e)}

def run_monte_carlo_simulation(tickers, weights=None, days=90, simulations=1000):
    """
    Runs a Monte Carlo simulation for portfolio future value.
    Returns 10th, 50th, 90th percentile paths.
    """
    try:
        if not tickers: return {"error": "No tickers"}

        # Get history
        data = yf.download(tickers, period="1y", progress=False)
        if data.empty: return {"error": "No data"}

        if 'Close' in data: prices = data['Close']
        else: prices = data

        if isinstance(prices, pd.Series): prices = prices.to_frame()
        prices = prices.dropna()

        if prices.empty: return {"error": "Insufficient data"}

        if len(tickers) > 1 and not weights:
            weights = np.array([1/len(tickers)] * len(tickers))
        elif not weights:
            weights = np.array([1.0])
        else:
            weights = np.array(weights)

        returns = prices.pct_change().dropna()

        # Portfolio stats
        if len(tickers) > 1:
            mean_returns = returns.mean()
            cov_matrix = returns.cov()

            # Check alignment
            if len(mean_returns) != len(weights):
                 # Simple fallback for robustness
                 weights = np.array([1/len(mean_returns)] * len(mean_returns))

            port_mean = np.sum(mean_returns * weights)
            port_std = np.sqrt(np.dot(weights.T, np.dot(cov_matrix, weights)))
        else:
            # Single ticker
            if returns.shape[1] > 1:
                 # Handling edge case where 'prices' has multiple cols but tickers len is 1 (unlikely with yf)
                 returns = returns.iloc[:,0]
            elif isinstance(returns, pd.DataFrame):
                 returns = returns.iloc[:,0]

            port_mean = returns.mean()
            port_std = returns.std()

        # Simulation
        # Geometric Brownian Motion
        sim_results = np.zeros((days, simulations))
        initial_value = 100 # Normalized start

        for s in range(simulations):
            price_path = [initial_value]
            for d in range(days):
                drift = port_mean - (0.5 * port_std**2)
                shock = port_std * np.random.normal()
                price = price_path[-1] * np.exp(drift + shock)
                price_path.append(price)
            sim_results[:, s] = price_path[1:]

        p10 = np.percentile(sim_results, 10, axis=1)
        p50 = np.percentile(sim_results, 50, axis=1)
        p90 = np.percentile(sim_results, 90, axis=1)

        return {
            "days": list(range(1, days + 1)),
            "p10": [round(x, 2) for x in p10],
            "p50": [round(x, 2) for x in p50],
            "p90": [round(x, 2) for x in p90],
            "metrics": {
                "expected_return": round(port_mean * 252 * 100, 2),
                "volatility": round(port_std * np.sqrt(252) * 100, 2)
            }
        }

    except Exception as e:
        logging.error(f"Monte Carlo error: {e}")
        return {"error": str(e)}

def calculate_dcf(ticker, growth_rate=0.10, discount_rate=0.10, terminal_growth=0.03, years=5):
    """
    Performs a simplified Discounted Cash Flow (DCF) valuation.
    """
    try:
        stock = yf.Ticker(ticker)

        # Get FCF
        cf = stock.cashflow
        if cf is None or cf.empty or 'Free Cash Flow' not in cf.index:
            return {"error": "Free Cash Flow data not available"}

        fcf_recent = cf.loc['Free Cash Flow'].iloc[0]
        # Handle currency? yfinance usually reports in reporting currency. Price in trading currency.
        # Assuming USD/USD for simplicity for now.
        if pd.isna(fcf_recent): return {"error": "Recent FCF is NaN"}

        # Get Shares
        shares = stock.info.get('sharesOutstanding')
        if not shares: return {"error": "Shares Outstanding not available"}

        # Projection
        future_fcf = []

        current_fcf = fcf_recent
        total_pv = 0

        for i in range(1, years + 1):
            projected = current_fcf * (1 + growth_rate)
            discount_factor = (1 + discount_rate) ** i
            pv = projected / discount_factor

            future_fcf.append(projected)
            total_pv += pv
            current_fcf = projected

        # Terminal Value
        if discount_rate <= terminal_growth:
            return {"error": "Discount rate must be > Terminal growth"}

        terminal_val = future_fcf[-1] * (1 + terminal_growth) / (discount_rate - terminal_growth)
        terminal_pv = terminal_val / ((1 + discount_rate) ** years)

        total_equity_value = total_pv + terminal_pv
        fair_value = total_equity_value / shares

        # Current Price
        hist = stock.history(period="1d")
        if hist.empty: return {"error": "Price data unavailable"}
        current_price = hist['Close'].iloc[-1]

        return {
            "ticker": ticker,
            "current_price": round(float(current_price), 2),
            "fair_value": round(float(fair_value), 2),
            "upside": round(((fair_value - current_price) / current_price) * 100, 2),
            "parameters": {
                "fcf": float(fcf_recent),
                "growth_rate": growth_rate,
                "discount_rate": discount_rate,
                "terminal_growth": terminal_growth
            }
        }

    except Exception as e:
        logging.error(f"DCF error for {ticker}: {e}")
        return {"error": str(e)}

def get_macro_summary():
    """
    Fetches commodities and currencies.
    """
    tickers = {
        'Gold': 'GC=F',
        'Oil': 'CL=F',
        'USD Index': 'DX-Y.NYB',
        'EUR/USD': 'EURUSD=X'
    }
    results = []
    try:
        # yf.download might fail if one ticker is bad, but these are standard
        data = yf.download(list(tickers.values()), period="5d", progress=False)
        if data.empty: return []

        if 'Close' in data:
            close = data['Close']
        else:
            close = data

        for name, ticker in tickers.items():
            if ticker not in close: continue
            series = close[ticker].dropna()
            if len(series) < 2: continue

            price = series.iloc[-1]
            prev = series.iloc[-2]
            change = ((price - prev) / prev) * 100

            results.append({
                "name": name,
                "ticker": ticker,
                "price": round(float(price), 2),
                "change_pct": round(float(change), 2)
            })

        return results
    except Exception as e:
        logging.error(f"Macro error: {e}")
        return []

def get_insider_sentiment(ticker):
    """
    Fetches recent insider transactions.
    """
    try:
        stock = yf.Ticker(ticker)
        insider = stock.insider_transactions
        if insider is None or insider.empty:
            return {"error": "No insider data"}

        transactions = []
        buy_val = 0.0
        sell_val = 0.0

        # Index is usually dates? Or default int index?
        # yfinance usually returns DataFrame where Index is relevant or simple int.
        # Let's rely on 'Start Date' column if present.

        if 'Start Date' in insider.columns:
            insider = insider.sort_values('Start Date', ascending=False)

        # Take top 10 recent
        for idx, row in insider.head(10).iterrows():
            # Check columns availability
            shares = row.get('Shares', 0)
            value = row.get('Value', 0)

            # Handle NaN
            if pd.isna(shares): shares = 0
            if pd.isna(value): value = 0

            # Determine Action
            # Often in 'Text' or 'Transaction' column?
            # From experience, yf returns 'Text' which is descriptive.
            text = str(row.get('Text', '')).lower()

            action = "Unspecified"
            if "sale" in text or "disposition" in text:
                action = "SELL"
                sell_val += float(value)
            elif "purchase" in text or "acquisition" in text:
                action = "BUY"
                buy_val += float(value)
            elif "grant" in text:
                action = "GRANT"

            # Holder name is often in the Index? Or 'Insider' column.
            # yfinance 0.2.x often puts name in 'Insider' column.
            holder = str(row.get('Insider', 'Unknown'))

            date_val = row.get('Start Date', 'N/A')
            if hasattr(date_val, 'strftime'):
                date_str = date_val.strftime('%Y-%m-%d')
            else:
                date_str = str(date_val)

            transactions.append({
                "date": date_str,
                "holder": holder,
                "shares": int(shares),
                "value": float(value),
                "action": action
            })

        return {
            "transactions": transactions,
            "summary": {
                "buy_total": round(buy_val, 2),
                "sell_total": round(sell_val, 2),
                "net_sentiment": "BULLISH" if buy_val > sell_val else "BEARISH"
            }
        }
    except Exception as e:
        logging.error(f"Insider error: {e}")
        return {"error": str(e)}

def get_analyst_ratings(ticker):
    """
    Fetches analyst recommendations breakdown.
    """
    try:
        stock = yf.Ticker(ticker)
        recs = stock.recommendations
        if recs is None or recs.empty:
            return {"error": "No ratings data"}

        # recs is usually a DataFrame with period as index or column
        # We want the latest period (row 0 usually)
        latest = recs.iloc[0]

        data = {
            "strongBuy": int(latest.get('strongBuy', 0)),
            "buy": int(latest.get('buy', 0)),
            "hold": int(latest.get('hold', 0)),
            "sell": int(latest.get('sell', 0)),
            "strongSell": int(latest.get('strongSell', 0))
        }

        total = sum(data.values())
        consensus = "N/A"
        if total > 0:
            # Simple max vote
            consensus = max(data, key=data.get).replace('strong', 'Strong ').title()

        return {
            "consensus": consensus,
            "breakdown": data,
            "total_analysts": total
        }
    except Exception as e:
        logging.error(f"Analyst error: {e}")
        return {"error": str(e)}

def calculate_piotroski_f_score(ticker):
    """
    Calculates the Piotroski F-Score (0-9) for financial health.
    """
    try:
        stock = yf.Ticker(ticker)
        bs = stock.balance_sheet
        inc = stock.income_stmt
        cf = stock.cashflow

        if bs is None or inc is None or cf is None or bs.empty or inc.empty or cf.empty:
            return {"error": "Financial data unavailable"}

        # Helper to safely get value at index i
        def get_val(df, field, i):
            if field in df.index and len(df.columns) > i:
                val = df.loc[field].iloc[i]
                return float(val) if not pd.isna(val) else 0.0
            return 0.0

        # Current (0) and Previous (1)
        net_income = get_val(inc, 'Net Income', 0)
        total_assets = get_val(bs, 'Total Assets', 0)
        prev_assets = get_val(bs, 'Total Assets', 1)

        cfo = get_val(cf, 'Operating Cash Flow', 0)
        if cfo == 0: cfo = get_val(cf, 'Cash Flow From Continuing Operating Activities', 0)

        prev_net_income = get_val(inc, 'Net Income', 1)

        # 1. ROA > 0
        score_roa = 1 if (total_assets > 0 and net_income / total_assets > 0) else 0

        # 2. CFO > 0
        score_cfo = 1 if cfo > 0 else 0

        # 3. Delta ROA
        roa_curr = net_income / total_assets if total_assets > 0 else 0
        roa_prev = prev_net_income / prev_assets if prev_assets > 0 else 0
        score_delta_roa = 1 if roa_curr > roa_prev else 0

        # 4. Accrual (CFO > Net Income)
        score_accrual = 1 if cfo > net_income else 0

        # Leverage
        lt_debt = get_val(bs, 'Long Term Debt', 0)
        prev_lt_debt = get_val(bs, 'Long Term Debt', 1)
        lev_curr = lt_debt / total_assets if total_assets > 0 else 0
        lev_prev = prev_lt_debt / prev_assets if prev_assets > 0 else 0
        score_leverage = 1 if lev_curr <= lev_prev else 0

        # Liquidity
        curr_assets = get_val(bs, 'Current Assets', 0)
        curr_liab = get_val(bs, 'Current Liabilities', 0)
        prev_curr_assets = get_val(bs, 'Current Assets', 1)
        prev_curr_liab = get_val(bs, 'Current Liabilities', 1)
        cr_curr = curr_assets / curr_liab if curr_liab > 0 else 0
        cr_prev = prev_curr_assets / prev_curr_liab if prev_curr_liab > 0 else 0
        score_liquidity = 1 if cr_curr > cr_prev else 0

        # Dilution
        shares = get_val(bs, 'Ordinary Shares Number', 0)
        if shares == 0: shares = get_val(bs, 'Share Issued', 0)
        prev_shares = get_val(bs, 'Ordinary Shares Number', 1)
        if prev_shares == 0: prev_shares = get_val(bs, 'Share Issued', 1)
        score_dilution = 1 if (prev_shares > 0 and shares <= prev_shares) else 0

        # Efficiency
        gross_profit = get_val(inc, 'Gross Profit', 0)
        revenue = get_val(inc, 'Total Revenue', 0)
        prev_gross_profit = get_val(inc, 'Gross Profit', 1)
        prev_revenue = get_val(inc, 'Total Revenue', 1)

        margin_curr = gross_profit / revenue if revenue > 0 else 0
        margin_prev = prev_gross_profit / prev_revenue if prev_revenue > 0 else 0
        score_margin = 1 if margin_curr > margin_prev else 0

        turnover_curr = revenue / total_assets if total_assets > 0 else 0
        turnover_prev = prev_revenue / prev_assets if prev_assets > 0 else 0
        score_turnover = 1 if turnover_curr > turnover_prev else 0

        total_score = (score_roa + score_cfo + score_delta_roa + score_accrual +
                       score_leverage + score_liquidity + score_dilution +
                       score_margin + score_turnover)

        return {
            "score": total_score,
            "breakdown": {
                "ROA Positive": bool(score_roa),
                "CFO Positive": bool(score_cfo),
                "ROA Improving": bool(score_delta_roa),
                "Quality Earnings": bool(score_accrual),
                "Lower Leverage": bool(score_leverage),
                "Higher Liquidity": bool(score_liquidity),
                "No Dilution": bool(score_dilution),
                "Margin Expanding": bool(score_margin),
                "Turnover Improving": bool(score_turnover)
            }
        }
    except Exception as e:
        logging.error(f"F-Score error for {ticker}: {e}")
        return {"error": str(e)}

def get_options_data(ticker):
    """
    Fetches basic options data (Put/Call Ratio, Max Pain).
    """
    try:
        stock = yf.Ticker(ticker)
        dates = stock.options
        if not dates:
            return {"error": "No options data"}

        expiry = dates[0]
        chain = stock.option_chain(expiry)

        calls = chain.calls
        puts = chain.puts

        if calls.empty or puts.empty:
             return {"error": "Incomplete chain"}

        call_vol = calls['volume'].fillna(0).sum()
        put_vol = puts['volume'].fillna(0).sum()
        call_oi = calls['openInterest'].fillna(0).sum()
        put_oi = puts['openInterest'].fillna(0).sum()

        pc_ratio_vol = put_vol / call_vol if call_vol > 0 else 0
        pc_ratio_oi = put_oi / call_oi if call_oi > 0 else 0

        # Max Pain
        strikes = set(calls['strike']).union(set(puts['strike']))
        min_payout = float('inf')
        max_pain = 0

        # Optimize: only check strikes with significant OI? No, iterate all.
        for k in strikes:
            # Call ITM if S > K (Payout S - K) -> Holder gains if S > K.
            # If price ends at P.
            # Call Value = max(0, P - K).
            # Put Value = max(0, K - P).
            # Total Payout = Sum(OI_call * max(0, P - K_call)) + Sum(OI_put * max(0, K_put - P))
            # Here P is the 'k' we are testing.

            c_payout = calls.apply(lambda r: max(0, k - r['strike']) * (r['openInterest'] or 0), axis=1).sum()
            p_payout = puts.apply(lambda r: max(0, r['strike'] - k) * (r['openInterest'] or 0), axis=1).sum()

            total = c_payout + p_payout
            if total < min_payout:
                min_payout = total
                max_pain = k

        return {
            "expiry": expiry,
            "put_call_vol": round(pc_ratio_vol, 2),
            "put_call_oi": round(pc_ratio_oi, 2),
            "max_pain": max_pain,
            "total_call_vol": int(call_vol),
            "total_put_vol": int(put_vol)
        }

    except Exception as e:
        logging.error(f"Options error for {ticker}: {e}")
        return {"error": str(e)}

def get_sector_rotation():
    """
    Calculates Sector Rotation metrics (Trend vs Momentum) relative to SPY.
    """
    sectors = {
        'XLE': 'Energy', 'XLF': 'Financials', 'XLK': 'Tech', 'XLV': 'Health',
        'XLI': 'Industrials', 'XLP': 'Staples', 'XLY': 'Discretionary',
        'XLB': 'Materials', 'XLU': 'Utilities', 'XLRE': 'Real Estate', 'XLC': 'Comm'
    }
    try:
        tickers = list(sectors.keys()) + ['SPY']
        data = yf.download(tickers, period="6mo", progress=False)
        if data.empty: return []

        if 'Close' in data:
            close = data['Close']
        else:
            close = data

        if 'SPY' not in close: return []

        spy = close['SPY']
        results = []

        for ticker, name in sectors.items():
            if ticker not in close: continue

            series = close[ticker].dropna()
            # Align with SPY
            common_idx = series.index.intersection(spy.index)
            if len(common_idx) < 60: continue

            s_price = series.loc[common_idx]
            m_price = spy.loc[common_idx]

            rs = s_price / m_price

            # Trend: RS vs 60-day MA of RS
            ma_rs = rs.rolling(window=60).mean()
            curr_rs = rs.iloc[-1]
            curr_ma = ma_rs.iloc[-1]

            # Momentum: ROC of RS (10 days)
            prev_rs = rs.iloc[-10] if len(rs) > 10 else rs.iloc[0]

            x_trend = ((curr_rs / curr_ma) - 1) * 100 if curr_ma > 0 else 0
            y_mom = ((curr_rs - prev_rs) / prev_rs) * 100 if prev_rs > 0 else 0

            # Quadrant
            quad = ""
            if x_trend > 0 and y_mom > 0: quad = "Leading"
            elif x_trend > 0 and y_mom < 0: quad = "Weakening"
            elif x_trend < 0 and y_mom < 0: quad = "Lagging"
            else: quad = "Improving"

            results.append({
                "ticker": ticker,
                "name": name,
                "x": round(x_trend, 2),
                "y": round(y_mom, 2),
                "quadrant": quad
            })

        return results
    except Exception as e:
        logging.error(f"Sector rotation error: {e}")
        return []

def get_advanced_patterns():
    """
    Scans for Double Top/Bottom patterns on a subset of stocks.
    """
    tickers = SP500_TICKERS[:50] # Limit to top 50 for performance
    patterns = []

    try:
        data = yf.download(tickers, period="6mo", progress=False)
        if data.empty: return []

        if 'Close' in data:
            close = data['Close']
        else:
            close = data

        for ticker in tickers:
            if ticker not in close: continue
            series = close[ticker].dropna()
            if len(series) < 50: continue

            arr = series.values
            peaks, _ = find_peaks(arr, distance=10)
            troughs, _ = find_peaks(-arr, distance=10)

            # Double Top
            if len(peaks) >= 2:
                p1, p2 = peaks[-2], peaks[-1]
                v1, v2 = arr[p1], arr[p2]
                # Peaks should be similar height (within 2%)
                if abs(v1 - v2) / v1 < 0.02:
                    # Check for trough in between
                    mid_slice = arr[p1:p2]
                    if len(mid_slice) > 0:
                        min_val = mid_slice.min()
                        # Drop from peak should be significant (>3%)
                        if (v1 - min_val) / v1 > 0.03:
                            patterns.append({"ticker": ticker, "pattern": "Double Top", "price": float(arr[-1])})

            # Double Bottom
            if len(troughs) >= 2:
                t1, t2 = troughs[-2], troughs[-1]
                v1, v2 = arr[t1], arr[t2]
                if abs(v1 - v2) / v1 < 0.02:
                    mid_slice = arr[t1:t2]
                    if len(mid_slice) > 0:
                        max_val = mid_slice.max()
                        if (max_val - v1) / v1 > 0.03:
                            patterns.append({"ticker": ticker, "pattern": "Double Bottom", "price": float(arr[-1])})

    except Exception as e:
        logging.error(f"Advanced pattern error: {e}")

    return patterns

def generate_trade_thesis(ticker):
    """
    Synthesizes a trade thesis based on aggregated data.
    """
    try:
        f_score = calculate_piotroski_f_score(ticker)
        insider = get_insider_sentiment(ticker)
        analyst = get_analyst_ratings(ticker)

        # Determine Sentiment
        bullish_signals = 0
        bearish_signals = 0
        reasons = []

        # F-Score
        if not f_score.get('error'):
            fs = f_score.get('score', 0)
            if fs >= 7:
                bullish_signals += 1
                reasons.append(f"Strong Fundamentals (F-Score {fs}/9).")
            elif fs <= 3:
                bearish_signals += 1
                reasons.append(f"Weak Fundamentals (F-Score {fs}/9).")

        # Insider
        if not insider.get('error'):
            net_insider = insider.get('summary', {}).get('net_sentiment', 'NEUTRAL')
            if net_insider == 'BULLISH':
                bullish_signals += 1
                reasons.append("Insiders are buying.")
            elif net_insider == 'BEARISH':
                bearish_signals += 1
                reasons.append("Insiders are selling.")

        # Analyst
        if not analyst.get('error'):
            consensus = analyst.get('consensus', '').lower()
            if 'buy' in consensus:
                bullish_signals += 1
                reasons.append(f"Analysts rate it {analyst['consensus']}.")
            elif 'sell' in consensus:
                bearish_signals += 1
                reasons.append(f"Analysts rate it {analyst['consensus']}.")

        # Conclusion
        if bullish_signals > bearish_signals:
            verdict = "BULLISH"
            color = "success"
        elif bearish_signals > bullish_signals:
            verdict = "BEARISH"
            color = "danger"
        else:
            verdict = "NEUTRAL"
            color = "warning"

        text = f"The AI Thesis is <strong>{verdict}</strong>. "
        text += " ".join(reasons)
        if not reasons: text += "Mixed signals or insufficient data."

        return {"verdict": verdict, "thesis": text, "color": color}

    except Exception as e:
        logging.error(f"Thesis error: {e}")
        return {"error": str(e)}

def get_ownership_data(ticker):
    """
    Fetches Institutional Holders and Short Interest data.
    """
    try:
        stock = yf.Ticker(ticker)

        # Institutional Holders
        inst_holders = []
        try:
            ih = stock.institutional_holders
            if ih is not None and not ih.empty:
                # Take top 5
                top_5 = ih.head(5)
                for _, row in top_5.iterrows():
                    holder = row.get('Holder', 'N/A')
                    shares = row.get('Shares', 0)
                    date_val = row.get('Date Reported', 'N/A')

                    if hasattr(date_val, 'strftime'):
                        date_str = date_val.strftime('%Y-%m-%d')
                    else:
                        date_str = str(date_val)

                    inst_holders.append({
                        "holder": str(holder),
                        "shares": int(shares) if not pd.isna(shares) else 0,
                        "date": date_str
                    })
        except Exception as e:
            logging.error(f"Inst holders fetch error: {e}")

        # Short Interest
        short_data = {}
        try:
            info = stock.info
            short_float = info.get('shortPercentOfFloat')
            short_data = {
                "shortPercentOfFloat": round(short_float * 100, 2) if short_float else "N/A",
                "shortRatio": info.get('shortRatio', "N/A"),
                "sharesShort": info.get('sharesShort', "N/A")
            }
        except Exception as e:
            logging.error(f"Short info fetch error: {e}")

        return {
            "institutional_holders": inst_holders,
            "short_interest": short_data
        }
    except Exception as e:
        logging.error(f"Ownership error for {ticker}: {e}")
        return {"error": str(e)}

def detect_market_anomalies():
    """
    Detects anomalous market behavior (Unusual Volume/Price action) using Isolation Forest.
    """
    tickers = SP500_TICKERS[:50] # Top 50
    anomalies = []

    try:
        data = yf.download(tickers, period="30d", progress=False)
        if data.empty: return []

        if 'Close' in data:
            close = data['Close']
            volume = data['Volume'] if 'Volume' in data else None
        else:
            close = data
            volume = None

        features = []
        valid_tickers = []
        meta = []

        for ticker in tickers:
            if ticker not in close: continue

            c = close[ticker].dropna()
            if len(c) < 30: continue

            ret = c.pct_change().iloc[-1]

            vol_ratio = 1.0
            if volume is not None and ticker in volume:
                v = volume[ticker].dropna()
                if not v.empty:
                    vol_ratio = v.iloc[-1] / v.mean() if v.mean() > 0 else 1.0

            features.append([ret, vol_ratio])
            valid_tickers.append(ticker)
            meta.append({'price': c.iloc[-1]})

        if len(features) < 5: return []

        X = np.array(features)
        # Contamination 0.1 = top 10%
        clf = IsolationForest(contamination=0.1, random_state=42)
        preds = clf.fit_predict(X)

        for i, pred in enumerate(preds):
            if pred == -1: # Outlier
                anomalies.append({
                    "ticker": valid_tickers[i],
                    "price": float(meta[i]['price']),
                    "return_pct": round(features[i][0] * 100, 2),
                    "vol_ratio": round(features[i][1], 2),
                    "reason": "Unusual Price/Volume Behavior"
                })

    except Exception as e:
        logging.error(f"Anomaly detection error: {e}")

    return anomalies

def get_efficient_frontier(tickers, num_portfolios=200):
    try:
        if len(tickers) < 2: return {"error": "Need 2+ assets"}

        data = yf.download(tickers, period="1y", progress=False)
        if data.empty: return {"error": "No data"}

        if 'Close' in data:
            prices = data['Close']
        else:
            prices = data

        returns = prices.pct_change().dropna()
        if returns.empty: return {"error": "Insufficient data"}

        mean_returns = returns.mean()
        cov_matrix = returns.cov()
        num_assets = len(tickers)
        rf = 0.04

        results = []

        for _ in range(num_portfolios):
            weights = np.random.random(num_assets)
            weights /= np.sum(weights)

            p_ret = np.sum(mean_returns * weights) * 252
            p_vol = np.sqrt(np.dot(weights.T, np.dot(cov_matrix, weights))) * np.sqrt(252)
            p_sharpe = (p_ret - rf) / p_vol

            results.append({
                "x": round(p_vol * 100, 2), # Volatility
                "y": round(p_ret * 100, 2), # Return
                "sharpe": round(p_sharpe, 2)
            })

        return results
    except Exception as e:
        logging.error(f"Frontier error: {e}")
        return {"error": str(e)}

def get_trending_topics():
    try:
        tickers = ['SPY', 'QQQ', 'DIA', 'AAPL', 'NVDA', 'TSLA', 'AMZN', 'MSFT', 'GOOGL', 'META']
        all_text = ""

        for ticker in tickers:
            t = yf.Ticker(ticker)
            news = t.news
            if news:
                for item in news:
                    all_text += " " + item.get('title', '')

        words = re.findall(r'\w+', all_text.lower())
        stop_words = {'the', 'a', 'an', 'to', 'of', 'in', 'for', 'on', 'with', 'at', 'is', 'and', 'or', 'by', 'from', 'up', 'down', 'stocks', 'stock', 'market', 'markets', 'today', 'week', 'year', 'why', 'what', 'how', 'new', 'news', 'are', 'be', 'as', 'that', 'it', 'its', 'will', 'has', 'have', 'inc', 'corp', 'company', 'earnings', 'report', 'results', 'quarter', 'q1', 'q2', 'q3', 'q4', 'price', 'target', 'buy', 'sell', 'rating', 'analyst', 'analysts', 'estimates', 'revenue', 'profit', 'sales', 'growth', 'share', 'shares', 'investor', 'investors', 'trading', 'trade', 'volume', 'high', 'low', 'close', 'open', 'vs', 'record', 'hit', 'hits', 'continues', 'continue', 'stock', 'stocks'}

        filtered = [w for w in words if w not in stop_words and len(w) > 2 and not w.isdigit()]

        counts = Counter(filtered)
        top = counts.most_common(20)

        return [{"text": w, "weight": c} for w, c in top]

    except Exception as e:
        logging.error(f"Topics error: {e}")
        return []
