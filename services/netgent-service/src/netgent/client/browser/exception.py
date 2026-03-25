from __future__ import annotations


class BrowserClientError(RuntimeError):
    """Base exception for browser client failures."""


class BrowserConnectionError(BrowserClientError):
    """Raised when Playwright cannot connect to the CDP endpoint."""


class BrowserSessionError(BrowserClientError):
    """Raised when a browser session cannot be prepared or used."""


class BrowserSnapshotError(BrowserClientError):
    """Raised when a browser snapshot cannot be captured or parsed."""
