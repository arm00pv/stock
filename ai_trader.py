import logging
from database import get_portfolio_holdings, execute_sale, execute_investment, log_ai_decision, get_risk_profile
from ai_picker import get_ai_recommendation, get_ai_recommendation_score
from constants import TICKER_CATEGORIES
from cache import yf_download_cached

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def calculate_sell_score(ticker, current_score):
    """
    Calculates a dynamic sell score based on the AI score and recent performance.
    """
    try:
        hist = yf_download_cached(ticker, period="1y")
        if hist.empty or len(hist) < 252:
            return current_score

        # Calculate drop from recent peak
        peak_price = hist['Close'].max()
        current_price = hist['Close'].iloc[-1]
        peak_drop_pct = (current_price - peak_price) / peak_price if peak_price > 0 else 0

        # Calculate historical volatility
        returns = hist['Close'].pct_change().dropna()
        volatility = returns.std() * (252**0.5)

        # Calculate Beta
        market_hist = yf_download_cached('^GSPC', period="1y")
        market_returns = market_hist['Close'].pct_change().dropna()
        covariance = returns.cov(market_returns)
        beta = covariance / market_returns.var()

        # Combine AI score with performance drop, volatility, and beta
        sell_score = current_score + (peak_drop_pct * 0.3) - (volatility * 0.1) - (beta * 0.1)
        return sell_score
    except Exception as e:
        logging.error(f"Error calculating sell score for {ticker}: {e}")
        return current_score

def get_market_sentiment():
    """
    Analyzes the overall market sentiment.
    """
    # For simplicity, we'll use a major index as a proxy for the market
    market_ticker = '^GSPC'
    sentiment_score = get_ai_recommendation_score('hot_stock', market_ticker)
    return sentiment_score

def manage_ai_portfolio():
    """
    Manages the AI-guided portfolio by selling underperforming assets
    and reinvesting in top-rated stocks.
    """
    logging.info("Starting AI portfolio management cycle.")

    portfolio_name = 'ai_guided_portfolio'
    holdings = get_portfolio_holdings(portfolio_name)
    risk_profile = get_risk_profile(portfolio_name)

    # Set base sell threshold based on risk profile
    if risk_profile == 'Conservative':
        base_sell_threshold = 0.6
    elif risk_profile == 'Aggressive':
        base_sell_threshold = 0.3
    else:  # Moderate
        base_sell_threshold = 0.4

    market_sentiment = get_market_sentiment()
    # Adjust sell threshold based on market sentiment
    sell_threshold = base_sell_threshold - (market_sentiment * 0.1) # More aggressive selling in a bear market

    total_proceeds = 0
    if not holdings:
        logging.info("AI portfolio is empty. Investing in a new stock.")
        invest_in_new_stock(portfolio_name, 100.00) # Initial investment
        return

    # Re-evaluate holdings and sell if necessary
    for holding in holdings:
        ticker = holding['ticker']
        current_ai_score = get_ai_recommendation_score('hot_stock', ticker)
        sell_score = calculate_sell_score(ticker, current_ai_score)

        # Define a threshold for selling
        if sell_score < sell_threshold:
            logging.info(f"Selling {ticker} due to low dynamic score: {sell_score} (Threshold: {sell_threshold})")
            shares_to_sell = holding['shares']

            try:
                price_history = yf_download_cached(ticker, period="1d")
                if not price_history.empty:
                    price = price_history['Close'].iloc[-1]
                    success, message = execute_sale(portfolio_name, ticker, shares_to_sell, price)
                    if success:
                        log_ai_decision(portfolio_name, ticker, 'SELL', f"Low dynamic score: {sell_score:.2f}")
                        total_proceeds += shares_to_sell * price
            except Exception as e:
                logging.error(f"Failed to sell {ticker}: {e}")

    # Re-invest proceeds
    investment_amount = total_proceeds if total_proceeds > 0 else 100.00
    invest_in_new_stock(portfolio_name, investment_amount)

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
                log_ai_decision(portfolio_name, new_ticker, 'BUY', f"Top-rated stock with score: {get_ai_recommendation_score(category, new_ticker):.2f}")
                logging.info(f"AI portfolio invested in {new_ticker}.")
        except Exception as e:
            logging.error(f"AI portfolio failed to invest in {new_ticker}: {e}")