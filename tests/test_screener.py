from __future__ import annotations

import unittest
from pathlib import Path

from chaogu.screener import screen_stocks


ROOT = Path(__file__).resolve().parents[1]


class ScreenerTests(unittest.TestCase):
    def test_screen_stocks_returns_candidates_from_project_csv(self) -> None:
        result = screen_stocks(
            files=[ROOT / "data" / "sample_prices.csv"],
            lookback=20,
            short_window=5,
            long_window=20,
            min_return_pct=-1.0,
            min_avg_volume=0.0,
            require_uptrend=False,
            limit=10,
        )

        self.assertGreaterEqual(result["total_candidates"], 1)
        candidate = result["candidates"][0]
        self.assertEqual(candidate["symbol"], "SAMPLE")
        self.assertIn("return_pct", candidate)
        self.assertIn("score", candidate)

    def test_screen_stocks_honors_uptrend_filter(self) -> None:
        result = screen_stocks(
            files=[ROOT / "data" / "sample_prices.csv"],
            lookback=20,
            short_window=5,
            long_window=20,
            min_return_pct=-1.0,
            min_avg_volume=0.0,
            require_uptrend=True,
            limit=10,
        )

        for candidate in result["candidates"]:
            self.assertTrue(candidate["uptrend"])


if __name__ == "__main__":
    unittest.main()
