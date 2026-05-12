from __future__ import annotations

import unittest

from chaogu.ledger import cash_ledger_from_fills


class LedgerTests(unittest.TestCase):
    def test_cash_ledger_tracks_buy_and_sell_cash_effects(self) -> None:
        rows = cash_ledger_from_fills(
            [
                {
                    "timestamp": "2025-01-02",
                    "symbol": "000001.SZ",
                    "side": "BUY",
                    "quantity": 100,
                    "price": 10.0,
                    "fee": 5.0,
                },
                {
                    "timestamp": "2025-01-03",
                    "symbol": "000001.SZ",
                    "side": "SELL",
                    "quantity": 100,
                    "price": 11.0,
                    "fee": 5.0,
                    "realized_pnl": 95.0,
                },
            ]
        )

        self.assertEqual(rows[0]["gross_amount"], 1000.0)
        self.assertEqual(rows[0]["cash_effect"], -1005.0)
        self.assertEqual(rows[1]["cash_effect"], 1095.0)
        self.assertEqual(rows[1]["cumulative_cash_effect"], 90.0)
        self.assertEqual(rows[1]["realized_pnl"], 95.0)


if __name__ == "__main__":
    unittest.main()
