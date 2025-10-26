from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List, Sequence

from trading.domain.models import BaseOrderRequest, ListedInstrumentBook, OrderSide, OrderType


@dataclass(slots=True)
class Fill:
    price: float
    quantity: int


class MatchingEngine:
    def match(
        self,
        order: BaseOrderRequest,
        book: ListedInstrumentBook,
    ) -> tuple[List[Fill], int]:
        remaining = order.quantity
        fills: list[Fill] = []
        levels: Sequence[tuple[float, int]]
        price_condition: Callable[[float], bool]

        if order.side is OrderSide.BUY:
            levels = book.asks

            def price_condition(price: float) -> bool:
                if order.order_type is OrderType.MARKET:
                    return True
                limit_price = getattr(order, "limit_price", None)
                return limit_price is not None and price <= limit_price

        else:
            levels = book.bids

            def price_condition(price: float) -> bool:
                if order.order_type is OrderType.MARKET:
                    return True
                limit_price = getattr(order, "limit_price", None)
                return limit_price is not None and price >= limit_price

        for price, available in levels:
            if remaining <= 0:
                break
            if not price_condition(price):
                continue
            fill_qty = min(available, remaining)
            fills.append(Fill(price=price, quantity=fill_qty))
            remaining -= fill_qty

        return fills, remaining
