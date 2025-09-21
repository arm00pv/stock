import ai_picker

print("Testing get_ai_recommendation...")
tickers = ['AAPL', 'MSFT', 'GOOG']
try:
    ticker = ai_picker.get_ai_recommendation('hot_stock', tickers)
    print(f"Ticker found: {ticker}")
except Exception as e:
    print(f"An error occurred: {e}")

print("Test complete.")
