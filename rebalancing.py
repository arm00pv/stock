import logging
from database import get_portfolio_holdings, get_risk_profile, execute_sale, execute_investment, log_ai_decision
from cache import yf_download_cached

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def get_target_allocation(risk_profile):
    """
    Returns the target asset allocation for a given risk profile.
    """
    if risk_profile == 'Conservative':
        return {'stocks': 0.4, 'bonds': 0.6}
    elif risk_profile == 'Aggressive':
        return {'stocks': 0.8, 'bonds': 0.2}
    else:  # Moderate
        return {'stocks': 0.6, 'bonds': 0.4}

def rebalance_portfolio(portfolio_name):
    """
    Rebalances a portfolio to match its target asset allocation.
    """
    logging.info(f"Starting rebalancing for portfolio: {portfolio_name}")

    risk_profile = get_risk_profile(portfolio_name)
    if not risk_profile:
        logging.warning(f"Could not retrieve risk profile for {portfolio_name}. Skipping rebalancing.")
        return

    target_allocation = get_target_allocation(risk_profile)
    holdings = get_portfolio_holdings(portfolio_name)

    # For simplicity, we'll assume all current holdings are stocks
    # and we'll use a placeholder for bond ETFs
    BOND_ETF = 'BND'

    total_value = 0
    stock_value = 0
    bond_value = 0

    for holding in holdings:
        try:
            price_history = yf_download_cached(holding['ticker'], period="1d")
            if not price_history.empty:
                price = price_history['Close'].iloc[-1]
                value = holding['shares'] * price
                total_value += value
                if holding['ticker'] == BOND_ETF:
                    bond_value += value
                else:
                    stock_value += value
        except Exception as e:
            logging.error(f"Could not get price for {holding['ticker']}: {e}")

    if total_value == 0:
        logging.info(f"Portfolio {portfolio_name} is empty. Nothing to rebalance.")
        return

    current_allocation = {
        'stocks': stock_value / total_value,
        'bonds': bond_value / total_value
    }

    logging.info(f"Current allocation for {portfolio_name}: {current_allocation}")
    logging.info(f"Target allocation for {portfolio_name}: {target_allocation}")

    # Calculate the difference between the target and current allocations
    stock_diff = target_allocation['stocks'] - current_allocation['stocks']
    bond_diff = target_allocation['bonds'] - current_allocation['bonds']

    # Generate trades to rebalance the portfolio
    if stock_diff > 0.05:  # Need to buy more stocks
        amount_to_buy = total_value * stock_diff
        # For simplicity, we'll sell bonds to fund the purchase of stocks
        # In a real application, you would need to select which stocks to buy
        logging.info(f"Selling {amount_to_buy} of {BOND_ETF} to buy stocks.")
    elif stock_diff < -0.05:  # Need to sell stocks
        amount_to_sell = total_value * abs(stock_diff)
        # For simplicity, we'll sell a portion of each stock holding
        for holding in holdings:
            if holding['ticker'] != BOND_ETF:
                # In a real application, you would need to be more strategic about which stocks to sell
                logging.info(f"Selling a portion of {holding['ticker']} to buy bonds.")

    logging.info(f"Rebalancing for portfolio {portfolio_name} complete.")