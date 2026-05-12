from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .broker import PaperBroker
from .config import AppConfig
from .data import load_bars
from .ledger import cash_ledger_from_fills
from .models import Fill, Portfolio
from .risk import RiskManager
from .strategy import build_strategy


@dataclass
class PaperState:
    portfolio: Portfolio
    processed_count: int = 0
    fills: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "portfolio": self.portfolio.to_dict(),
            "processed_count": self.processed_count,
            "fills": self.fills,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PaperState":
        return cls(
            portfolio=Portfolio.from_dict(data["portfolio"]),
            processed_count=int(data.get("processed_count", 0)),
            fills=list(data.get("fills", [])),
        )


def load_state(path: str | Path, starting_cash: float) -> PaperState:
    state_path = Path(path)
    if not state_path.exists():
        return PaperState(portfolio=Portfolio(cash=starting_cash))
    with state_path.open("r", encoding="utf-8") as file:
        return PaperState.from_dict(json.load(file))


def save_state(path: str | Path, state: PaperState) -> None:
    state_path = Path(path)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    with state_path.open("w", encoding="utf-8") as file:
        json.dump(state.to_dict(), file, ensure_ascii=False, indent=2)


def run_paper_once(config: AppConfig, state_path: str | Path) -> dict[str, Any]:
    bars = load_bars(config.market_data_csv, config.symbol)
    state = load_state(state_path, config.starting_cash)
    previous_processed_count = state.processed_count
    strategy = build_strategy(config.strategy)
    risk = RiskManager(config.risk)
    broker = PaperBroker(
        commission_bps=config.execution.commission_bps,
        slippage_bps=config.execution.slippage_bps,
        min_fee=config.execution.min_fee,
    )

    prices: dict[str, float] = {}
    current_day = None
    day_start_equity: float | None = None
    new_fills: list[Fill] = []

    for index, bar in enumerate(bars):
        prices[bar.symbol] = bar.close
        if current_day != bar.timestamp.date():
            current_day = bar.timestamp.date()
            day_start_equity = state.portfolio.market_value(prices)

        forced_exit = risk.forced_exit_signal(bar, state.portfolio) if index >= state.processed_count else None
        strategy_signal = strategy.on_bar(bar)
        if index < state.processed_count:
            continue

        signal = forced_exit or strategy_signal
        if signal is None:
            continue

        equity = state.portfolio.market_value(prices)
        order = risk.order_from_signal(signal, bar, state.portfolio, equity, day_start_equity)
        if order is None:
            continue

        fill = broker.execute(order, state.portfolio)
        if fill is not None:
            new_fills.append(fill)
            state.fills.append(fill.to_dict())

    state.processed_count = len(bars)
    save_state(state_path, state)

    final_equity = state.portfolio.market_value(prices) if prices else state.portfolio.cash
    return {
        "processed_bars": len(bars),
        "new_bars": max(0, len(bars) - previous_processed_count),
        "new_fills": [fill.to_dict() for fill in new_fills],
        "fills": state.fills,
        "cash_ledger": cash_ledger_from_fills(state.fills),
        "cash": round(state.portfolio.cash, 6),
        "equity": round(final_equity, 6),
        "positions": state.portfolio.to_dict()["positions"],
        "state_path": str(state_path),
    }


def watch_paper(config: AppConfig, state_path: str | Path) -> None:
    while True:
        report = run_paper_once(config, state_path)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        time.sleep(config.execution.poll_seconds)
