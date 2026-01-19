import time
import yfinance as yf
import concurrent.futures

# Mock tickers
tickers_to_test = ['AAPL', 'MSFT', 'GOOG', 'AMZN', 'TSLA']

def fetch_one_optimized(ticker):
    print(f"Enriching {ticker}...")
    try:
        stock_info = yf.Ticker(ticker).info
        market_cap = stock_info.get('marketCap')
        sector = stock_info.get('sector')
        return (ticker, market_cap, sector)
    except Exception as e:
        print(f"  -> Error {ticker}: {e}")
        return None

def optimized_enrichment():
    print("--- Optimized Parallel ---")
    start_total = time.time()
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        future_to_ticker = {executor.submit(fetch_one_optimized, ticker): ticker for ticker in tickers_to_test}
        for future in concurrent.futures.as_completed(future_to_ticker):
            ticker = future_to_ticker[future]
            try:
                data = future.result()
                if data:
                    results.append(data)
                    print(f"  -> Got {data}")
            except Exception as e:
                print(f"  -> Exception for {ticker}: {e}")

    end_total = time.time()
    print(f"Total time optimized: {end_total - start_total:.2f}s")

if __name__ == "__main__":
    optimized_enrichment()
