import yfinance as yf
import pandas as pd
import logging
from database import get_recently_picked_tickers

logging.basicConfig(level=logging.INFO,
                    filename='ai_picker.log',
                    filemode='a',
                    format='%(asctime)s - %(levelname)s - %(message)s')

def get_ai_recommendation(category, tickers, price_limit=None):
    """
    Provides a stock recommendation based on a more advanced scoring model.
    """
    logging.info(f"Starting AI recommendation for category: {category}")
    try:
        recent_picks = get_recently_picked_tickers(category, days=7)
        logging.info(f"Recently picked: {recent_picks}")
    except Exception as e:
        logging.error(f"Database error when fetching recent picks: {e}", exc_info=True)
        recent_picks = []

    scored_tickers = []
    for ticker in tickers:
        if ticker in recent_picks:
            logging.info(f"Skipping {ticker} as it was picked recently.")
            continue
        try:
            logging.info(f"Processing ticker: {ticker}")
            stock = yf.Ticker(ticker)
            info = stock.info
            hist = stock.history(period="3mo")

            if hist.empty:
                logging.warning(f"No history found for {ticker}")
                continue

            # Price limit check
            current_price = hist['Close'].iloc[-1]
            if price_limit and current_price > price_limit:
                logging.info(f"Skipping {ticker} due to price limit.")
                continue

            # --- Advanced Scoring ---
            score = 0

            # 1. Momentum Score (25%)
            price_change_pct = (hist['Close'].iloc[-1] - hist['Close'].iloc[-30]) / hist['Close'].iloc[-30] if len(hist) > 30 else 0
            momentum_score = price_change_pct * 100
            score += momentum_score * 0.25

            # 2. Value Score (P/E Ratio) (25%)
            pe_ratio = info.get('trailingPE', info.get('forwardPE'))
            if pe_ratio and pe_ratio > 0:
                # Lower P/E is better. We'll cap the score contribution.
                value_score = max(0, 50 - pe_ratio)
                score += value_score * 0.25

            # 3. Moving Average Score (25%)
            ma_20 = hist['Close'].rolling(window=20).mean().iloc[-1]
            ma_50 = hist['Close'].rolling(window=50).mean().iloc[-1]
            if not pd.isna(ma_20) and not pd.isna(ma_50) and ma_50 > 0:
                ma_score = (ma_20 / ma_50 - 1) * 100 # % difference
                # Give a bonus for "golden cross"
                if ma_20 > ma_50:
                    score += (ma_score * 2) * 0.25
                else:
                    score += ma_score * 0.25

            # 4. Volatility Score (lower is better) (15%)
            returns = hist['Close'].pct_change().dropna()
            volatility = returns.std() * (252**0.5) # Annualized volatility
            if not pd.isna(volatility) and volatility > 0:
                # Lower volatility gets a higher score. Capped at 25.
                volatility_score = max(0, 25 - (volatility * 50))
                score += volatility_score * 0.15

            # 5. Volume Score (10%)
            avg_volume = hist['Volume'].mean()
            volume_score = avg_volume / 1_000_000 # Simple scaling
            score += min(volume_score, 10) * 0.10 # Cap volume contribution

            if score > 0:
                scored_tickers.append((ticker, score))
                logging.info(f"Scored {ticker}: {score} (Momentum: {momentum_score:.2f}, Value: {value_score if 'value_score' in locals() else 'N/A'}, MA: {ma_score if 'ma_score' in locals() else 'N/A'}, Volatility: {volatility_score if 'volatility_score' in locals() else 'N/A'}, Volume: {volume_score:.2f})")
            else:
                logging.info(f"Skipping {ticker} due to low or negative score.")

        except Exception as e:
            logging.error(f"Could not process {ticker}: {e}", exc_info=True)
            continue

    if not scored_tickers:
        logging.warning("No suitable tickers found after scoring.")
        return tickers[0] if tickers else None

    # Sort by score descending
    scored_tickers.sort(key=lambda x: x[1], reverse=True)
    logging.info(f"Top scored ticker: {scored_tickers[0][0]}")

    return scored_tickers[0][0]
