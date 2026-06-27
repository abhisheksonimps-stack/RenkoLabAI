from __future__ import annotations

from collections import deque
from datetime import datetime
from typing import Any

from backend.app.chart.renko.configuration import BrickConfiguration, PriceSource
from backend.app.chart.renko.events import BrickClosed, BrickOpened, BrickReversed, BrickExtended
from backend.app.chart.renko.interfaces import BrickBuilder, RenkoEngine
from backend.app.chart.renko.models import Brick, BrickDirection, BrickSnapshot, BrickState
from backend.app.events.bus import EventBus
from backend.app.chart.renko.builder import TraditionalBrickBuilder


class TraditionalRenkoEngine(RenkoEngine):
    def __init__(self, event_bus: EventBus | None = None) -> None:
        self._event_bus = event_bus
        self._configuration: BrickConfiguration | None = None
        self._state: BrickState | None = None
        self._builder: BrickBuilder = TraditionalBrickBuilder()
        self._brick_history: deque[Brick] = deque()
        self._pending_open_price: float | None = None
        self._last_brick_boundary: float | None = None

        if self._event_bus is not None:
            self._event_bus.register_event(BrickOpened)
            self._event_bus.register_event(BrickExtended)
            self._event_bus.register_event(BrickReversed)

    @property
    def state(self) -> BrickState:
        if self._state is None:
            raise RuntimeError("Engine state has not been initialized")
        return self._state

    async def start(self) -> None:
        if self._configuration is None:
            raise RuntimeError("Engine has not been configured")
        self._state = BrickState(
            direction=BrickDirection.NEUTRAL,
            last_price=0.0,
            brick_size=self._configuration.brick_size,
            is_open=True,
            metadata={"started_at": datetime.utcnow().isoformat()},
        )

    async def stop(self) -> None:
        if self._state is None:
            return
        self._state = BrickState(
            direction=self._state.direction,
            last_price=self._state.last_price,
            brick_size=self._state.brick_size,
            is_open=False,
            metadata={**self._state.metadata, "stopped_at": datetime.utcnow().isoformat()},
        )

    async def reset(self) -> None:
        self._configuration = None
        self._state = None
        self._brick_history.clear()
        self._pending_open_price = None
        self._last_brick_boundary = None

    async def process_market_data(self, market_data: Any) -> None:
        if self._configuration is None:
            raise RuntimeError("Engine has not been configured")
        if self._state is None or not self._state.is_open:
            await self.start()

        candle_price = self._select_price(market_data, self._configuration.price_source)
        candle_timestamp = market_data["timestamp"]
        brick_size = self._configuration.brick_size

        if self._pending_open_price is None:
            self._initialize_first_brick(candle_price)
            return

        movements = self._generate_bricks_from_price(candle_price, candle_timestamp, brick_size)
        for brick_data in movements:
            brick = await self._builder.build_brick(brick_data, self._configuration)
            self._brick_history.append(brick)
            await self._publish_brick_event(brick_data["event"], brick)
            self._state = BrickState(
                direction=brick.direction,
                last_price=brick.close_price,
                brick_size=brick_size,
                is_open=True,
                metadata={"last_brick_id": brick.brick_id},
            )

    async def get_snapshot(self) -> BrickSnapshot:
        if self._configuration is None or self._state is None:
            raise RuntimeError("Engine snapshot unavailable")
        return BrickSnapshot(
            configuration=self._configuration,
            state=self._state,
            timestamp=datetime.utcnow(),
            metadata={"brick_count": len(self._brick_history)},
        )

    def configure(self, configuration: BrickConfiguration) -> None:
        self._configuration = configuration
        self._state = BrickState(
            direction=BrickDirection.NEUTRAL,
            last_price=0.0,
            brick_size=configuration.brick_size,
            is_open=False,
            metadata={},
        )

    def history(self) -> tuple[Brick, ...]:
        return tuple(self._brick_history)

    def _select_price(self, market_data: dict[str, Any], source: PriceSource) -> float:
        if source == PriceSource.OPEN:
            return float(market_data["open"])
        if source == PriceSource.HIGH:
            return float(market_data["high"])
        if source == PriceSource.LOW:
            return float(market_data["low"])
        if source == PriceSource.CLOSE:
            return float(market_data["close"])
        if source == PriceSource.TYPICAL:
            return float((market_data["high"] + market_data["low"] + market_data["close"]) / 3.0)
        raise ValueError(f"Unsupported price source: {source}")

    def _initialize_first_brick(self, price: float) -> None:
        self._pending_open_price = price
        self._last_brick_boundary = price
        self._state = BrickState(
            direction=BrickDirection.NEUTRAL,
            last_price=price,
            brick_size=self._configuration.brick_size,
            is_open=True,
            metadata={"anchor_price": price},
        )

    def _generate_bricks_from_price(self, price: float, timestamp: datetime, brick_size: float) -> list[dict[str, Any]]:
        if self._pending_open_price is None or self._state is None:
            raise RuntimeError("Engine is not initialized for brick generation")

        bricks: list[dict[str, Any]] = []
        last_close = self._state.last_price
        direction = self._state.direction

        if direction == BrickDirection.NEUTRAL:
            direction = self._derive_initial_direction(price, last_close, brick_size)
            if direction is None:
                self._state = BrickState(
                    direction=BrickDirection.NEUTRAL,
                    last_price=price,
                    brick_size=brick_size,
                    is_open=True,
                    metadata=self._state.metadata,
                )
                return []

        movement = price - last_close
        steps = int(abs(movement) // brick_size)
        if steps == 0:
            self._state = BrickState(
                direction=direction,
                last_price=price,
                brick_size=brick_size,
                is_open=True,
                metadata=self._state.metadata,
            )
            return []

        trend_direction = BrickDirection.UP if movement > 0 else BrickDirection.DOWN
        reversal_threshold = 2 * brick_size
        reversed_direction = direction.opposite() if direction != BrickDirection.NEUTRAL else trend_direction

        if direction != trend_direction and abs(movement) >= reversal_threshold:
            bricks.extend(self._create_reversal_bricks(price, timestamp, brick_size, direction, trend_direction, steps))
        elif direction == trend_direction:
            bricks.extend(self._create_continuation_bricks(price, timestamp, brick_size, direction, steps))
        else:
            self._state = BrickState(
                direction=direction,
                last_price=price,
                brick_size=brick_size,
                is_open=True,
                metadata=self._state.metadata,
            )

        return bricks

    def _derive_initial_direction(self, price: float, last_close: float, brick_size: float) -> BrickDirection | None:
        if price - last_close >= brick_size:
            return BrickDirection.UP
        if last_close - price >= brick_size:
            return BrickDirection.DOWN
        return None

    def _create_continuation_bricks(
        self,
        price: float,
        timestamp: datetime,
        brick_size: float,
        direction: BrickDirection,
        steps: int,
    ) -> list[dict[str, Any]]:
        bricks: list[dict[str, Any]] = []
        open_price = self._state.last_price
        for step in range(1, steps + 1):
            close_price = open_price + brick_size if direction == BrickDirection.UP else open_price - brick_size
            bricks.append(
                {
                    "direction": direction,
                    "open_price": open_price,
                    "close_price": close_price,
                    "high_price": max(open_price, close_price),
                    "low_price": min(open_price, close_price),
                    "volume": 0.0,
                    "timestamp": timestamp,
                    "event": BrickOpened if step == 1 and len(self._brick_history) == 0 else BrickExtended,
                }
            )
            open_price = close_price
        return bricks

    def _create_reversal_bricks(
        self,
        price: float,
        timestamp: datetime,
        brick_size: float,
        previous_direction: BrickDirection,
        new_direction: BrickDirection,
        steps: int,
    ) -> list[dict[str, Any]]:
        bricks: list[dict[str, Any]] = []
        open_price = self._state.last_price
        for step in range(1, steps + 1):
            close_price = open_price + brick_size if new_direction == BrickDirection.UP else open_price - brick_size
            bricks.append(
                {
                    "direction": new_direction,
                    "open_price": open_price,
                    "close_price": close_price,
                    "high_price": max(open_price, close_price),
                    "low_price": min(open_price, close_price),
                    "volume": 0.0,
                    "timestamp": timestamp,
                    "event": BrickReversed if step == 1 else BrickExtended,
                }
            )
            open_price = close_price
        return bricks

    async def _publish_brick_event(self, event_type: type[BrickOpened | BrickExtended | BrickReversed], brick: Brick) -> None:
        if self._event_bus is None:
            return

        if event_type is BrickOpened:
            event = event_type(
                name=event_type.__name__,
                occurred_at=datetime.utcnow(),
                payload={},
                configuration=self._configuration,
                snapshot=await self.get_snapshot(),
            )
        else:
            event = event_type(
                name=event_type.__name__,
                occurred_at=datetime.utcnow(),
                payload={},
                configuration=self._configuration,
                snapshot=await self.get_snapshot(),
                brick=brick,
            )
        await self._event_bus.publish(event)
