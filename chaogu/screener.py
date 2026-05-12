from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

from .data import load_bars
from .models import Bar


def screen_stocks(
    files: Iterable[str | Path],
    lookback: int = 20,
    short_window: int = 5,
    long_window: int = 20,
    min_return_pct: float = 0.0,
    min_avg_volume: float = 0.0,
    require_uptrend: bool = True,
    limit: int = 50,
) -> dict[str, Any]:
    if lookback < 2:
        raise ValueError("lookback must be at least 2")
    if short_window < 1:
        raise ValueError("short_window must be positive")
    if long_window < short_window:
        raise ValueError("long_window must be at least short_window")
    if limit < 1:
        raise ValueError("limit must be positive")

    candidates: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []

    for file_path in files:
        path = Path(file_path)
        try:
            bars = load_bars(path)
        except Exception as exc:  # noqa: BLE001 - invalid data files should not stop the whole screen.
            errors.append({"path": str(path), "error": str(exc)})
            continue

        grouped: dict[str, list[Bar]] = defaultdict(list)
        for bar in bars:
            grouped[bar.symbol].append(bar)

        for symbol, symbol_bars in grouped.items():
            candidate = _score_symbol(
                symbol=symbol,
                bars=symbol_bars,
                source=path,
                lookback=lookback,
                short_window=short_window,
                long_window=long_window,
                min_return_pct=min_return_pct,
                min_avg_volume=min_avg_volume,
                require_uptrend=require_uptrend,
            )
            if candidate is not None:
                candidates.append(candidate)

    candidates.sort(key=lambda item: item["score"], reverse=True)
    return {
        "candidates": candidates[:limit],
        "total_candidates": len(candidates),
        "errors": errors,
        "parameters": {
            "lookback": lookback,
            "short_window": short_window,
            "long_window": long_window,
            "min_return_pct": min_return_pct,
            "min_avg_volume": min_avg_volume,
            "require_uptrend": require_uptrend,
            "limit": limit,
        },
    }


def _score_symbol(
    symbol: str,
    bars: list[Bar],
    source: Path,
    lookback: int,
    short_window: int,
    long_window: int,
    min_return_pct: float,
    min_avg_volume: float,
    require_uptrend: bool,
) -> dict[str, Any] | None:
    bars = sorted(bars, key=lambda item: item.timestamp)
    required = max(lookback + 1, long_window)
    if len(bars) < required:
        return None

    closes = [bar.close for bar in bars]
    volumes = [bar.volume for bar in bars]
    last = bars[-1]
    start_price = closes[-lookback - 1]
    if start_price <= 0:
        return None

    return_pct = last.close / start_price - 1
    short_ma = sum(closes[-short_window:]) / short_window
    long_ma = sum(closes[-long_window:]) / long_window
    avg_volume = sum(volumes[-lookback:]) / lookback
    uptrend = short_ma > long_ma and last.close > long_ma

    if return_pct < min_return_pct:
        return None
    if avg_volume < min_avg_volume:
        return None
    if require_uptrend and not uptrend:
        return None

    score = return_pct * 100
    if uptrend:
        score += 5
    score += max(0.0, (short_ma / long_ma - 1) * 20) if long_ma > 0 else 0.0

    return {
        "symbol": symbol,
        "source": str(source),
        "last_date": last.timestamp.date().isoformat(),
        "close": round(last.close, 6),
        "return_pct": round(return_pct * 100, 4),
        "short_ma": round(short_ma, 6),
        "long_ma": round(long_ma, 6),
        "avg_volume": round(avg_volume, 2),
        "uptrend": uptrend,
        "score": round(score, 4),
    }
