from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class Side(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


@dataclass(frozen=True)
class Bar:
    timestamp: datetime
    symbol: str
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True)
class Signal:
    timestamp: datetime
    symbol: str
    target_weight: float
    reason: str


@dataclass(frozen=True)
class Order:
    timestamp: datetime
    symbol: str
    side: Side
    quantity: int
    price: float
    reason: str

    @property
    def notional(self) -> float:
        return self.quantity * self.price


@dataclass(frozen=True)
class Fill:
    timestamp: datetime
    symbol: str
    side: Side
    quantity: int
    price: float
    fee: float
    slippage: float
    reason: str
    realized_pnl: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "symbol": self.symbol,
            "side": self.side.value,
            "quantity": self.quantity,
            "price": round(self.price, 6),
            "fee": round(self.fee, 6),
            "slippage": round(self.slippage, 6),
            "reason": self.reason,
            "realized_pnl": round(self.realized_pnl, 6),
        }


@dataclass
class Position:
    symbol: str
    quantity: int = 0
    avg_price: float = 0.0

    def market_value(self, price: float) -> float:
        return self.quantity * price

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "quantity": self.quantity,
            "avg_price": self.avg_price,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Position":
        return cls(
            symbol=str(data["symbol"]),
            quantity=int(data.get("quantity", 0)),
            avg_price=float(data.get("avg_price", 0.0)),
        )


@dataclass
class Portfolio:
    cash: float
    positions: dict[str, Position] = field(default_factory=dict)

    def position_for(self, symbol: str) -> Position:
        if symbol not in self.positions:
            self.positions[symbol] = Position(symbol=symbol)
        return self.positions[symbol]

    def market_value(self, prices: dict[str, float]) -> float:
        value = self.cash
        for symbol, position in self.positions.items():
            if position.quantity == 0:
                continue
            if symbol not in prices:
                continue
            value += position.market_value(prices[symbol])
        return value

    def exposure_value(self, symbol: str, price: float) -> float:
        return self.position_for(symbol).market_value(price)

    def to_dict(self) -> dict[str, Any]:
        return {
            "cash": self.cash,
            "positions": {
                symbol: position.to_dict()
                for symbol, position in self.positions.items()
                if position.quantity != 0
            },
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Portfolio":
        positions = {
            symbol: Position.from_dict(position)
            for symbol, position in data.get("positions", {}).items()
        }
        return cls(cash=float(data["cash"]), positions=positions)
