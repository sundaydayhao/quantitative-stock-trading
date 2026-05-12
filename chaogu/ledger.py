from __future__ import annotations

from typing import Any, Iterable


def cash_ledger_from_fills(fills: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    cumulative = 0.0
    for fill in fills:
        quantity = int(fill.get("quantity", 0))
        price = float(fill.get("price", 0.0))
        fee = float(fill.get("fee", 0.0))
        gross_amount = quantity * price
        side = str(fill.get("side", "")).upper()
        if side == "BUY":
            cash_effect = -(gross_amount + fee)
        elif side == "SELL":
            cash_effect = gross_amount - fee
        else:
            cash_effect = 0.0
        cumulative += cash_effect

        rows.append(
            {
                "timestamp": fill.get("timestamp", ""),
                "symbol": fill.get("symbol", ""),
                "side": side,
                "quantity": quantity,
                "price": round(price, 6),
                "gross_amount": round(gross_amount, 6),
                "fee": round(fee, 6),
                "cash_effect": round(cash_effect, 6),
                "cumulative_cash_effect": round(cumulative, 6),
                "realized_pnl": round(float(fill.get("realized_pnl", 0.0)), 6),
                "reason": fill.get("reason", ""),
            }
        )
    return rows
