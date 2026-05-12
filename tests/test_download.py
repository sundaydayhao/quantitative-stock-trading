from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from chaogu.download import _akshare_symbol, _date_yyyymmdd, _write_bars_csv


class DownloadTests(unittest.TestCase):
    def test_akshare_symbol_accepts_common_a_share_formats(self) -> None:
        self.assertEqual(_akshare_symbol("000001.SZ"), "000001")
        self.assertEqual(_akshare_symbol("600000.SH"), "600000")
        self.assertEqual(_akshare_symbol("sz000001"), "000001")
        self.assertEqual(_akshare_symbol("BJ430047"), "430047")

    def test_date_normalization(self) -> None:
        self.assertEqual(_date_yyyymmdd("2025-01-02"), "20250102")
        self.assertEqual(_date_yyyymmdd("20250102"), "20250102")
        with self.assertRaises(ValueError):
            _date_yyyymmdd("2025/01/02")

    def test_write_bars_csv_uses_project_schema(self) -> None:
        rows = [
            {
                "timestamp": "2025-01-02",
                "symbol": "000001.SZ",
                "open": 10.0,
                "high": 10.5,
                "low": 9.9,
                "close": 10.2,
                "volume": 123400.0,
            }
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "bars.csv"
            _write_bars_csv(path, rows)

            with path.open("r", encoding="utf-8", newline="") as file:
                loaded = list(csv.DictReader(file))

            self.assertEqual(loaded[0]["symbol"], "000001.SZ")
            self.assertEqual(loaded[0]["close"], "10.2")


if __name__ == "__main__":
    unittest.main()
