import logging
from database import get_portfolio_holdings, execute_sale, execute_investment
from ai_picker import get_ai_recommendation, get_ai_recommendation_score
from constants import TICKER_CATEGORIES
from cache import yf_download_cached

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def manage_ai_portfolio():
    """
    Manages the AI-guided portfolio by selling underperforming assets
    and reinvesting in top-rated stocks.
    """
    logging.info("Starting AI portfolio management cycle.")

    portfolio_name = 'ai_guided_portfolio'
    holdings = get_portfolio_holdings(portfolio_name)

    if not holdings:
        logging.info("AI portfolio is empty. Investing in a new stock.")
        invest_in_new_stock(portfolio_name, 100.00) # Initial investment
        return

    # Re-evaluate holdings and sell if necessary
    for holding in holdings:
        ticker = holding['ticker']
        current_score = get_ai_recommendation_score('hot_stock', ticker)

        # Define a threshold for selling
        if current_score < 0.5: # Example threshold
            logging.info(f"Selling {ticker} due to low score: {current_score}")
            shares_to_sell = holding['shares']

            try:
                price_history = yf_download_cached(ticker, period="1d")
                if not price_history.empty:
                    price = price_history['Close'].iloc[-1]
                    execute_sale(portfolio_name, ticker, shares_to_sell, price)
            except Exception as e:
                logging.error(f"Failed to sell {ticker}: {e}")

    # Re-invest proceeds
    # For simplicity, we'll just invest a fixed amount for now
    invest_in_new_stock(portfolio_name, 100.00)

def invest_in_new_stock(portfolio_name, investment_amount):
    """
    Invests a given amount in a new top-rated stock.
    """
    category = 'hot_stock' # For now, the AI portfolio will only invest in hot stocks
    new_ticker = get_ai_recommendation(category, TICKER_CATEGORIES.get(category, []))

    if new_ticker:
        try:
            price_history = yf_download_cached(new_ticker, period="1d")
            if not price_history.empty:
                price = price_history['Close'].iloc[-1]
                shares = investment_amount / price
                execute_investment(portfolio_name, new_ticker, shares, price, investment_amount)
                logging.info(f"AI portfolio invested in {new_ticker}.")
        except Exception as e:
            logging.error(f"AI portfolio failed to invest in {new_ticker}: {e}")