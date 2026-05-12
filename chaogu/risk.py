from __future__ import annotations

from .config import RiskConfig
from .models import Bar, Order, Portfolio, Side, Signal


class RiskManager:
    def __init__(self, config: RiskConfig) -> None:
        self.config = config

    def forced_exit_signal(self, bar: Bar, portfolio: Portfolio) -> Signal | None:
        position = portfolio.position_for(bar.symbol)
        if position.quantity <= 0 or position.avg_price <= 0:
            return None

        if self.config.stop_loss_pct > 0:
            stop_price = position.avg_price * (1 - self.config.stop_loss_pct)
            if bar.close <= stop_price:
                return Signal(
                    timestamp=bar.timestamp,
                    symbol=bar.symbol,
                    target_weight=0.0,
                    reason=f"stop_loss@{stop_price:.4f}",
                )

        if self.config.take_profit_pct > 0:
            take_profit_price = position.avg_price * (1 + self.config.take_profit_pct)
            if bar.close >= take_profit_price:
                return Signal(
                    timestamp=bar.timestamp,
                    symbol=bar.symbol,
                    target_weight=0.0,
                    reason=f"take_profit@{take_profit_price:.4f}",
                )

        return None

    def order_from_signal(
        self,
        signal: Signal,
        bar: Bar,
        portfolio: Portfolio,
        equity: float,
        day_start_equity: float | None = None,
    ) -> Order | None:
        if equity <= 0:
            return None

        target_weight = self._bounded_target_weight(signal.target_weight)
        current_qty = portfolio.position_for(signal.symbol).quantity

        if self._daily_loss_tripped(equity, day_start_equity):
            target_weight = min(target_weight, 0.0)
            if current_qty <= 0:
                return None

        current_value = current_qty * bar.close
        target_value = equity * target_weight
        delta_value = target_value - current_value
        if abs(delta_value) < self.config.min_order_value:
            return None

        if delta_value > 0:
            return self._buy_order(signal, bar, portfolio, equity, delta_value)
        return self._sell_order(signal, bar, current_qty, delta_value)

    def _buy_order(
        self,
        signal: Signal,
        bar: Bar,
        portfolio: Portfolio,
        equity: float,
        delta_value: float,
    ) -> Order | None:
        available_cash = max(0.0, portfolio.cash - equity * self.config.min_cash_buffer_pct)
        order_value = min(delta_value, self.config.max_order_value, available_cash)
        if order_value < self.config.min_order_value:
            return None
        quantity = self._round_to_lot(int(order_value // bar.close))
        if quantity <= 0:
            return None
        return Order(
            timestamp=bar.timestamp,
            symbol=signal.symbol,
            side=Side.BUY,
            quantity=quantity,
            price=bar.close,
            reason=signal.reason,
        )

    def _sell_order(self, signal: Signal, bar: Bar, current_qty: int, delta_value: float) -> Order | None:
        order_value = min(abs(delta_value), self.config.max_order_value)
        if order_value < self.config.min_order_value:
            return None
        quantity = int(order_value // bar.close)
        if not self.config.allow_short:
            quantity = min(quantity, current_qty)
            if signal.target_weight <= 0 and quantity >= current_qty:
                quantity = current_qty
            else:
                quantity = self._round_to_lot(quantity)
        else:
            quantity = self._round_to_lot(quantity)
        if quantity <= 0:
            return None
        return Order(
            timestamp=bar.timestamp,
            symbol=signal.symbol,
            side=Side.SELL,
            quantity=quantity,
            price=bar.close,
            reason=signal.reason,
        )

    def _bounded_target_weight(self, target_weight: float) -> float:
        upper = self.config.max_position_pct
        lower = -upper if self.config.allow_short else 0.0
        return min(upper, max(lower, target_weight))

    def _daily_loss_tripped(self, equity: float, day_start_equity: float | None) -> bool:
        if day_start_equity is None or day_start_equity <= 0:
            return False
        return equity <= day_start_equity * (1 - self.config.max_daily_loss_pct)

    def _round_to_lot(self, quantity: int) -> int:
        if self.config.lot_size <= 1:
            return quantity
        return (quantity // self.config.lot_size) * self.config.lot_size
