import yfinance as yf
import logging

def get_market_status():
    """
    Fetches current market indicators: S&P 500, VIX, 10Y Treasury.
    """
    tickers = ['^GSPC', '^VIX', '^TNX']
    market_data = {}

    try:
        data = yf.download(tickers, period="5d", progress=False)
        if data.empty or 'Close' not in data:
            return {}

        close_data = data['Close']
        # Calculate change

        for ticker in tickers:
            if ticker in close_data:
                series = close_data[ticker].dropna()
                if len(series) >= 2:
                    current = series.iloc[-1]
                    prev = series.iloc[-2]
                    change = current - prev
                    change_pct = (change / prev) * 100

                    name_map = {
                        '^GSPC': 'S&P 500',
                        '^VIX': 'Volatility (VIX)',
                        '^TNX': '10Y Treasury Yield'
                    }

                    market_data[name_map.get(ticker, ticker)] = {
                        'price': float(current),
                        'change': float(change),
                        'change_pct': float(change_pct)
                    }
    except Exception as e:
        logging.error(f"Error fetching market status: {e}")

    return market_data
