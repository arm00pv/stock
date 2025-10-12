import unittest
import sys
import os
from unittest.mock import patch, MagicMock

# Add the parent directory to the sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from ai_trader import manage_ai_portfolio, calculate_sell_score, invest_in_new_stock
from database import get_portfolio_holdings, execute_sale, execute_investment, log_ai_decision

class AITraderTestCase(unittest.TestCase):

    @patch('ai_trader.get_portfolio_holdings')
    @patch('ai_trader.invest_in_new_stock')
    def test_manage_ai_portfolio_empty(self, mock_invest, mock_get_holdings):
        mock_get_holdings.return_value = []
        manage_ai_portfolio()
        mock_invest.assert_called_once_with('ai_guided_portfolio', 100.00)

    @patch('ai_trader.yf_download_cached')
    def test_calculate_sell_score(self, mock_yf):
        # Create a mock dataframe
        mock_df = MagicMock()
        mock_df.empty = False
        mock_df['Close'].max.return_value = 100
        mock_df['Close'].iloc.__getitem__.return_value = 90 # Correctly mock iloc
        mock_yf.return_value = mock_df

        score = calculate_sell_score('AAPL', 0.8)
        self.assertLess(score, 0.8)

    @patch('ai_trader.get_portfolio_holdings')
    @patch('ai_trader.get_ai_recommendation_score')
    @patch('ai_trader.calculate_sell_score')
    @patch('ai_trader.execute_sale')
    @patch('ai_trader.invest_in_new_stock')
    def test_manage_ai_portfolio_sells_stock(self, mock_invest, mock_execute_sale, mock_calc_score, mock_get_score, mock_get_holdings):
        mock_get_holdings.return_value = [{'ticker': 'AAPL', 'shares': 10}]
        mock_get_score.return_value = 0.3
        mock_calc_score.return_value = 0.3 # Simulate a low score

        manage_ai_portfolio()

        mock_execute_sale.assert_called_once()
        mock_invest.assert_called_once()

    @patch('ai_trader.get_ai_recommendation')
    @patch('ai_trader.yf_download_cached')
    @patch('ai_trader.execute_investment')
    @patch('ai_trader.log_ai_decision')
    def test_invest_in_new_stock(self, mock_log, mock_execute, mock_yf, mock_get_rec):
        mock_get_rec.return_value = 'MSFT'
        mock_df = MagicMock()
        mock_df.empty = False
        mock_df['Close'].iloc[-1] = 200.0
        mock_yf.return_value = mock_df

        invest_in_new_stock('ai_guided_portfolio', 100)

        mock_execute.assert_called_once()
        mock_log.assert_called_once()


if __name__ == '__main__':
    unittest.main()