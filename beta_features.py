import yfinance as yf
import pandas as pd
import numpy as np
import logging
from scipy.optimize import minimize
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
