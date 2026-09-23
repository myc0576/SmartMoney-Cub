"""Read-only account connection layer for the global journal."""

from .adapters import FixtureConnection, all_fixture_adapters, fixture_adapter
from .manifests import CONNECTION_MANIFESTS, get_manifest, list_manifests
from .manager import ConnectionManager
from .ccxt import CCXTConnection
from .ibkr import FlexTransport, IBKRFlexConnection
from .snaptrade import MCPTransport, SnapTradeOAuthClient, SnapTradePersonalMCPConnection as SnapTradeMCPConnection
SnapTradePersonalMCPConnection = SnapTradeMCPConnection
from .models import (
    AuthSpec,
    ConnectionAccount,
    ConnectionCursor,
    ConnectionManifest,
    CredentialBundle,
    EventPage,
    HistorySpec,
    NormalizedEvent,
    NormalizedPosition,
    OfficialLink,
    ScopeValidation,
    SyncResult,
    ValidationStatus,
    validate_read_scope,
)
from .protocol import ConnectionError, PermissionConnectionError, ReadOnlyConnection, TransientConnectionError
from .providers import (
    CCXTReadOnlyConnection,
    StructuralTransport,
    TransportConnection,
)
from .mt5 import MetaTraderInvestorConnection
from .local_statements import LocalStatementConnection
from .vezgo import VezgoConnection
from .sync import SyncEngine, SyncState

__all__ = [
    "AuthSpec",
    "CONNECTION_MANIFESTS",
    "ConnectionAccount",
    "ConnectionCursor",
    "ConnectionError",
    "ConnectionManifest",
    "ConnectionManager",
    "CredentialBundle",
    "EventPage",
    "FixtureConnection",
    "CCXTReadOnlyConnection",
    "CCXTConnection",
    "HistorySpec",
    "IBKRFlexConnection",
    "FlexTransport",
    "LocalStatementConnection",
    "MetaTraderInvestorConnection",
    "NormalizedEvent",
    "NormalizedPosition",
    "OfficialLink",
    "PermissionConnectionError",
    "ReadOnlyConnection",
    "ScopeValidation",
    "SnapTradePersonalMCPConnection",
    "SnapTradeMCPConnection",
    "MCPTransport",
    "SnapTradeOAuthClient",
    "StructuralTransport",
    "SyncEngine",
    "SyncResult",
    "SyncState",
    "TransientConnectionError",
    "TransportConnection",
    "VezgoConnection",
    "ValidationStatus",
    "all_fixture_adapters",
    "fixture_adapter",
    "get_manifest",
    "list_manifests",
    "validate_read_scope",
]
