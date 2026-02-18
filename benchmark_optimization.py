import time
import unittest.mock as mock
import database

# Mock setup
class MockCursor:
    def __init__(self):
        self.executed = []

    def execute(self, query, params=None):
        # Simulate query execution latency
        time.sleep(0.001)
        self.executed.append((query, params))

    def executemany(self, query, params_list):
        # Simulate batch query execution latency (slightly longer than single but much faster than N single queries)
        time.sleep(0.005)
        self.executed.append((query, params_list))

    def close(self):
        pass

    def fetchall(self):
        return []

class MockConnection:
    def __init__(self):
        # Simulate connection establishment latency
        time.sleep(0.01)
        self.cursor_mock = MockCursor()

    def cursor(self):
        return self.cursor_mock

    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        pass

def mock_connect(**kwargs):
    return MockConnection()

# Patch database.mysql.connector.connect
patcher = mock.patch('database.mysql.connector.connect', side_effect=mock_connect)
patcher.start()

# Helper to generate tickers
tickers = [f"TICK{i}" for i in range(100)]
ticker_sentiments = {t: -0.5 for t in tickers} # All negative to trigger updates

def original_logic(tickers, ticker_sentiments):
    print(f"Processing {len(tickers)} tickers with ORIGINAL logic...")
    start_time = time.time()
    for ticker in tickers:
        average_sentiment = ticker_sentiments.get(ticker)
        if average_sentiment is None:
            database.set_sell_flag(ticker, False)
            continue

        if average_sentiment < -0.2:
            database.set_sell_flag(ticker, True)
        else:
            database.set_sell_flag(ticker, False)

    end_time = time.time()
    duration = end_time - start_time
    print(f"Original logic took: {duration:.4f} seconds")
    return duration

def optimized_logic(tickers, ticker_sentiments):
    print(f"Processing {len(tickers)} tickers with OPTIMIZED logic...")
    start_time = time.time()
    updates = []
    for ticker in tickers:
        average_sentiment = ticker_sentiments.get(ticker)
        if average_sentiment is None:
            updates.append((ticker, False))
            continue

        if average_sentiment < -0.2:
            updates.append((ticker, True))
        else:
            updates.append((ticker, False))

    if updates:
        database.set_sell_flags_batch(updates)

    end_time = time.time()
    duration = end_time - start_time
    print(f"Optimized logic took: {duration:.4f} seconds")
    return duration

if __name__ == "__main__":
    try:
        original_duration = original_logic(tickers, ticker_sentiments)
        optimized_duration = optimized_logic(tickers, ticker_sentiments)

        improvement = original_duration / optimized_duration if optimized_duration > 0 else 0
        print(f"Improvement: {improvement:.2f}x faster")

    finally:
        patcher.stop()
