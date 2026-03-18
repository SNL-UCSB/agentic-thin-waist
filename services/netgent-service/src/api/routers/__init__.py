"""Router package for NetGent API subroutes."""

from .health import router as health_router
from .workflow import router as workflow_router

__all__ = ["workflow_router", "health_router"]
