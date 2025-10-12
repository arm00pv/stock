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
    Calculates the trades needed to rebalance a portfolio.
    Returns a list of proposed trades, not executing them.
    """
    logging.info(f"Calculating rebalancing plan for portfolio: {portfolio_name}")
    risk_profile = get_risk_profile(portfolio_name)
    if not risk_profile:
        logging.warning(f"Could not retrieve risk profile for {portfolio_name}.")
        return []

    target_allocation = get_target_allocation(risk_profile)
    holdings = get_portfolio_holdings(portfolio_name)

    BOND_ETF = 'BND' # Placeholder for bond ETF
    CASH_PROXY = 'USD' # Placeholder for cash

    # Calculate current values
    total_value = 0
    asset_values = {'stocks': 0, 'bonds': 0}
    current_prices = {}

    for holding in holdings:
        try:
            price = yf_download_cached(holding['ticker'], period="1d")['Close'].iloc[-1]
            current_prices[holding['ticker']] = price
            value = holding['shares'] * price
            total_value += value
            asset_type = 'bonds' if holding['ticker'] == BOND_ETF else 'stocks'
            asset_values[asset_type] += value
        except Exception as e:
            logging.error(f"Could not get price for {holding['ticker']}: {e}")
            # Exclude from rebalancing if price is not available
            continue

    if total_value == 0:
        return []

    # Determine trades
    trades = []
    for asset_type, target_pct in target_allocation.items():
        current_value = asset_values[asset_type]
        target_value = total_value * target_pct
        diff = target_value - current_value

        if diff > 0: # Need to buy
            # For simplicity, we buy a broad market ETF for the asset class
            # A more advanced implementation would select specific assets
            ticker_to_buy = 'VOO' if asset_type == 'stocks' else BOND_ETF
            price = yf_download_cached(ticker_to_buy, period="1d")['Close'].iloc[-1]
            shares = diff / price
            trades.append({'action': 'BUY', 'ticker': ticker_to_buy, 'shares': round(shares, 6), 'amount': round(diff, 2)})

        elif diff < 0: # Need to sell
            amount_to_sell = abs(diff)
            # Sell proportionally from existing holdings of that asset type
            for holding in holdings:
                h_asset_type = 'bonds' if holding['ticker'] == BOND_ETF else 'stocks'
                if h_asset_type == asset_type:
                    price = current_prices.get(holding['ticker'])
                    if price:
                        value_of_holding = holding['shares'] * price
                        proportion = value_of_holding / asset_values[asset_type]
                        sell_amount_for_holding = amount_to_sell * proportion
                        shares_to_sell = sell_amount_for_holding / price
                        trades.append({'action': 'SELL', 'ticker': holding['ticker'], 'shares': round(shares_to_sell, 6), 'amount': round(sell_amount_for_holding, 2)})

    return trades