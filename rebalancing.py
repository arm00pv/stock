import logging
from database import get_portfolio_holdings, get_risk_profile, execute_sale, execute_investment, log_ai_decision, get_portfolio_summary
from ai_picker import get_ai_recommendation
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
    Calculates the trades needed to rebalance a portfolio to its target allocation.
    Prioritizes using cash, sells over-allocated assets, and buys AI-recommended stocks.
    """
    logging.info(f"Calculating rebalancing plan for portfolio: {portfolio_name}")

    risk_profile = get_risk_profile(portfolio_name)
    if not risk_profile:
        logging.warning(f"Could not retrieve risk profile for {portfolio_name}.")
        return []

    target_allocation = get_target_allocation(risk_profile)
    holdings = get_portfolio_holdings(portfolio_name)
    cash_balance, _ = get_portfolio_summary(portfolio_name)

    BOND_ETF = 'BND'

    # Calculate current portfolio value and asset allocation
    total_value = cash_balance
    asset_values = {'stocks': 0, 'bonds': 0, 'cash': cash_balance}
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
            continue

    if total_value == 0:
        return []

    # Determine over- and under-allocated assets
    trades = []
    allocation_diffs = {}
    for asset_type, target_pct in target_allocation.items():
        current_pct = asset_values[asset_type] / total_value
        allocation_diffs[asset_type] = target_pct - current_pct

    # Generate sell trades for over-allocated assets
    for asset_type, diff in sorted(allocation_diffs.items(), key=lambda item: item[1]):
        if diff < -0.01: # Materially over-allocated
            amount_to_sell = total_value * abs(diff)

            # Sell proportionally from holdings in this asset class
            holdings_in_class = [h for h in holdings if (h['ticker'] == BOND_ETF if asset_type == 'bonds' else h['ticker'] != BOND_ETF)]
            for holding in holdings_in_class:
                price = current_prices.get(holding['ticker'])
                if price:
                    value_of_holding = holding['shares'] * price
                    proportion = value_of_holding / asset_values[asset_type]
                    sell_amount_for_holding = amount_to_sell * proportion
                    shares_to_sell = sell_amount_for_holding / price
                    trades.append({'action': 'SELL', 'ticker': holding['ticker'], 'shares': round(shares_to_sell, 6), 'amount': round(sell_amount_for_holding, 2)})
                    cash_balance += sell_amount_for_holding

    # Generate buy trades for under-allocated assets, using available cash
    for asset_type, diff in sorted(allocation_diffs.items(), key=lambda item: item[1], reverse=True):
        if diff > 0.01 and cash_balance > 0: # Materially under-allocated
            amount_to_buy = min(total_value * diff, cash_balance)

            if asset_type == 'stocks':
                # Use AI to pick the best stock to buy
                # This assumes the AI picker is aligned with the portfolio's category, which is a simplification
                ticker_to_buy = get_ai_recommendation('hot_stock')
            else:
                ticker_to_buy = BOND_ETF

            if ticker_to_buy:
                price = yf_download_cached(ticker_to_buy, period="1d")['Close'].iloc[-1]
                shares = amount_to_buy / price
                trades.append({'action': 'BUY', 'ticker': ticker_to_buy, 'shares': round(shares, 6), 'amount': round(amount_to_buy, 2)})
                cash_balance -= amount_to_buy

    return trades