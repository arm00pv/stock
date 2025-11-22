import yfinance as yf
import numpy as np
import pandas as pd
import logging
from sp500_list import SP500_TICKERS

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def get_sp500_predictions():
    """
    Generates price predictions for SP500 stocks using linear regression on 30-day history.
    Returns a list of dictionaries with ticker, current_price, predicted_price, prediction_pct.
    """
    # We use a subset of SP500 for performance in this beta
    tickers = SP500_TICKERS

    results = []
    try:
        # Batch download
        data = yf.download(tickers, period="3mo", progress=False)
        if data.empty or 'Close' not in data:
            return []

        close_prices = data['Close']

        for ticker in tickers:
            try:
                if ticker not in close_prices: continue

                series = close_prices[ticker].dropna()
                if len(series) < 30: continue

                current_price = series.iloc[-1]
                last_30 = series.iloc[-30:]

                x = np.arange(len(last_30))
                y = last_30.values
                slope, intercept = np.polyfit(x, y, 1)

                # Predict 7 days out
                prediction_7d = slope * (len(last_30) + 7) + intercept
                prediction_pct = ((prediction_7d - current_price) / current_price) * 100

                # Basic filtering: only show decent potential moves or strong trends
                # or just return all and let frontend sort
                results.append({
                    "ticker": ticker,
                    "current_price": float(current_price),
                    "predicted_price": float(prediction_7d),
                    "prediction_pct": float(prediction_pct),
                    "slope": float(slope) # Trend indicator
                })
            except Exception as e:
                logging.error(f"Prediction error for {ticker}: {e}")
                continue

        # Sort by highest positive prediction percentage
        results.sort(key=lambda x: x['prediction_pct'], reverse=True)
        return results

    except Exception as e:
        logging.error(f"Batch prediction error: {e}")
        return []
