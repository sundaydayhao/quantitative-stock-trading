from __future__ import annotations

from abc import ABC, abstractmethod

from .models import Fill, Order, Portfolio, Side


class Broker(ABC):
    @abstractmethod
    def execute(self, order: Order, portfolio: Portfolio) -> Fill | None:
        ...


class PaperBroker(Broker):
    def __init__(self, commission_bps: float = 0.0, slippage_bps: float = 0.0, min_fee: float = 0.0) -> None:
        self.commission_bps = commission_bps
        self.slippage_bps = slippage_bps
        self.min_fee = min_fee

    def execute(self, order: Order, portfolio: Portfolio) -> Fill | None:
        if order.side == Side.BUY:
            return self._buy(order, portfolio)
        if order.side == Side.SELL:
            return self._sell(order, portfolio)
        raise ValueError(f"unsupported order side: {order.side}")

    def _buy(self, order: Order, portfolio: Portfolio) -> Fill | None:
        execution_price = order.price * (1 + self.slippage_bps / 10_000)
        quantity = order.quantity
        fee = self._fee(quantity * execution_price)

        while quantity > 0 and quantity * execution_price + fee > portfolio.cash:
            quantity -= 1
            fee = self._fee(quantity * execution_price)

        if quantity <= 0:
            return None

        gross = quantity * execution_price
        portfolio.cash -= gross + fee
        position = portfolio.position_for(order.symbol)
        new_quantity = position.quantity + quantity
        if new_quantity <= 0:
            position.quantity = 0
            position.avg_price = 0.0
        else:
            position.avg_price = ((position.quantity * position.avg_price) + gross) / new_quantity
            position.quantity = new_quantity

        return Fill(
            timestamp=order.timestamp,
            symbol=order.symbol,
            side=Side.BUY,
            quantity=quantity,
            price=execution_price,
            fee=fee,
            slippage=execution_price - order.price,
            reason=order.reason,
        )

    def _sell(self, order: Order, portfolio: Portfolio) -> Fill | None:
        position = portfolio.position_for(order.symbol)
        quantity = min(order.quantity, position.quantity)
        if quantity <= 0:
            return None

        execution_price = order.price * (1 - self.slippage_bps / 10_000)
        gross = quantity * execution_price
        fee = self._fee(gross)
        realized_pnl = (execution_price - position.avg_price) * quantity - fee

        portfolio.cash += gross - fee
        position.quantity -= quantity
        if position.quantity == 0:
            position.avg_price = 0.0

        return Fill(
            timestamp=order.timestamp,
            symbol=order.symbol,
            side=Side.SELL,
            quantity=quantity,
            price=execution_price,
            fee=fee,
            slippage=order.price - execution_price,
            reason=order.reason,
            realized_pnl=realized_pnl,
        )

    def _fee(self, notional: float) -> float:
        if notional <= 0:
            return 0.0
        return max(self.min_fee, notional * self.commission_bps / 10_000)


class LiveBrokerAdapter(Broker):
    def execute(self, order: Order, portfolio: Portfolio) -> Fill | None:
        return self.place_order(order, portfolio)

    def place_order(self, order: Order, portfolio: Portfolio) -> Fill | None:
        raise NotImplementedError(
            "Live trading is intentionally not implemented. "
            "Connect your broker API here and keep RiskManager checks before this call."
        )
