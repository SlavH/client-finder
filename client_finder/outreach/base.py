"""Channel registry base."""

from __future__ import annotations

from typing import Any

CHANNEL_REGISTRY: dict[str, type] = {}


def register_channel(cls: type) -> type:
    CHANNEL_REGISTRY[cls.name] = cls
    return cls