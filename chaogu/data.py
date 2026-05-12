from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

from .models import Bar


REQUIRED_COLUMNS = {"timestamp", "symbol", "open", "high", "low", "close", "volume"}


def load_bars(path: str | Path, symbol: str | None = None) -> list[Bar]:
    csv_path = Path(path)
    with csv_path.open("r", encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)
        if reader.fieldnames is None:
            raise ValueError(f"{csv_path} has no header")
        missing = REQUIRED_COLUMNS - set(reader.fieldnames)
        if missing:
            raise ValueError(f"{csv_path} missing required columns: {', '.join(sorted(missing))}")

        bars = [_row_to_bar(row) for row in reader if symbol is None or row["symbol"] == symbol]

    bars.sort(key=lambda bar: (bar.timestamp, bar.symbol))
    if not bars:
        raise ValueError(f"no bars loaded from {csv_path}")
    return bars


def _row_to_bar(row: dict[str, str]) -> Bar:
    return Bar(
        timestamp=_parse_timestamp(row["timestamp"]),
        symbol=row["symbol"],
        open=float(row["open"]),
        high=float(row["high"]),
        low=float(row["low"]),
        close=float(row["close"]),
        volume=float(row["volume"]),
    )


def _parse_timestamp(value: str) -> datetime:
    value = value.strip()
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value)
