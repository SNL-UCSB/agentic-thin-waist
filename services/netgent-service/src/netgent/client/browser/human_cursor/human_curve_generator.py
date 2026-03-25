"""Generates human-like mouse trajectory curves using Bezier curves with distortion and tweening."""

from __future__ import annotations

import math
import random

from .bezier_calculator import calculate_points_in_curve
from .math_utils import Vector
from .tweening import TweeningFunction, ease_out_quad


class HumanizeMouseTrajectory:
    """Produce a list of ``Vector`` points that trace a realistic mouse path."""

    def __init__(
        self,
        from_point: Vector,
        to_point: Vector,
        *,
        offset_boundary_x: float = 80,
        offset_boundary_y: float = 80,
        left_boundary: float | None = None,
        right_boundary: float | None = None,
        down_boundary: float | None = None,
        up_boundary: float | None = None,
        knots_count: int = 2,
        distortion_mean: float = 1.0,
        distortion_st_dev: float = 1.0,
        distortion_frequency: float = 0.5,
        tweening: TweeningFunction = ease_out_quad,
        target_points: int = 100,
    ) -> None:
        self.from_point = from_point
        self.to_point = to_point

        lb = (
            left_boundary
            if left_boundary is not None
            else min(from_point.x, to_point.x) - offset_boundary_x
        )
        rb = (
            right_boundary
            if right_boundary is not None
            else max(from_point.x, to_point.x) + offset_boundary_x
        )
        db = (
            down_boundary
            if down_boundary is not None
            else min(from_point.y, to_point.y) - offset_boundary_y
        )
        ub = (
            up_boundary
            if up_boundary is not None
            else max(from_point.y, to_point.y) + offset_boundary_y
        )

        internal_knots = self._generate_internal_knots(lb, rb, db, ub, knots_count)
        points = self._generate_points(internal_knots)
        points = self._distort_points(
            points, distortion_mean, distortion_st_dev, distortion_frequency
        )
        self.points = self._tween_points(points, tweening, target_points)

    # ------------------------------------------------------------------

    def _generate_internal_knots(
        self,
        l_boundary: float,
        r_boundary: float,
        d_boundary: float,
        u_boundary: float,
        knots_count: int,
    ) -> list[Vector]:
        if l_boundary > r_boundary:
            raise ValueError("left_boundary must be <= right_boundary")
        if d_boundary > u_boundary:
            raise ValueError("down_boundary must be <= upper_boundary")
        knots_count = max(knots_count, 0)

        knots: list[Vector] = []
        for _ in range(knots_count):
            x = random.randint(int(l_boundary), int(r_boundary))
            y = random.randint(int(d_boundary), int(u_boundary))
            knots.append(Vector(float(x), float(y)))
        return knots

    def _generate_points(self, knots: list[Vector]) -> list[Vector]:
        distance = math.sqrt(
            (self.to_point.x - self.from_point.x) ** 2
            + (self.to_point.y - self.from_point.y) ** 2
        )
        mid_pts_cnt = max(int(distance), 50)
        all_knots = [self.from_point] + knots + [self.to_point]
        return calculate_points_in_curve(mid_pts_cnt, all_knots)

    @staticmethod
    def _distort_points(
        points: list[Vector],
        distortion_mean: float,
        distortion_st_dev: float,
        distortion_frequency: float,
    ) -> list[Vector]:
        if not (0 <= distortion_frequency <= 1):
            raise ValueError("distortion_frequency must be in [0, 1]")

        distorted: list[Vector] = [points[0].copy()]
        for pt in points[1:-1]:
            delta = (
                random.gauss(distortion_mean, distortion_st_dev)
                if random.random() < distortion_frequency
                else 0.0
            )
            distorted.append(Vector(pt.x, pt.y + delta))
        distorted.append(points[-1].copy())
        return distorted

    @staticmethod
    def _tween_points(
        points: list[Vector],
        tween: TweeningFunction,
        target_points: int,
    ) -> list[Vector]:
        if target_points < 2:
            raise ValueError("target_points must be >= 2")
        if len(points) <= target_points:
            return list(points)

        result: list[Vector] = []
        for i in range(target_points):
            if i == 0:
                result.append(points[0].copy())
                continue
            if i == target_points - 1:
                result.append(points[-1].copy())
                continue

            t = i / (target_points - 1)
            tweened_t = tween(t)

            continuous_index = tweened_t * (len(points) - 1)
            lower_idx = int(continuous_index)
            upper_idx = min(lower_idx + 1, len(points) - 1)
            frac = continuous_index - lower_idx

            lp = points[lower_idx]
            up = points[upper_idx]
            result.append(
                Vector(
                    lp.x + (up.x - lp.x) * frac,
                    lp.y + (up.y - lp.y) * frac,
                )
            )
        return result
