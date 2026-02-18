import time
import yfinance as yf
import concurrent.futures

# Mock tickers
tickers_to_test = ['AAPL', 'MSFT', 'GOOG', 'AMZN', 'TSLA']

def fetch_one(ticker):
    start = time.time()
    print(f"Enriching {ticker}...")
    try:
        # Simulate what the original code does
        stock_info = yf.Ticker(ticker).info
        market_cap = stock_info.get('marketCap')
        sector = stock_info.get('sector')
        print(f"  -> Got {ticker}: {market_cap}, {sector}")
    except Exception as e:
        print(f"  -> Error {ticker}: {e}")

    # Simulate the sleep in the original code
    time.sleep(2)
    return time.time() - start

def baseline_enrichment():
    print("--- Baseline Sequential ---")
    start_total = time.time()
    for ticker in tickers_to_test:
        fetch_one(ticker)
    end_total = time.time()
    print(f"Total time baseline: {end_total - start_total:.2f}s")

if __name__ == "__main__":
    baseline_enrichment()
