import os
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
import logging
import requests

logging.basicConfig(level=logging.INFO,
                    filename='backtesting.log',
                    filemode='a',
                    format='%(asctime)s - %(levelname)s - %(message)s')

sentiment_cache = {}

def get_historical_news_sentiment(date_str, tickers):
    if date_str in sentiment_cache:
        return sentiment_cache[date_str]
    api_token = os.environ.get('MARKETAUX_API_KEY')
    if not api_token: return {ticker: 0 for ticker in tickers}

    scores = {ticker: 0 for ticker in tickers}
    try:
        params = {'api_token': api_token, 'symbols': ",".join(tickers), 'published_on': date_str, 'limit': 50}
        response = requests.get("https://api.marketaux.com/v1/news/all", params=params)
        response.raise_for_status()
        data = response.json().get('data', [])

        sentiment_sums = {ticker: 0 for ticker in tickers}
        article_counts = {ticker: 0 for ticker in tickers}

        for article in data:
            for entity in article.get('entities', []):
                ticker = entity.get('symbol')
                if ticker in tickers:
                    sentiment_sums[ticker] += entity.get('sentiment_score', 0)
                    article_counts[ticker] += 1

        for ticker in tickers:
            if article_counts[ticker] > 0:
                scores[ticker] = sentiment_sums[ticker] / article_counts[ticker]

    except requests.exceptions.RequestException as e:
        logging.error(f"Could not fetch news for {date_str}: {e}")

    sentiment_cache[date_str] = scores
    return scores

def get_historical_recommendation(current_date, hist_data, tickers, sentiment_scores):
    scored_tickers = []

    for ticker in tickers:
        try:
            ticker_hist = hist_data[hist_data.index < current_date]
            if len(ticker_hist) < 51: continue

            close_prices = ticker_hist[('Close', ticker)]
            volume = ticker_hist[('Volume', ticker)]

            if close_prices.isna().all(): continue

            score = 0

            price_change_pct = (close_prices.iloc[-1] - close_prices.iloc[-30]) / close_prices.iloc[-30] if len(close_prices) > 30 else 0
            score += (price_change_pct * 100) * 0.20

            ma_20 = close_prices.rolling(window=20).mean().iloc[-1]
            ma_50 = close_prices.rolling(window=50).mean().iloc[-1]
            if not pd.isna(ma_20) and not pd.isna(ma_50) and ma_50 > 0:
                ma_score = (ma_20 / ma_50 - 1) * 100
                score += (ma_score * 2 if ma_20 > ma_50 else ma_score) * 0.20

            returns = close_prices.pct_change().dropna()
            volatility = returns.tail(30).std() * (252**0.5)
            if not pd.isna(volatility) and volatility > 0:
                score += max(0, 25 - (volatility * 50)) * 0.15

            avg_volume = volume.tail(30).mean()
            score += min(avg_volume / 1_000_000, 10) * 0.05

            sentiment_score = sentiment_scores.get(ticker, 0)
            score += (sentiment_score * 20) * 0.40

            if score > 0:
                scored_tickers.append((ticker, score))

        except Exception as e:
            logging.warning(f"Could not score {ticker} on {current_date}: {e}")
            continue

    if not scored_tickers: return tickers[0] if tickers else None
    return sorted(scored_tickers, key=lambda x: x[1], reverse=True)[0][0]

