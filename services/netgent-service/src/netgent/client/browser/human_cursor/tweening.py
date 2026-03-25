"""Easing/tweening functions ported from the humancursor implementation."""

from __future__ import annotations

import math
from typing import Callable

TweeningFunction = Callable[[float], float]


def linear(t: float) -> float:
    return t


def ease_in_quad(t: float) -> float:
    return t * t


def ease_out_quad(t: float) -> float:
    return t * (2 - t)


def ease_in_out_quad(t: float) -> float:
    if t < 0.5:
        return 2 * t * t
    return -1 + (4 - 2 * t) * t


def ease_in_cubic(t: float) -> float:
    return t * t * t


def ease_out_cubic(t: float) -> float:
    t1 = t - 1
    return t1 * t1 * t1 + 1


def ease_in_out_cubic(t: float) -> float:
    if t < 0.5:
        return 4 * t * t * t
    t1 = 2 * t - 2
    return (t1 * t1 * t1 + 2) / 2


def ease_in_quart(t: float) -> float:
    return t**4


def ease_out_quart(t: float) -> float:
    t1 = t - 1
    return 1 - t1**4


def ease_in_out_quart(t: float) -> float:
    if t < 0.5:
        return 8 * t**4
    t1 = t - 1
    return 1 - 8 * t1**4


def ease_in_quint(t: float) -> float:
    return t**5


def ease_out_quint(t: float) -> float:
    t1 = t - 1
    return 1 + t1**5


def ease_in_out_quint(t: float) -> float:
    if t < 0.5:
        return 16 * t**5
    t1 = t - 1
    return 1 + 16 * t1**5


def ease_in_sine(t: float) -> float:
    return 1 - math.cos((t * math.pi) / 2)


def ease_out_sine(t: float) -> float:
    return math.sin((t * math.pi) / 2)


def ease_in_out_sine(t: float) -> float:
    return -(math.cos(math.pi * t) - 1) / 2


def ease_in_expo(t: float) -> float:
    if t == 0:
        return 0.0
    return 2 ** (10 * t - 10)


def ease_out_expo(t: float) -> float:
    if t == 1:
        return 1.0
    return 1 - 2 ** (-10 * t)


def ease_in_out_expo(t: float) -> float:
    if t == 0:
        return 0.0
    if t == 1:
        return 1.0
    if t < 0.5:
        return 2 ** (20 * t - 10) / 2
    return (2 - 2 ** (-20 * t + 10)) / 2


def ease_in_circ(t: float) -> float:
    return 1 - math.sqrt(1 - t**2)


def ease_out_circ(t: float) -> float:
    return math.sqrt(1 - (t - 1) ** 2)


def ease_in_out_circ(t: float) -> float:
    if t < 0.5:
        return (1 - math.sqrt(1 - (2 * t) ** 2)) / 2
    return (math.sqrt(1 - (-2 * t + 2) ** 2) + 1) / 2


TWEEN_OPTIONS: list[TweeningFunction] = [
    ease_out_expo,
    ease_in_out_quint,
    ease_in_out_sine,
    ease_in_out_quart,
    ease_in_out_expo,
    ease_in_out_cubic,
    ease_in_out_circ,
    linear,
    ease_out_sine,
    ease_out_quart,
    ease_out_quint,
    ease_out_cubic,
    ease_out_circ,
]
