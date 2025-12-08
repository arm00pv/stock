import yfinance as yf
import numpy as np
import pandas as pd
import logging
from sklearn.ensemble import RandomForestRegressor
from sp500_list import SP500_TICKERS

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def get_sp500_predictions():
    """
    Generates price predictions for SP500 stocks using Random Forest on 6-month history.
    Predicts 7-day future price based on SMA, Returns, and Volume.
    """
    # Limit to top 30 for performance in beta environment
    tickers = SP500_TICKERS[:30]

    results = []
    try:
        # Batch download
        data = yf.download(tickers, period="6mo", progress=False)
        if data.empty: return []

        # Handle yfinance structure
        if 'Close' in data:
            prices = data['Close']
            volume = data['Volume'] if 'Volume' in data else None
        else:
            prices = data # Fallback
            volume = None

        for ticker in tickers:
            try:
                # Check if ticker is in columns (MultiIndex or Flat)
                if ticker not in prices.columns: continue

                # Prepare DataFrame
                # Use .copy() to avoid SettingWithCopy
                df = pd.DataFrame({'Close': prices[ticker]})
                if volume is not None and ticker in volume.columns:
                    df['Vol'] = volume[ticker]
                else:
                    df['Vol'] = 0

                df.dropna(inplace=True)
                if len(df) < 50: continue

                # Feature Engineering
                df['SMA_5'] = df['Close'].rolling(window=5).mean()
                df['SMA_20'] = df['Close'].rolling(window=20).mean()
                df['Return'] = df['Close'].pct_change()

                df.dropna(inplace=True)

                # Target: Price 7 days ahead
                df['Target'] = df['Close'].shift(-7)

                # Train Data (Drop rows where Target is NaN)
                train_df = df.dropna()

                if len(train_df) < 30: continue

                X = train_df[['SMA_5', 'SMA_20', 'Return', 'Vol']]
                y = train_df['Target']

                # Train Random Forest
                # n_estimators=50 is faster than default 100, sufficient for demo
                model = RandomForestRegressor(n_estimators=50, random_state=42, n_jobs=1)
                model.fit(X, y)

                # Predict using the MOST RECENT data point (which has features but no Target yet)
                latest_row = df.iloc[[-1]]
                latest_features = latest_row[['SMA_5', 'SMA_20', 'Return', 'Vol']]

                pred_price = model.predict(latest_features)[0]
                current_price = latest_row['Close'].iloc[0]

                pct_change = ((pred_price - current_price) / current_price) * 100

                results.append({
                    "ticker": ticker,
                    "current_price": float(current_price),
                    "predicted_price": float(pred_price),
                    "prediction_pct": float(pct_change),
                    "model": "RandomForest"
                })

            except Exception as e:
                logging.error(f"Prediction error for {ticker}: {e}")
                continue

        # Sort by highest upside
        results.sort(key=lambda x: x['prediction_pct'], reverse=True)
        return results

    except Exception as e:
        logging.error(f"Batch prediction error: {e}")
        return []
