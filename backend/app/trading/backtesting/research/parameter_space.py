"""Parameter-space expansion utilities for institutional research.

The optimizer receives a single deterministic stream of parameter dictionaries.
Reserved infrastructure keys are kept in the same dictionary so each trial can
be fully reproduced, while the optimizer later separates strategy constructor
parameters from risk/brick/engine parameters.
"""

from __future__ import annotations

import itertools
from decimal import Decimal
from typing import Iterable, Mapping, Sequence

from pydantic import Field, field_validator, model_validator

from backend.app.trading.backtesting.research.models import ResearchModel, ResearchScalar

_RESERVED_PARAMETER_KEYS = frozenset(
    {
        "atr",
        "atr_multiple",
        "brick_size",
        "brick_type",
        "fixed_quantity",
        "leverage",
        "max_open_positions",
        "position_fraction",
        "risk_percent",
        "stop_loss",
        "take_profit",
        "timeframe",
        "trailing_stop",
        "trailing_stop_percent",
    }
)


class ParameterAxis(ResearchModel):
    """One named optimization axis."""

    name: str = Field(min_length=1)
    values: tuple[ResearchScalar, ...]

    @field_validator("name")
    @classmethod
    def _normalize_name(cls, value: str) -> str:
        name = value.strip()
        if not name:
            raise ValueError("parameter axis name cannot be blank")
        return name

    @model_validator(mode="after")
    def _validate_values(self) -> "ParameterAxis":
        if not self.values:
            raise ValueError("parameter axis requires at least one value")
        return self


class ParameterSet(ResearchModel):
    """One deterministic parameter combination."""

    values: Mapping[str, ResearchScalar] = Field(default_factory=dict)

    @field_validator("values", mode="before")
    @classmethod
    def _normalize_values(cls, value: Mapping[str, ResearchScalar] | None) -> dict[str, ResearchScalar]:
        if value is None:
            return {}
        return {str(key): item for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}

    @property
    def strategy_values(self) -> dict[str, ResearchScalar]:
        """Return non-reserved values intended for strategy constructors."""
        return {key: value for key, value in self.values.items() if key not in _RESERVED_PARAMETER_KEYS}

    @property
    def infrastructure_values(self) -> dict[str, ResearchScalar]:
        """Return reserved values consumed by the research/backtest layer."""
        return {key: value for key, value in self.values.items() if key in _RESERVED_PARAMETER_KEYS}


class ParameterSpace(ResearchModel):
    """Deterministic Cartesian product of optimization axes."""

    axes: tuple[ParameterAxis, ...] = Field(default_factory=tuple)

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, Sequence[ResearchScalar]]) -> "ParameterSpace":
        """Build a parameter space from a mapping of name to candidate values."""
        axes = tuple(ParameterAxis(name=str(name), values=tuple(values)) for name, values in sorted(mapping.items()))
        return cls(axes=axes)

    @classmethod
    def single(cls, values: Mapping[str, ResearchScalar] | None = None) -> "ParameterSpace":
        """Build a single-combination parameter space."""
        if not values:
            return cls()
        return cls.from_mapping({key: (value,) for key, value in values.items()})

    @classmethod
    def standard_grid(
        cls,
        *,
        ema_periods: Sequence[int] = (),
        atr_periods: Sequence[int] = (),
        renko_brick_sizes: Sequence[float] = (),
        risk_percents: Sequence[float] = (),
        stop_losses: Sequence[float] = (),
        take_profits: Sequence[float] = (),
        trailing_stops: Sequence[float] = (),
    ) -> "ParameterSpace":
        """Build the standard Sprint 8 research grid."""
        grid: dict[str, Sequence[ResearchScalar]] = {}
        if ema_periods:
            grid["period"] = tuple(int(value) for value in ema_periods)
        if atr_periods:
            grid["atr_period"] = tuple(int(value) for value in atr_periods)
        if renko_brick_sizes:
            grid["brick_size"] = tuple(float(value) for value in renko_brick_sizes)
        if risk_percents:
            grid["risk_percent"] = tuple(float(value) for value in risk_percents)
        if stop_losses:
            grid["stop_loss"] = tuple(float(value) for value in stop_losses)
        if take_profits:
            grid["take_profit"] = tuple(float(value) for value in take_profits)
        if trailing_stops:
            grid["trailing_stop"] = tuple(float(value) for value in trailing_stops)
        return cls.from_mapping(grid)

    @property
    def is_empty(self) -> bool:
        """Return whether this space has no axes."""
        return len(self.axes) == 0

    def combinations(self) -> tuple[ParameterSet, ...]:
        """Return deterministic parameter combinations."""
        if not self.axes:
            return (ParameterSet(),)
        names = tuple(axis.name for axis in self.axes)
        value_lists = tuple(axis.values for axis in self.axes)
        combinations = []
        for values in itertools.product(*value_lists):
            combinations.append(ParameterSet(values=dict(zip(names, values))))
        return tuple(combinations)

    def extend(self, axes: Iterable[ParameterAxis]) -> "ParameterSpace":
        """Return a new space with additional axes appended and name-sorted."""
        axis_by_name = {axis.name: axis for axis in self.axes}
        for axis in axes:
            axis_by_name[axis.name] = axis
        return ParameterSpace(axes=tuple(axis_by_name[name] for name in sorted(axis_by_name)))


def coerce_float(value: ResearchScalar, default: float | None = None) -> float | None:
    """Return a float for numeric research scalars."""
    if value is None or isinstance(value, bool):
        return default
    if isinstance(value, (int, float, Decimal)):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


__all__ = [
    "ParameterAxis",
    "ParameterSet",
    "ParameterSpace",
    "coerce_float",
]
