from __future__ import annotations

import unittest

from chaogu.webapp import CONFIG_DIR, _prepare_config_for_path, _safe_config_name


class WebAppTests(unittest.TestCase):
    def test_safe_config_name_keeps_json_inside_config_dir(self) -> None:
        self.assertEqual(_safe_config_name("000001 sma"), "000001_sma.json")
        self.assertEqual(_safe_config_name("strategy.json"), "strategy.json")
        with self.assertRaises(ValueError):
            _safe_config_name(".hidden")

    def test_prepare_config_rewrites_project_data_path_for_configs_dir(self) -> None:
        config = {
            "symbol": "000001.SZ",
            "market_data_csv": "data/000001.SZ.daily.qfq.csv",
            "starting_cash": 100000,
            "strategy": {
                "name": "moving_average_cross",
                "target_weight": 0.6,
                "short_window": 5,
                "long_window": 20,
            },
            "risk": {
                "max_position_pct": 0.6,
                "max_order_value": 20000,
                "min_cash_buffer_pct": 0.05,
                "max_daily_loss_pct": 0.03,
                "stop_loss_pct": 0.08,
                "take_profit_pct": 0.18,
                "min_order_value": 1000,
                "allow_short": False,
                "lot_size": 100,
            },
            "execution": {
                "broker": "paper",
                "commission_bps": 2.0,
                "slippage_bps": 3.0,
                "min_fee": 5.0,
                "poll_seconds": 60,
            },
        }

        prepared = _prepare_config_for_path(config, CONFIG_DIR / "web_test.json")

        self.assertEqual(prepared["market_data_csv"], "../data/000001.SZ.daily.qfq.csv")


if __name__ == "__main__":
    unittest.main()
