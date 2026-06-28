from __future__ import annotations

import dataclasses
from datetime import datetime
from enum import Enum
from typing import Any, Dict

from backend.app.chart.renko.configuration import (
    BrickConfiguration,
    BrickType,
    PriceSource,
    ReferencePrice,
    RenkoMode,
    RoundingMode,
)
from backend.app.chart.renko.models import Brick, BrickDirection, BrickState

"""Persistence serialization boundary.

Snapshot persistence must not be coupled to how the domain models happen to be
implemented. This module is the single place that knows how to turn the domain
models (BrickConfiguration / Brick / BrickState) into JSON-compatible dicts and
back. It adapts to the model representation in use:

* Pydantic models  -> ``model_dump(mode="json")`` / ``model_validate`` (v2) or
  ``dict()`` / ``parse_obj`` (v1).
* dataclasses      -> field introspection + explicit enum/datetime coercion.

The domain models therefore need no serialization API of their own, and swapping
the model framework does not touch the engine or the snapshot layer.
"""


# --------------------------------------------------------------------------- #
# Generic helpers
# --------------------------------------------------------------------------- #

def _jsonify(value: Any) -> Any:
    """Recursively convert enums/datetimes/containers into JSON-safe values."""
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _jsonify(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonify(item) for item in value]
    return value


def _to_plain_dict(obj: Any) -> Dict[str, Any]:
    """Encode a domain model to a JSON-safe dict, regardless of framework."""
    # Pydantic v2.
    model_dump = getattr(obj, "model_dump", None)
    if callable(model_dump):
        return model_dump(mode="json")
    # Pydantic v1.
    pydantic_dict = getattr(obj, "dict", None)
    if callable(pydantic_dict) and hasattr(obj, "__fields__"):
        return _jsonify(pydantic_dict())
    # dataclass: shallow field iteration + _jsonify (handles enums/datetimes and
    # copies nested dicts/lists). Avoids dataclasses.asdict's recursive deepcopy,
    # which dominates snapshot creation for large histories. Output is identical
    # for these models (no nested-dataclass fields).
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {f.name: _jsonify(getattr(obj, f.name)) for f in dataclasses.fields(obj)}
    raise TypeError(f"Cannot serialize object of type {type(obj)!r}")


def _from_plain_dict(model_cls: type, data: Dict[str, Any], enum_fields: Dict[str, type]):
    """Decode a JSON-safe dict back into a domain model, regardless of framework."""
    if not isinstance(data, dict):
        raise TypeError(f"Expected a mapping for {model_cls.__name__}, got {type(data)!r}")

    # Pydantic v2.
    model_validate = getattr(model_cls, "model_validate", None)
    if callable(model_validate):
        return model_validate(data)
    # Pydantic v1.
    parse_obj = getattr(model_cls, "parse_obj", None)
    if callable(parse_obj) and hasattr(model_cls, "__fields__"):
        return parse_obj(data)
    # dataclass: coerce enum-valued strings back into enums, keep only known fields.
    if dataclasses.is_dataclass(model_cls):
        field_names = {f.name for f in dataclasses.fields(model_cls)}
        kwargs: Dict[str, Any] = {}
        for key, value in data.items():
            if key not in field_names:
                continue
            if key in enum_fields and value is not None and not isinstance(value, Enum):
                kwargs[key] = enum_fields[key](value)
            else:
                kwargs[key] = value
        return model_cls(**kwargs)
    raise TypeError(f"Cannot deserialize into {model_cls!r}")


# --------------------------------------------------------------------------- #
# BrickConfiguration
# --------------------------------------------------------------------------- #

_CONFIG_ENUM_FIELDS: Dict[str, type] = {
    "brick_type": BrickType,
    "price_source": PriceSource,
    "mode": RenkoMode,
    "reference_price": ReferencePrice,
    "rounding_mode": RoundingMode,
}


def configuration_to_dict(configuration: BrickConfiguration) -> Dict[str, Any]:
    return _to_plain_dict(configuration)


def configuration_from_dict(data: Dict[str, Any]) -> BrickConfiguration:
    return _from_plain_dict(BrickConfiguration, data, _CONFIG_ENUM_FIELDS)


# --------------------------------------------------------------------------- #
# Brick
# --------------------------------------------------------------------------- #

_BRICK_ENUM_FIELDS: Dict[str, type] = {"direction": BrickDirection}


def brick_to_dict(brick: Brick) -> Dict[str, Any]:
    return _to_plain_dict(brick)


def brick_from_dict(data: Dict[str, Any]) -> Brick:
    if not isinstance(data, dict):
        raise TypeError(f"Expected a mapping for Brick, got {type(data)!r}")
    # ``created_at`` is an ISO string in the persisted form; normalise it for the
    # dataclass path (Pydantic coerces strings itself).
    prepared = dict(data)
    created_at = prepared.get("created_at")
    if isinstance(created_at, str) and not _has_pydantic(Brick):
        prepared["created_at"] = datetime.fromisoformat(created_at)
    return _from_plain_dict(Brick, prepared, _BRICK_ENUM_FIELDS)


# --------------------------------------------------------------------------- #
# BrickState
# --------------------------------------------------------------------------- #

_STATE_ENUM_FIELDS: Dict[str, type] = {"direction": BrickDirection}


def brick_state_to_dict(state: BrickState) -> Dict[str, Any]:
    return _to_plain_dict(state)


def brick_state_from_dict(data: Dict[str, Any]) -> BrickState:
    return _from_plain_dict(BrickState, data, _STATE_ENUM_FIELDS)


def _has_pydantic(model_cls: type) -> bool:
    return callable(getattr(model_cls, "model_validate", None)) or (
        callable(getattr(model_cls, "parse_obj", None)) and hasattr(model_cls, "__fields__")
    )
