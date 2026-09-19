from __future__ import annotations


class JevError(Exception):
    """Base exception for all Jev engine operations."""


class JevUnavailable(JevError):
    """Raised when a Jev backend is unavailable, unconfigured, or offline."""


class JevProtocolError(JevError):
    """Raised when a Jev backend returns malformed data or violates the expected contract."""
