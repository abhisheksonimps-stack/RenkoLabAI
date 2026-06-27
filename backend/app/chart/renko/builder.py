from __future__ import annotations

from datetime import datetime
from typing import Any

from backend.app.chart.renko.configuration import BrickConfiguration
from backend.app.chart.renko.interfaces import BrickBuilder
from backend.app.chart.renko.models import Brick, BrickDirection


class TraditionalBrickBuilder(BrickBuilder):
    async def build_brick(self, market_data: Any, configuration: BrickConfiguration) -> Brick:
        if not isinstance(market_data, dict):
            raise TypeError("Brick builder market_data must be a dict")

        direction = BrickDirection(market_data["direction"])
        open_price = float(market_data["open_price"])
        close_price = float(market_data["close_price"])
        high_price = float(market_data.get("high_price", max(open_price, close_price)))
        low_price = float(market_data.get("low_price", min(open_price, close_price)))
        volume = float(market_data.get("volume", 0.0) or 0.0)
        timestamp = market_data["timestamp"]

        if not isinstance(timestamp, datetime):
            raise TypeError("Brick timestamp must be a datetime")

        brick_id = (
            f"brick-{direction.value}-{timestamp.isoformat()}-"
            f"{int(open_price * 100000)}-{int(close_price * 100000)}"
        )

        return Brick(
            brick_id=brick_id,
            direction=direction,
            open_price=open_price,
            close_price=close_price,
            high_price=high_price,
            low_price=low_price,
            volume=volume,
            created_at=timestamp,
            metadata={
                "brick_size": configuration.brick_size,
                "price_source": configuration.price_source.value,
            },
        )
