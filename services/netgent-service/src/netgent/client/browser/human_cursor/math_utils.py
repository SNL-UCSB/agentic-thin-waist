"""Basic vector and math utilities for human-cursor."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class Vector:
    x: float
    y: float

    def __add__(self, other: Vector) -> Vector:
        return Vector(self.x + other.x, self.y + other.y)

    def copy(self) -> Vector:
        return Vector(self.x, self.y)


@dataclass
class TimedVector(Vector):
    timestamp: float = 0.0


ORIGIN = Vector(0, 0)


def scale(
    value: float, range1: tuple[float, float], range2: tuple[float, float]
) -> float:
    return (value - range1[0]) * (range2[1] - range2[0]) / (
        range1[1] - range1[0]
    ) + range2[0]


def clamp(target: float, min_val: float, max_val: float) -> float:
    return min(max_val, max(min_val, target))
