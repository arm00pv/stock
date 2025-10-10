import os
import yfinance as yf
import pandas as pd
import logging
import requests
from database import get_recently_picked_tickers, get_ai_settings

logging.basicConfig(level=logging.INFO,
                    filename='ai_picker.log',
                    filemode='a',
                    format='%(asctime)s - %(levelname)s - %(message)s')

def get_news_sentiment(tickers):
    """
    Fetches news sentiment for a list of tickers from the Marketaux API in a single call.
    """
    api_token = os.environ.get('MARKETAUX_API_KEY')
    if not api_token or not tickers:
        logging.warning("Marketaux API key not found or no tickers provided. Skipping sentiment analysis.")
        return {ticker: 0 for ticker in tickers}

    try:
        params = {
            'api_token': api_token,
            'symbols': ','.join(tickers),
            'limit': 100,
            'language': 'en',
            'filter_entities': 'true'
        }
        response = requests.get("https://api.marketaux.com/v1/news/all", params=params)
        response.raise_for_status()
        data = response.json()

        sentiments = {ticker: [] for ticker in tickers}
        if data.get('data'):
            for article in data['data']:
                for entity in article.get('entities', []):
                    ticker = entity.get('symbol')
                    if ticker in sentiments:
                        sentiments[ticker].append(entity.get('sentiment_score', 0))

        return {
            ticker: sum(scores) / len(scores) if scores else 0
            for ticker, scores in sentiments.items()
        }

    except requests.exceptions.RequestException as e:
        logging.error(f"Could not fetch news for tickers {','.join(tickers)}: {e}")
        return {ticker: 0 for ticker in tickers}

def get_ai_recommendation(category, tickers, price_limit=None):
    """
    Provides a stock recommendation based on a customizable, advanced scoring model with improved fallback logic.
    """
    logging.info(f"Starting AI recommendation for category: {category}")

    settings = get_ai_settings(category)
    if not settings:
        logging.warning(f"No AI settings found for category {category}. Using default weights.")
        settings = {
            'momentum_weight': 0.20, 'value_weight': 0.20, 'ma_weight': 0.20,
            'volatility_weight': 0.15, 'volume_weight': 0.05, 'sentiment_weight': 0.20
        }

    try:
        recent_picks = get_recently_picked_tickers(category, days=7)
    except Exception as e:
        logging.error(f"Database error when fetching recent picks: {e}", exc_info=True)
        recent_picks = set()

    sentiment_scores = get_news_sentiment(tickers)
    all_scored_tickers = []

    for ticker in tickers:
        if ticker in recent_picks:
            continue
        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            hist = stock.history(period="3mo")

            if hist.empty: continue

            current_price = hist['Close'].iloc[-1]
            if price_limit and current_price > price_limit: continue

            score = 0
            price_change_pct = (hist['Close'].iloc[-1] - hist['Close'].iloc[-30]) / hist['Close'].iloc[-30] if len(hist) > 30 else 0
            score += (price_change_pct * 100) * float(settings['momentum_weight'])

            pe_ratio = info.get('trailingPE', info.get('forwardPE'))
            if pe_ratio and pe_ratio > 0:
                score += max(0, 50 - pe_ratio) * float(settings['value_weight'])

            ma_20 = hist['Close'].rolling(window=20).mean().iloc[-1]
            ma_50 = hist['Close'].rolling(window=50).mean().iloc[-1]
            if not pd.isna(ma_20) and not pd.isna(ma_50) and ma_50 > 0:
                ma_score = (ma_20 / ma_50 - 1) * 100
                score += (ma_score * 2 if ma_20 > ma_50 else ma_score) * float(settings['ma_weight'])

            returns = hist['Close'].pct_change().dropna()
            volatility = returns.std() * (252**0.5)
            if not pd.isna(volatility) and volatility > 0:
                score += max(0, 25 - (volatility * 50)) * float(settings['volatility_weight'])

            avg_volume = hist['Volume'].mean()
            score += min(avg_volume / 1_000_000, 10) * float(settings['volume_weight'])

            sentiment_score = sentiment_scores.get(ticker, 0)
            score += (sentiment_score * 20) * float(settings['sentiment_weight'])

            all_scored_tickers.append((ticker, score))

        except Exception as e:
            logging.error(f"Could not process {ticker}: {e}", exc_info=True)
            continue

    positive_scored_tickers = [t for t in all_scored_tickers if t[1] > 0]

    if positive_scored_tickers:
        positive_scored_tickers.sort(key=lambda x: x[1], reverse=True)
        top_ticker = positive_scored_tickers[0][0]
        logging.info(f"Top scored ticker with positive score: {top_ticker}")
        return top_ticker

    if all_scored_tickers:
        all_scored_tickers.sort(key=lambda x: x[1], reverse=True)
        top_ticker = all_scored_tickers[0][0]
        logging.warning(f"No tickers with positive score. Falling back to highest scored ticker: {top_ticker}")
        return top_ticker

    logging.warning("No suitable tickers found after scoring. All available tickers might have been recently picked.")
    return None