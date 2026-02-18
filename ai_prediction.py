import pandas as pd
import numpy as np
import yfinance as yf
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import train_test_split
from datetime import datetime, timedelta

class StockPredictor:
    def __init__(self):
        self.model = RandomForestRegressor(n_estimators=100, random_state=42)
        self.days_to_predict = 7
        self.cache = {}
        self.cache_ttl = 3600 # 1 hour

    def fetch_data(self, ticker, months=6):
        end_date = datetime.now()
        start_date = end_date - timedelta(days=months*30 + 30) # Extra buffer for technicals
        try:
            df = yf.download(ticker, start=start_date, end=end_date, progress=False)
            if df.empty:
                return None
            return df
        except Exception as e:
            print(f"Error fetching data for {ticker}: {e}")
            return None

    def prepare_features(self, df):
        if df is None or len(df) < 50:
            return None

        df = df.copy()
        # Ensure we are working with single-level columns if MultiIndex (common in newer yfinance)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        # Technical Indicators
        df['SMA_10'] = df['Close'].rolling(window=10).mean()
        df['SMA_50'] = df['Close'].rolling(window=50).mean()
        df['Returns'] = df['Close'].pct_change()
        df['Volume_Change'] = df['Volume'].pct_change()

        # Target: Future Price (e.g., 7 days ahead)
        df['Target'] = df['Close'].shift(-self.days_to_predict)

        df.dropna(inplace=True)
        return df

    def train_and_predict(self, ticker):
        # Check cache
        if ticker in self.cache:
            val, timestamp = self.cache[ticker]
            if (datetime.now() - timestamp).total_seconds() < self.cache_ttl:
                return val

        df = self.fetch_data(ticker)
        data = self.prepare_features(df)

        if data is None or data.empty:
            return None

        features = ['SMA_10', 'SMA_50', 'Returns', 'Volume_Change', 'Close', 'Volume']
        X = data[features]
        y = data['Target']

        # Train on all available data up to the last known target
        self.model.fit(X, y)

        # Prepare the latest data point for prediction
        last_row = df.iloc[-1:].copy()

        # Recalculate features for the last row (it might have NaN Target in prepare_features but we need it for X)
        # Re-fetch or re-calc to ensure we have the inputs
        last_row['SMA_10'] = df['Close'].rolling(window=10).mean().iloc[-1]
        last_row['SMA_50'] = df['Close'].rolling(window=50).mean().iloc[-1]
        last_row['Returns'] = df['Close'].pct_change().iloc[-1]
        last_row['Volume_Change'] = df['Volume'].pct_change().iloc[-1]

        X_latest = last_row[features]

        # Handling potential NaNs if data is too short
        if X_latest.isnull().values.any():
            return None

        prediction = self.model.predict(X_latest)[0]

        # Cache result
        self.cache[ticker] = (prediction, datetime.now())

        return prediction

    def predict_sp500(self):
        # Example using SPY as proxy
        return self.train_and_predict('SPY')

if __name__ == "__main__":
    predictor = StockPredictor()
    prediction = predictor.predict_sp500()
    print(f"SPY 7-day forecast: {prediction}")