def get_technical_recommendation(current_date, hist_data, tickers, strategy='ma_crossover'):
    scored_tickers = []

    for ticker in tickers:
        try:
            ticker_hist = hist_data[hist_data.index < current_date]
            # Need enough data for indicators
            if len(ticker_hist) < 60: continue

            close = ticker_hist[('Close', ticker)]
            if close.isna().all(): continue

            score = 0
            current_price = close.iloc[-1]

            if strategy == 'rsi_reversal':
                # RSI calculation
                delta = close.diff()
                gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
                rs = gain / loss
                rsi = 100 - (100 / (1 + rs))

                current_rsi = rsi.iloc[-1]
                # Buy if RSI < 30 (Oversold)
                if not pd.isna(current_rsi) and current_rsi < 30:
                    score = 100 + (30 - current_rsi) # Higher score for lower RSI

            elif strategy == 'macd_trend':
                # MACD calculation
                exp1 = close.ewm(span=12, adjust=False).mean()
                exp2 = close.ewm(span=26, adjust=False).mean()
                macd = exp1 - exp2
                signal = macd.ewm(span=9, adjust=False).mean()

                # Buy if MACD crosses above Signal
                if macd.iloc[-1] > signal.iloc[-1] and macd.iloc[-2] <= signal.iloc[-2]:
                    score = 100

            else: # Default 'ma_crossover' (or similar basic logic)
                # Reusing part of the original logic but simpler for this mode
                # Buy if 20MA > 50MA
                ma_20 = close.rolling(window=20).mean().iloc[-1]
                ma_50 = close.rolling(window=50).mean().iloc[-1]
                if ma_20 > ma_50:
                    score = 50

            if score > 0:
                scored_tickers.append((ticker, score))

        except Exception as e:
            continue

    if not scored_tickers: return None
    return sorted(scored_tickers, key=lambda x: x[1], reverse=True)[0][0]

from cache import yf_download_cached

def run_backtest(start_date_str, end_date_str, initial_capital, investment_amount, category, tickers, short_ma, long_ma, strategy='ai_score'):
    logging.info(f"Starting backtest for {category} from {start_date_str} to {end_date_str} with strategy {strategy}")

    start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
    end_date = datetime.strptime(end_date_str, '%Y-%m-%d')

    fetch_start_date = start_date - timedelta(days=max(100, long_ma))
    try:
        hist_data = yf_download_cached(tickers, start=fetch_start_date, end=end_date, progress=False)
        if hist_data.empty or 'Close' not in hist_data:
            return {"error": "Could not download valid historical data."}
    except Exception as e:
        return {"error": f"Failed to download historical data: {e}"}

    cash = float(initial_capital)
    holdings = {ticker: 0.0 for ticker in tickers}
    portfolio_history = []

    for day in pd.date_range(start=start_date, end=end_date, freq='B'):
        if day not in hist_data.index:
            if portfolio_history:
                portfolio_history.append({'date': day.strftime('%Y-%m-%d'), 'total_value': portfolio_history[-1]['total_value']})
            continue

        day_str = day.strftime('%Y-%m-%d')

        day_hist_data = hist_data[hist_data.index < day]
        recommended_ticker = None

        if strategy == 'ai_score':
            sentiment_scores = get_historical_news_sentiment(day_str, tickers)
            recommended_ticker = get_historical_recommendation(day, day_hist_data, tickers, sentiment_scores)
        else:
            recommended_ticker = get_technical_recommendation(day, day_hist_data, tickers, strategy)

        if recommended_ticker:
            try:
                price = hist_data.loc[day, ('Open', recommended_ticker)]
                if not pd.isna(price) and price > 0 and cash >= investment_amount:
                    shares_to_buy = investment_amount / price
                    holdings[recommended_ticker] += shares_to_buy
                    cash -= investment_amount
            except KeyError: pass

        current_holdings_value = sum(holdings[ticker] * hist_data.loc[day, ('Close', ticker)] for ticker in tickers if not pd.isna(hist_data.loc[day, ('Close', ticker)]))
        total_value = cash + current_holdings_value
        portfolio_history.append({'date': day.strftime('%Y-%m-%d'), 'total_value': total_value})

    portfolio_df = pd.DataFrame(portfolio_history).set_index('date')
    portfolio_df.index = pd.to_datetime(portfolio_df.index)

    short_ma_series = portfolio_df['total_value'].rolling(window=short_ma).mean()
    long_ma_series = portfolio_df['total_value'].rolling(window=long_ma).mean()

    final_value = portfolio_history[-1]['total_value'] if portfolio_history else initial_capital
    total_return_pct = ((final_value - initial_capital) / initial_capital) * 100 if initial_capital > 0 else 0

    logging.info(f"Backtest complete. Final value: ${final_value:.2f}, Total return: {total_return_pct:.2f}%")

    return {
        "status": "success",
        "start_date": start_date_str,
        "end_date": end_date_str,
        "initial_capital": initial_capital,
        "final_value": final_value,
        "total_return_pct": total_return_pct,
        "portfolio_history": portfolio_history,
        "short_ma": short_ma_series.dropna().tolist(),
        "long_ma": long_ma_series.dropna().tolist()
    }