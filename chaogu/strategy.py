from __future__ import annotations

from collections import defaultdict, deque
from typing import Protocol

from .config import StrategyConfig
from .models import Bar, Signal


class Strategy(Protocol):
    def on_bar(self, bar: Bar) -> Signal | None:
        ...


class MovingAverageCrossStrategy:
    def __init__(self, short_window: int, long_window: int, target_weight: float) -> None:
        if short_window >= long_window:
            raise ValueError("short_window must be smaller than long_window")
        self.short_window = short_window
        self.long_window = long_window
        self.target_weight = target_weight
        self._closes: dict[str, deque[float]] = defaultdict(lambda: deque(maxlen=long_window))

    def on_bar(self, bar: Bar) -> Signal | None:
        closes = self._closes[bar.symbol]
        closes.append(bar.close)
        if len(closes) < self.long_window:
            return None

        all_closes = list(closes)
        short_avg = sum(all_closes[-self.short_window :]) / self.short_window
        long_avg = sum(all_closes) / self.long_window
        if short_avg > long_avg:
            return Signal(
                timestamp=bar.timestamp,
                symbol=bar.symbol,
                target_weight=self.target_weight,
                reason=f"sma{self.short_window}>{self.long_window}",
            )
        return Signal(
            timestamp=bar.timestamp,
            symbol=bar.symbol,
            target_weight=0.0,
            reason=f"sma{self.short_window}<={self.long_window}",
        )


class RsiMeanReversionStrategy:
    def __init__(self, rsi_window: int, buy_below: float, sell_above: float, target_weight: float) -> None:
        self.rsi_window = rsi_window
        self.buy_below = buy_below
        self.sell_above = sell_above
        self.target_weight = target_weight
        self._closes: dict[str, deque[float]] = defaultdict(lambda: deque(maxlen=rsi_window + 1))

    def on_bar(self, bar: Bar) -> Signal | None:
        closes = self._closes[bar.symbol]
        closes.append(bar.close)
        if len(closes) < self.rsi_window + 1:
            return None

        rsi = _simple_rsi(list(closes))
        if rsi <= self.buy_below:
            return Signal(
                timestamp=bar.timestamp,
                symbol=bar.symbol,
                target_weight=self.target_weight,
                reason=f"rsi{self.rsi_window}<={self.buy_below:g}",
            )
        if rsi >= self.sell_above:
            return Signal(
                timestamp=bar.timestamp,
                symbol=bar.symbol,
                target_weight=0.0,
                reason=f"rsi{self.rsi_window}>={self.sell_above:g}",
            )
        return None


class BreakoutStrategy:
    def __init__(self, entry_window: int, exit_window: int, target_weight: float) -> None:
        self.entry_window = entry_window
        self.exit_window = exit_window
        self.target_weight = target_weight
        self._closes: dict[str, deque[float]] = defaultdict(lambda: deque(maxlen=max(entry_window, exit_window)))

    def on_bar(self, bar: Bar) -> Signal | None:
        closes = self._closes[bar.symbol]
        if len(closes) >= self.entry_window and bar.close >= max(list(closes)[-self.entry_window :]):
            closes.append(bar.close)
            return Signal(
                timestamp=bar.timestamp,
                symbol=bar.symbol,
                target_weight=self.target_weight,
                reason=f"close>={self.entry_window}d_high",
            )
        if len(closes) >= self.exit_window and bar.close <= min(list(closes)[-self.exit_window :]):
            closes.append(bar.close)
            return Signal(
                timestamp=bar.timestamp,
                symbol=bar.symbol,
                target_weight=0.0,
                reason=f"close<={self.exit_window}d_low",
            )

        closes.append(bar.close)
        return None


class MomentumStrategy:
    def __init__(
        self,
        lookback_window: int,
        entry_return_pct: float,
        exit_return_pct: float,
        target_weight: float,
    ) -> None:
        self.lookback_window = lookback_window
        self.entry_return_pct = entry_return_pct
        self.exit_return_pct = exit_return_pct
        self.target_weight = target_weight
        self._closes: dict[str, deque[float]] = defaultdict(lambda: deque(maxlen=lookback_window + 1))

    def on_bar(self, bar: Bar) -> Signal | None:
        closes = self._closes[bar.symbol]
        closes.append(bar.close)
        if len(closes) < self.lookback_window + 1:
            return None

        start_price = closes[0]
        if start_price <= 0:
            return None

        return_pct = bar.close / start_price - 1
        if return_pct >= self.entry_return_pct:
            return Signal(
                timestamp=bar.timestamp,
                symbol=bar.symbol,
                target_weight=self.target_weight,
                reason=f"mom{self.lookback_window}>={self.entry_return_pct:.2%}",
            )
        if return_pct <= self.exit_return_pct:
            return Signal(
                timestamp=bar.timestamp,
                symbol=bar.symbol,
                target_weight=0.0,
                reason=f"mom{self.lookback_window}<={self.exit_return_pct:.2%}",
            )
        return None


def build_strategy(config: StrategyConfig) -> Strategy:
    if config.name == "moving_average_cross":
        return MovingAverageCrossStrategy(
            short_window=_required_int(config.short_window, "short_window"),
            long_window=_required_int(config.long_window, "long_window"),
            target_weight=config.target_weight,
        )
    if config.name == "rsi_mean_reversion":
        return RsiMeanReversionStrategy(
            rsi_window=_required_int(config.rsi_window, "rsi_window"),
            buy_below=_required_float(config.buy_below, "buy_below"),
            sell_above=_required_float(config.sell_above, "sell_above"),
            target_weight=config.target_weight,
        )
    if config.name == "breakout":
        return BreakoutStrategy(
            entry_window=_required_int(config.entry_window, "entry_window"),
            exit_window=_required_int(config.exit_window, "exit_window"),
            target_weight=config.target_weight,
        )
    if config.name == "momentum":
        return MomentumStrategy(
            lookback_window=_required_int(config.lookback_window, "lookback_window"),
            entry_return_pct=_required_float(config.entry_return_pct, "entry_return_pct"),
            exit_return_pct=_required_float(config.exit_return_pct, "exit_return_pct"),
            target_weight=config.target_weight,
        )
    raise ValueError(f"unsupported strategy: {config.name}")


def _simple_rsi(closes: list[float]) -> float:
    gains = 0.0
    losses = 0.0
    for previous, current in zip(closes, closes[1:]):
        delta = current - previous
        if delta >= 0:
            gains += delta
        else:
            losses += abs(delta)

    if gains == 0 and losses == 0:
        return 50.0
    if losses == 0:
        return 100.0
    relative_strength = gains / losses
    return 100 - (100 / (1 + relative_strength))


def _required_int(value: int | None, name: str) -> int:
    if value is None:
        raise ValueError(f"{name} is required")
    return value


def _required_float(value: float | None, name: str) -> float:
    if value is None:
        raise ValueError(f"{name} is required")
    return value
