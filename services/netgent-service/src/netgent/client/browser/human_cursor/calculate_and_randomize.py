"""Random parameter generation for human-like cursor curves."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import TypeVar

from .math_utils import Vector
from .tweening import TweeningFunction, TWEEN_OPTIONS

T = TypeVar("T")


@dataclass
class RandomCurveParameters:
    offset_boundary_x: float
    offset_boundary_y: float
    knots_count: int
    distortion_mean: float
    distortion_st_dev: float
    distortion_frequency: float
    tween: TweeningFunction
    target_points: int


def _weighted_random_choice(items: list[T], weights: list[float]) -> T:
    total = sum(weights)
    r = random.random() * total
    for item, w in zip(items, weights):
        r -= w
        if r <= 0:
            return item
    return items[-1]


def _random_from_range(min_val: int, max_val: int) -> int:
    return random.randint(min_val, max_val)


def generate_random_curve_parameters(
    pre_origin: Vector, post_destination: Vector
) -> RandomCurveParameters:
    """Generate randomised Bezier-curve parameters (mirrors the TS implementation)."""

    tween = random.choice(TWEEN_OPTIONS)

    # Offset boundary X – weighted random selection
    x_ranges = [
        (20, 44),
        (45, 74),
        (75, 99),
    ]
    x_weights = [0.2, 0.65, 15.0]
    sel = _weighted_random_choice(x_ranges, x_weights)
    offset_boundary_x = float(_random_from_range(*sel))

    # Offset boundary Y – weighted random selection
    y_ranges = [
        (20, 44),
        (45, 74),
        (75, 99),
    ]
    y_weights = [0.2, 0.65, 15.0]
    sel = _weighted_random_choice(y_ranges, y_weights)
    offset_boundary_y = float(_random_from_range(*sel))

    # Knots count
    knots_options = list(range(1, 11))
    knots_weights = [0.15, 0.36, 0.17, 0.12, 0.08, 0.04, 0.03, 0.02, 0.015, 0.005]
    knots_count: int = _weighted_random_choice(knots_options, knots_weights)

    # Distortion parameters
    distortion_mean = _random_from_range(80, 109) / 100
    distortion_st_dev = _random_from_range(85, 109) / 100
    distortion_frequency = _random_from_range(25, 69) / 100

    # Target points
    tp_ranges = [
        (35, 44),
        (45, 59),
        (60, 79),
    ]
    tp_weights = [0.53, 0.32, 0.15]
    sel = _weighted_random_choice(tp_ranges, tp_weights)
    target_points = _random_from_range(*sel)

    # Ensure minimum curve variation
    distance = math.sqrt(
        (post_destination.x - pre_origin.x) ** 2
        + (post_destination.y - pre_origin.y) ** 2
    )
    min_boundary = max(30.0, distance * 0.15)
    offset_boundary_x = max(offset_boundary_x, min_boundary)
    offset_boundary_y = max(offset_boundary_y, min_boundary)

    knots_count = max(knots_count, 2)

    return RandomCurveParameters(
        offset_boundary_x=offset_boundary_x,
        offset_boundary_y=offset_boundary_y,
        knots_count=knots_count,
        distortion_mean=distortion_mean,
        distortion_st_dev=distortion_st_dev,
        distortion_frequency=distortion_frequency,
        tween=tween,
        target_points=target_points,
    )
