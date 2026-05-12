from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .broker import PaperBroker
from .config import AppConfig
from .data import load_bars
from .models import Fill, Portfolio, Side
from .risk import RiskManager
from .strategy import build_strategy


@dataclass(frozen=True)
class BacktestResult:
    summary: dict[str, Any]
    fills: list[Fill]
    equity_curve: list[dict[str, Any]]


def run_backtest(config: AppConfig, out_dir: str | Path | None = None) -> BacktestResult:
    bars = load_bars(config.market_data_csv, config.symbol)
    portfolio = Portfolio(cash=config.starting_cash)
    strategy = build_strategy(config.strategy)
    risk = RiskManager(config.risk)
    broker = PaperBroker(
        commission_bps=config.execution.commission_bps,
        slippage_bps=config.execution.slippage_bps,
        min_fee=config.execution.min_fee,
    )

    prices: dict[str, float] = {}
    fills: list[Fill] = []
    equity_curve: list[dict[str, Any]] = []
    current_day = None
    day_start_equity: float | None = None

    for bar in bars:
        prices[bar.symbol] = bar.close
        if current_day != bar.timestamp.date():
            current_day = bar.timestamp.date()
            day_start_equity = portfolio.market_value(prices)

        forced_exit = risk.forced_exit_signal(bar, portfolio)
        strategy_signal = strategy.on_bar(bar)
        signal = forced_exit or strategy_signal
        equity_before = portfolio.market_value(prices)

        if signal is not None:
            order = risk.order_from_signal(
                signal=signal,
                bar=bar,
                portfolio=portfolio,
                equity=equity_before,
                day_start_equity=day_start_equity,
            )
            if order is not None:
                fill = broker.execute(order, portfolio)
                if fill is not None:
                    fills.append(fill)

        position = portfolio.position_for(config.symbol)
        equity_after = portfolio.market_value(prices)
        equity_curve.append(
            {
                "timestamp": bar.timestamp.isoformat(),
                "symbol": bar.symbol,
                "close": bar.close,
                "cash": round(portfolio.cash, 6),
                "position_qty": position.quantity,
                "position_avg_price": round(position.avg_price, 6),
                "equity": round(equity_after, 6),
            }
        )

    result = BacktestResult(
        summary=_summary(config, portfolio, prices, fills, equity_curve),
        fills=fills,
        equity_curve=equity_curve,
    )

    if out_dir is not None:
        write_result(result, out_dir)

    return result


def write_result(result: BacktestResult, out_dir: str | Path) -> None:
    output = Path(out_dir)
    output.mkdir(parents=True, exist_ok=True)

    with (output / "summary.json").open("w", encoding="utf-8") as file:
        json.dump(result.summary, file, ensure_ascii=False, indent=2)

    with (output / "equity_curve.csv").open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(result.equity_curve[0].keys()))
        writer.writeheader()
        writer.writerows(result.equity_curve)

    with (output / "fills.csv").open("w", encoding="utf-8", newline="") as file:
        fieldnames = ["timestamp", "symbol", "side", "quantity", "price", "fee", "slippage", "reason", "realized_pnl"]
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for fill in result.fills:
            writer.writerow(fill.to_dict())


def _summary(
    config: AppConfig,
    portfolio: Portfolio,
    prices: dict[str, float],
    fills: list[Fill],
    equity_curve: list[dict[str, Any]],
) -> dict[str, Any]:
    final_equity = portfolio.market_value(prices)
    sell_fills = [fill for fill in fills if fill.side == Side.SELL]
    winning_sells = [fill for fill in sell_fills if fill.realized_pnl > 0]
    return {
        "symbol": config.symbol,
        "initial_cash": round(config.starting_cash, 6),
        "final_equity": round(final_equity, 6),
        "total_return_pct": round((final_equity / config.starting_cash - 1) * 100, 4),
        "max_drawdown_pct": round(_max_drawdown(equity_curve) * 100, 4),
        "fills": len(fills),
        "buy_fills": sum(1 for fill in fills if fill.side == Side.BUY),
        "sell_fills": len(sell_fills),
        "sell_win_rate_pct": round((len(winning_sells) / len(sell_fills) * 100) if sell_fills else 0.0, 4),
        "cash": round(portfolio.cash, 6),
        "positions": {
            symbol: position.to_dict()
            for symbol, position in portfolio.positions.items()
            if position.quantity != 0
        },
    }


def _max_drawdown(equity_curve: list[dict[str, Any]]) -> float:
    peak = 0.0
    max_drawdown = 0.0
    for row in equity_curve:
        equity = float(row["equity"])
        peak = max(peak, equity)
        if peak > 0:
            max_drawdown = min(max_drawdown, equity / peak - 1)
    return max_drawdown
