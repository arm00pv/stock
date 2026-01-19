import os
from dotenv import load_dotenv
import requests
from collections import defaultdict

load_dotenv()
from database import get_portfolio_holdings, set_sell_flag, set_sell_flags_batch

# --- Configuration ---
MARKETAUX_API_KEY = os.environ.get('MARKETAUX_API_KEY', 'YOUR_DEFAULT_KEY_HERE')
SENTIMENT_THRESHOLD = -0.20 # Flag a stock if average sentiment is below this
NEWS_API_URL = "https://api.marketaux.com/v1/news/all"

def get_sentiment_for_tickers(tickers):
    """
    Fetches news from Marketaux for a given list of tickers and returns
    a dictionary of their average sentiment scores.
    """
    if not tickers:
        return {}

    print(f"Fetching sentiment for {len(tickers)} tickers...")
    ticker_sentiments = defaultdict(list)
    results = {}

    params = {
        'api_token': MARKETAUX_API_KEY,
        'symbols': ",".join(tickers),
        'limit': 100
    }

    try:
        response = requests.get(NEWS_API_URL, params=params)
        response.raise_for_status()
        news_data = response.json()

        for article in news_data.get('data', []):
            for entity in article.get('entities', []):
                ticker = entity.get('symbol')
                if ticker in tickers:
                    sentiment = entity.get('sentiment_score')
                    if sentiment is not None:
                        ticker_sentiments[ticker].append(float(sentiment))

        for ticker, scores in ticker_sentiments.items():
            if scores:
                results[ticker] = sum(scores) / len(scores)

    except requests.exceptions.RequestException as e:
        print(f"Error calling Marketaux API: {e}")
    except Exception as e:
        print(f"An error occurred during sentiment processing: {e}")

    print(f"Got sentiment for {len(results)} tickers.")
    return results

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

    ticker_sentiments = get_sentiment_for_tickers(tickers_to_check)

    print("\n--- Setting Flags based on new sentiment data ---")

    sell_flag_updates = []

    for ticker in tickers_to_check:
        average_sentiment = ticker_sentiments.get(ticker)

        if average_sentiment is None:
            # No news, reset flag
            sell_flag_updates.append((ticker, False))
            continue

        if average_sentiment < SENTIMENT_THRESHOLD:
            print(f"  -> FLAG SET: {ticker} sentiment ({average_sentiment:.4f}) is below threshold ({SENTIMENT_THRESHOLD})")
            sell_flag_updates.append((ticker, True))
        else:
            sell_flag_updates.append((ticker, False))

    if sell_flag_updates:
        print(f"Updating sell flags for {len(sell_flag_updates)} tickers...")
        set_sell_flags_batch(sell_flag_updates)

    print("\n--- Sentiment Analysis Pipeline Finished ---")

if __name__ == '__main__':
    run_sentiment_analysis()
