"""Bezier curve point calculation ported from humancursor."""

from __future__ import annotations

import math

from .math_utils import Vector


def _factorial(n: int) -> int:
    if n <= 1:
        return 1
    result = 1
    for i in range(2, n + 1):
        result *= i
    return result


def _binomial(n: int, k: int) -> float:
    return _factorial(n) / (_factorial(k) * _factorial(n - k))


def _bernstein_polynomial_point(x: float, i: int, n: int) -> float:
    return _binomial(n, i) * (x**i) * ((1 - x) ** (n - i))


def _bernstein_polynomial(points: list[Vector]):
    """Return a function that evaluates the Bezier curve at parameter t."""

    def evaluate(t: float) -> Vector:
        n = len(points) - 1
        x = 0.0
        y = 0.0
        for i, pt in enumerate(points):
            bern = _bernstein_polynomial_point(t, i, n)
            x += pt.x * bern
            y += pt.y * bern
        return Vector(x, y)

    return evaluate


def calculate_points_in_curve(n: int, points: list[Vector]) -> list[Vector]:
    """Given control points, return *n* points along the Bezier curve."""
    if n < 2:
        raise ValueError("n must be at least 2")

    curve_points: list[Vector] = []
    bernstein_poly = _bernstein_polynomial(points)

    for i in range(n):
        if i == 0:
            curve_points.append(points[0].copy())
        elif i == n - 1:
            curve_points.append(points[-1].copy())
        else:
            t = i / (n - 1)
            curve_points.append(bernstein_poly(t))

    return curve_points
