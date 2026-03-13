"""
select.py — Select operation: query the CTP corpus by statistical descriptors.

Wraps :class:`~app.database.postgres.Database` queries with convenience
methods and result formatting for the FastAPI layer.

Example
~~~~~~~
.. code-block:: python

    from app.operations.select import CTPSelector

    selector = CTPSelector(db=database)
    total, ctps = selector.select(
        query=SelectQuery(
            intensity_range_mbps=[100.0, 3000.0],
            burstiness_pmr_range=[2.0, 5.0],
            temporal_correlation_min=0.3,
        ),
        limit=20,
    )
"""

from __future__ import annotations

import logging
from typing import List, Optional, Tuple

from app.database.postgres import Database
from app.models.ctp import CrossTrafficProfile
from app.models.descriptors import SelectQuery

logger = logging.getLogger(__name__)


class CTPSelector:
    """Query the CTP corpus using multi-dimensional statistical descriptors.

    Args:
        db: Initialised :class:`~app.database.postgres.Database` instance.
    """

    def __init__(self, db: Database) -> None:
        self._db = db

    def select(
        self,
        query: SelectQuery,
        limit: int = 50,
        offset: int = 0,
        order_by: str = "intensity",
    ) -> Tuple[int, List[CrossTrafficProfile]]:
        """Query the corpus and return matching CTPs.

        Args:
            query: Filter parameters (all optional).
            limit: Maximum results to return.
            offset: Pagination offset.
            order_by: Sort column (``intensity`` | ``burstiness`` |
                ``contributor_count`` | ``window_index``).

        Returns:
            Tuple ``(total_matched, list_of_ctps)`` where *total_matched* is
            the full count before applying *limit*/*offset*.
        """
        logger.debug(
            "CTP select: filter=%s limit=%d offset=%d order=%s",
            query.model_dump(exclude_none=True),
            limit,
            offset,
            order_by,
        )
        total, ctps = self._db.query_ctps(
            query=query,
            limit=limit,
            offset=offset,
            order_by=order_by,
        )
        logger.info("Select returned %d/%d CTP(s) matching the query.", len(ctps), total)
        return total, ctps

    def get_by_id(self, ctp_id: str) -> Optional[CrossTrafficProfile]:
        """Retrieve a single CTP by its unique identifier.

        Args:
            ctp_id: The ``ctp_id`` value assigned during extraction.

        Returns:
            :class:`~app.models.ctp.CrossTrafficProfile` or ``None`` if not found.
        """
        ctp = self._db.get_ctp(ctp_id)
        if ctp is None:
            logger.warning("CTP '%s' not found in corpus.", ctp_id)
        return ctp

    def list_all(
        self,
        limit: int = 50,
        offset: int = 0,
        order_by: str = "intensity",
    ) -> Tuple[int, List[CrossTrafficProfile]]:
        """Return a paginated listing of all CTPs in the corpus.

        Args:
            limit: Maximum results.
            offset: Pagination offset.
            order_by: Sort column.

        Returns:
            Tuple ``(total_count, list_of_ctps)``.
        """
        return self._db.list_ctps(limit=limit, offset=offset, order_by=order_by)

    def count(self, dataset_name: Optional[str] = None) -> int:
        """Return the total number of CTPs in the corpus.

        Args:
            dataset_name: If given, count only CTPs from this dataset.

        Returns:
            Integer row count.
        """
        return self._db.count_ctps(dataset_name=dataset_name)
