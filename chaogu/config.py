from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class StrategyConfig:
    name: str
    target_weight: float
    short_window: int | None = None
    long_window: int | None = None
    rsi_window: int | None = None
    buy_below: float | None = None
    sell_above: float | None = None
    entry_window: int | None = None
    exit_window: int | None = None
    lookback_window: int | None = None
    entry_return_pct: float | None = None
    exit_return_pct: float | None = None


@dataclass(frozen=True)
class RiskConfig:
    max_position_pct: float
    max_order_value: float
    min_cash_buffer_pct: float
    max_daily_loss_pct: float
    stop_loss_pct: float
    take_profit_pct: float
    min_order_value: float
    allow_short: bool = False
    lot_size: int = 1


@dataclass(frozen=True)
class ExecutionConfig:
    broker: str
    commission_bps: float
    slippage_bps: float
    min_fee: float
    poll_seconds: int


@dataclass(frozen=True)
class AppConfig:
    symbol: str
    market_data_csv: Path
    starting_cash: float
    strategy: StrategyConfig
    risk: RiskConfig
    execution: ExecutionConfig


def load_config(path: str | Path) -> AppConfig:
    config_path = Path(path)
    with config_path.open("r", encoding="utf-8") as file:
        raw = json.load(file)

    base_dir = config_path.parent
    market_data_csv = Path(raw["market_data_csv"])
    if not market_data_csv.is_absolute():
        market_data_csv = base_dir / market_data_csv

    strategy = raw["strategy"]
    risk = raw["risk"]
    execution = raw["execution"]

    cfg = AppConfig(
        symbol=str(raw["symbol"]),
        market_data_csv=market_data_csv,
        starting_cash=float(raw["starting_cash"]),
        strategy=StrategyConfig(
            name=str(strategy["name"]),
            target_weight=float(strategy["target_weight"]),
            short_window=_optional_int(strategy.get("short_window")),
            long_window=_optional_int(strategy.get("long_window")),
            rsi_window=_optional_int(strategy.get("rsi_window")),
            buy_below=_optional_float(strategy.get("buy_below")),
            sell_above=_optional_float(strategy.get("sell_above")),
            entry_window=_optional_int(strategy.get("entry_window")),
            exit_window=_optional_int(strategy.get("exit_window")),
            lookback_window=_optional_int(strategy.get("lookback_window")),
            entry_return_pct=_optional_float(strategy.get("entry_return_pct")),
            exit_return_pct=_optional_float(strategy.get("exit_return_pct")),
        ),
        risk=RiskConfig(
            max_position_pct=float(risk["max_position_pct"]),
            max_order_value=float(risk["max_order_value"]),
            min_cash_buffer_pct=float(risk.get("min_cash_buffer_pct", 0.0)),
            max_daily_loss_pct=float(risk.get("max_daily_loss_pct", 1.0)),
            stop_loss_pct=float(risk.get("stop_loss_pct", 0.0)),
            take_profit_pct=float(risk.get("take_profit_pct", 0.0)),
            min_order_value=float(risk.get("min_order_value", 0.0)),
            allow_short=bool(risk.get("allow_short", False)),
            lot_size=int(risk.get("lot_size", 1)),
        ),
        execution=ExecutionConfig(
            broker=str(execution.get("broker", "paper")),
            commission_bps=float(execution.get("commission_bps", 0.0)),
            slippage_bps=float(execution.get("slippage_bps", 0.0)),
            min_fee=float(execution.get("min_fee", 0.0)),
            poll_seconds=int(execution.get("poll_seconds", 60)),
        ),
    )
    validate_config(cfg)
    return cfg


def validate_config(cfg: AppConfig) -> None:
    _require(cfg.starting_cash > 0, "starting_cash must be positive")
    _require(
        cfg.strategy.name in {"moving_average_cross", "rsi_mean_reversion", "breakout", "momentum"},
        "unsupported strategy",
    )
    _require(0 <= cfg.strategy.target_weight <= 1, "target_weight must be between 0 and 1")
    _validate_strategy(cfg.strategy)
    _require(0 < cfg.risk.max_position_pct <= 1, "max_position_pct must be in (0, 1]")
    _require(cfg.risk.max_order_value > 0, "max_order_value must be positive")
    _require(0 <= cfg.risk.min_cash_buffer_pct < 1, "min_cash_buffer_pct must be in [0, 1)")
    _require(0 < cfg.risk.max_daily_loss_pct <= 1, "max_daily_loss_pct must be in (0, 1]")
    _require(0 <= cfg.risk.stop_loss_pct < 1, "stop_loss_pct must be in [0, 1)")
    _require(0 <= cfg.risk.take_profit_pct < 10, "take_profit_pct must be non-negative")
    _require(cfg.risk.min_order_value >= 0, "min_order_value must be non-negative")
    _require(cfg.risk.lot_size > 0, "lot_size must be positive")
    _require(cfg.execution.broker in {"paper", "live"}, "broker must be paper or live")
    _require(cfg.execution.commission_bps >= 0, "commission_bps must be non-negative")
    _require(cfg.execution.slippage_bps >= 0, "slippage_bps must be non-negative")
    _require(cfg.execution.min_fee >= 0, "min_fee must be non-negative")
    _require(cfg.execution.poll_seconds > 0, "poll_seconds must be positive")


def config_to_dict(cfg: AppConfig) -> dict[str, Any]:
    return {
        "symbol": cfg.symbol,
        "market_data_csv": str(cfg.market_data_csv),
        "starting_cash": cfg.starting_cash,
        "strategy": _clean_dict(cfg.strategy),
        "risk": _clean_dict(cfg.risk),
        "execution": _clean_dict(cfg.execution),
    }


def _validate_strategy(strategy: StrategyConfig) -> None:
    if strategy.name == "moving_average_cross":
        _require(strategy.short_window is not None, "short_window is required for moving_average_cross")
        _require(strategy.long_window is not None, "long_window is required for moving_average_cross")
        _require(strategy.short_window > 0, "short_window must be positive")
        _require(strategy.long_window > strategy.short_window, "long_window must exceed short_window")
        return

    if strategy.name == "rsi_mean_reversion":
        _require(strategy.rsi_window is not None, "rsi_window is required for rsi_mean_reversion")
        _require(strategy.buy_below is not None, "buy_below is required for rsi_mean_reversion")
        _require(strategy.sell_above is not None, "sell_above is required for rsi_mean_reversion")
        _require(strategy.rsi_window >= 2, "rsi_window must be at least 2")
        _require(0 < strategy.buy_below < strategy.sell_above < 100, "buy_below must be below sell_above in (0, 100)")
        return

    if strategy.name == "breakout":
        _require(strategy.entry_window is not None, "entry_window is required for breakout")
        _require(strategy.exit_window is not None, "exit_window is required for breakout")
        _require(strategy.entry_window >= 2, "entry_window must be at least 2")
        _require(strategy.exit_window >= 2, "exit_window must be at least 2")
        return

    if strategy.name == "momentum":
        _require(strategy.lookback_window is not None, "lookback_window is required for momentum")
        _require(strategy.entry_return_pct is not None, "entry_return_pct is required for momentum")
        _require(strategy.exit_return_pct is not None, "exit_return_pct is required for momentum")
        _require(strategy.lookback_window >= 2, "lookback_window must be at least 2")
        _require(strategy.exit_return_pct < strategy.entry_return_pct, "exit_return_pct must be below entry_return_pct")
        return


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _clean_dict(value: Any) -> dict[str, Any]:
    return {key: item for key, item in asdict(value).items() if item is not None}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)
