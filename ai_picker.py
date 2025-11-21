import os
import yfinance as yf
import pandas as pd
import logging
import requests
import numpy as np
from database import get_recently_picked_tickers, get_ai_settings

logging.basicConfig(level=logging.INFO,
                    filename='ai_picker.log',
                    filemode='a',
                    format='%(asctime)s - %(levelname)s - %(message)s')

def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def calculate_macd(series, fast=12, slow=26, signal=9):
    exp1 = series.ewm(span=fast, adjust=False).mean()
    exp2 = series.ewm(span=slow, adjust=False).mean()
    macd = exp1 - exp2
    signal_line = macd.ewm(span=signal, adjust=False).mean()
    return macd, signal_line

def get_news_sentiment(tickers):
    """
    Fetches news sentiment for a list of tickers from the Marketaux API.
    """
    api_token = os.environ.get('MARKETAUX_API_KEY')
    if not api_token:
        logging.warning("Marketaux API key not found. Skipping sentiment analysis.")
        return {}

    sentiment_scores = {}
    for ticker in tickers:
        try:
            params = {
                'api_token': api_token,
                'symbols': ticker,
                'limit': 5,
                'language': 'en',
            }
            response = requests.get("https://api.marketaux.com/v1/news/all", params=params)
            response.raise_for_status()
            data = response.json()

            if not data.get('data'):
                sentiment_scores[ticker] = 0
                continue

            total_sentiment = sum(entity.get('sentiment_score', 0) for article in data['data'] for entity in article.get('entities', []) if entity.get('symbol') == ticker)
            article_count = sum(1 for article in data['data'] for entity in article.get('entities', []) if entity.get('symbol') == ticker)

            sentiment_scores[ticker] = total_sentiment / article_count if article_count > 0 else 0

        except requests.exceptions.RequestException as e:
            logging.error(f"Could not fetch news for {ticker}: {e}")
            sentiment_scores[ticker] = 0

    return sentiment_scores

def get_ai_recommendation(category, tickers, price_limit=None, return_score=False):
    """
    Provides a stock recommendation based on a customizable, advanced scoring model.
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
        recent_picks = []

    sentiment_scores = get_news_sentiment(tickers)
    scored_tickers = []

    for ticker in tickers:
        if ticker in recent_picks and len(tickers) > 1: # Only skip if we have other options
            continue
        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            hist = stock.history(period="6mo")

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

            # Technical Indicators
            rsi = calculate_rsi(hist['Close']).iloc[-1]
            if not pd.isna(rsi):
                 # RSI < 30 is oversold (good buy), > 70 is overbought.
                 # Score higher for oversold conditions in a "picking" context, unless momentum is key.
                 # Let's treat RSI 40-60 as neutral, <40 as bullish (buy dip), >70 as bearish?
                 # Actually, for a simple score: if RSI < 30, add points.
                 if rsi < 30: score += 5
                 elif rsi < 70: score += 2

            macd, signal = calculate_macd(hist['Close'])
            if not pd.isna(macd.iloc[-1]) and not pd.isna(signal.iloc[-1]):
                if macd.iloc[-1] > signal.iloc[-1]:
                    score += 5 # Bullish crossover

            sentiment_score = sentiment_scores.get(ticker, 0)
            score += (sentiment_score * 20) * float(settings['sentiment_weight'])

            scored_tickers.append((ticker, score))

        except Exception as e:
            logging.error(f"Could not process {ticker}: {e}", exc_info=True)
            continue

    if not scored_tickers:
        logging.warning("No suitable tickers found after scoring.")
        return (tickers[0], 0) if tickers else (None, 0)

    scored_tickers.sort(key=lambda x: x[1], reverse=True)
    top_ticker, top_score = scored_tickers[0]
    logging.info(f"Top scored ticker: {top_ticker} with score {top_score}")

    return (top_ticker, top_score) if return_score else top_ticker

def get_ai_recommendation_score(category, ticker):
    """
    Returns the AI score for a single ticker.
    """
    _, score = get_ai_recommendation(category, [ticker], return_score=True)
    return score

def get_stock_analysis(ticker):
    """
    Returns a detailed analysis breakdown for a ticker.
    """
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period="6mo")
        if hist.empty: return None

        info = stock.info
        current_price = hist['Close'].iloc[-1]

        # Calculations
        momentum_score = ((current_price - hist['Close'].iloc[-30]) / hist['Close'].iloc[-30]) * 100 if len(hist) > 30 else 0

        pe_ratio = info.get('trailingPE', info.get('forwardPE'))
        value_score = 50 - pe_ratio if pe_ratio and pe_ratio > 0 else 0

        returns = hist['Close'].pct_change().dropna()
        volatility = returns.std() * (252**0.5)
        volatility_score = 25 - (volatility * 50)

        rsi = calculate_rsi(hist['Close']).iloc[-1]
        macd, signal = calculate_macd(hist['Close'])
        macd_val = macd.iloc[-1]
        signal_val = signal.iloc[-1]

        sentiment_scores = get_news_sentiment([ticker])
        sentiment_val = sentiment_scores.get(ticker, 0)

        # Generate Text Summary
        summary = f"Analysis for {ticker}:\n"
        summary += f"- Momentum: {'Positive' if momentum_score > 0 else 'Negative'} ({momentum_score:.2f}% 30-day change).\n"
        if pe_ratio:
            summary += f"- Valuation: P/E Ratio is {pe_ratio:.2f}. {'Undervalued' if pe_ratio < 15 else 'Overvalued' if pe_ratio > 25 else 'Fair value'}.\n"
        summary += f"- Volatility: Annualized volatility is {volatility:.2f}. {'High' if volatility > 0.5 else 'Low'}.\n"
        summary += f"- RSI: {rsi:.2f} ({'Oversold' if rsi < 30 else 'Overbought' if rsi > 70 else 'Neutral'}).\n"
        summary += f"- MACD: {'Bullish' if macd_val > signal_val else 'Bearish'} trend.\n"
        summary += f"- Sentiment: Score is {sentiment_val:.2f}.\n"

        # Normalize scores for radar chart (0-100 scale approximation)
        metrics = {
            "Momentum": min(max(50 + momentum_score, 0), 100),
            "Value": min(max(value_score + 50, 0), 100), # Pivot around 50
            "Volatility": min(max(volatility_score + 50, 0), 100), # Higher score = Lower Volatility (better)
            "RSI": rsi if not pd.isna(rsi) else 50,
            "Sentiment": min(max(50 + (sentiment_val * 50), 0), 100),
            "MACD_Strength": min(max(50 + (macd_val - signal_val)*10, 0), 100)
        }

        return {
            "ticker": ticker,
            "metrics": metrics,
            "summary": summary,
            "price": current_price
        }

    except Exception as e:
        logging.error(f"Error generating analysis for {ticker}: {e}")
        return None
