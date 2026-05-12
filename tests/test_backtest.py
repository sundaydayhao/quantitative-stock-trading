from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from chaogu.backtest import run_backtest
from chaogu.config import load_config
from chaogu.models import Portfolio
from chaogu.paper import run_paper_once


ROOT = Path(__file__).resolve().parents[1]


class BacktestTests(unittest.TestCase):
    def test_backtest_runs_and_writes_outputs(self) -> None:
        cfg = load_config(ROOT / "config.example.json")
        with tempfile.TemporaryDirectory() as temp_dir:
            result = run_backtest(cfg, temp_dir)

            self.assertGreater(result.summary["final_equity"], 0)
            self.assertIn("max_drawdown_pct", result.summary)
            self.assertTrue((Path(temp_dir) / "summary.json").exists())
            self.assertTrue((Path(temp_dir) / "equity_curve.csv").exists())
            self.assertTrue((Path(temp_dir) / "fills.csv").exists())

    def test_paper_state_is_idempotent_without_new_bars(self) -> None:
        cfg = load_config(ROOT / "config.example.json")
        with tempfile.TemporaryDirectory() as temp_dir:
            state_path = Path(temp_dir) / "paper_state.json"

            first = run_paper_once(cfg, state_path)
            second = run_paper_once(cfg, state_path)

            self.assertGreater(first["processed_bars"], 0)
            self.assertEqual(second["new_bars"], 0)
            self.assertEqual(second["new_fills"], [])
            state = json.loads(state_path.read_text(encoding="utf-8"))
            portfolio = Portfolio.from_dict(state["portfolio"])
            self.assertGreaterEqual(portfolio.cash, 0)

    def test_a_share_presets_validate_and_backtest(self) -> None:
        for config_path in sorted((ROOT / "configs").glob("*.json")):
            with self.subTest(config=config_path.name):
                cfg = load_config(config_path)
                result = run_backtest(cfg)

                self.assertEqual(cfg.risk.lot_size, 100)
                self.assertGreater(result.summary["final_equity"], 0)
                for fill in result.fills:
                    self.assertEqual(fill.quantity % cfg.risk.lot_size, 0)


if __name__ == "__main__":
    unittest.main()
