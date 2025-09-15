import os
import requests
from collections import defaultdict
from database import get_portfolio_holdings, set_sell_flag

# --- Configuration ---
MARKETAUX_API_KEY = os.environ.get('MARKETAUX_API_KEY', 'YOUR_DEFAULT_KEY_HERE')
SENTIMENT_THRESHOLD = -0.20 # Flag a stock if average sentiment is below this
NEWS_API_URL = "https://api.marketaux.com/v1/news/all"

def get_all_portfolio_tickers():
    """Fetches all unique tickers currently held across all portfolios."""
    all_tickers = set()
    portfolio_names = ['main', 'monthly_dividend', 'daily_investment', 'high_yield_investment']
    for name in portfolio_names:
        holdings = get_portfolio_holdings(name)
        for holding in holdings:
            all_tickers.add(holding['ticker'])
    return list(all_tickers)

def run_sentiment_analysis():
    """
    Fetches news for all portfolio holdings, calculates average sentiment,
    and sets a sell_flag for stocks with consistently negative news.
    """
    print("--- Starting Sentiment Analysis Pipeline ---")

    tickers_to_check = get_all_portfolio_tickers()
    if not tickers_to_check:
        print("No holdings in any portfolio to analyze. Exiting.")
        return

    print(f"Found {len(tickers_to_check)} unique tickers to analyze: {tickers_to_check}")

    # Use a defaultdict to easily handle lists of scores
    ticker_sentiments = defaultdict(list)

    params = {
        'api_token': MARKETAUX_API_KEY,
        'symbols': ",".join(tickers_to_check),
        'limit': 100 # Get up to 100 recent articles mentioning these tickers
    }

    try:
        response = requests.get(NEWS_API_URL, params=params)
        response.raise_for_status()
        news_data = response.json()

        # Process the news data
        for article in news_data.get('data', []):
            for entity in article.get('entities', []):
                ticker = entity.get('symbol')
                if ticker in tickers_to_check:
                    sentiment = entity.get('sentiment_score')
                    if sentiment is not None:
                        ticker_sentiments[ticker].append(float(sentiment))

    except requests.exceptions.RequestException as e:
        print(f"Error calling Marketaux API: {e}")
        return
    except Exception as e:
        print(f"An error occurred during API processing: {e}")
        return

    # Calculate average sentiment and set flags
    print("\n--- Calculating Averages and Setting Flags ---")
    for ticker in tickers_to_check:
        scores = ticker_sentiments.get(ticker)
        if not scores:
            print(f"No sentiment data found for {ticker}. Resetting flag.")
            # Reset flag if no recent news
            set_sell_flag(ticker, False)
            continue

        average_sentiment = sum(scores) / len(scores)
        print(f"Ticker: {ticker}, Articles Found: {len(scores)}, Average Sentiment: {average_sentiment:.4f}")

        # Set the flag based on the threshold
        if average_sentiment < SENTIMENT_THRESHOLD:
            print(f"  -> FLAG SET: Sentiment ({average_sentiment:.4f}) is below threshold ({SENTIMENT_THRESHOLD})")
            set_sell_flag(ticker, True)
        else:
            # If sentiment is no longer negative, reset the flag
            set_sell_flag(ticker, False)

    print("\n--- Sentiment Analysis Pipeline Finished ---")


if __name__ == '__main__':
    # This allows the script to be run manually for testing
    run_sentiment_analysis()
