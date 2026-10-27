"""
MediaCompile — Base Social and External Connector Interface.
Source of Truth: MediaCompile-prompt.md (Section 18: Phase 8 — Social and External Integrations)
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field

@dataclass
class SyncResult:
    """Result summary of a connector sync or import operation."""
    success: bool
    items_synced: int = 0
    items_skipped: int = 0
    error_message: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)

class BaseConnector(ABC):
    """Abstract base class for all authorized third-party and export connectors."""

    provider_name: str = ""
    display_name: str = ""
    required_scopes: List[str] = []

    @abstractmethod
    def test_connection(self, credentials: Dict[str, Any]) -> bool:
        """Verify validity of third-party credentials/tokens."""
        pass

    @abstractmethod
    def sync_content(self, user, credentials: Dict[str, Any], limit: int = 50) -> SyncResult:
        """Execute on-demand or background sync from external authorized source."""
        pass

    @abstractmethod
    def import_export_data(self, user, data: Any) -> SyncResult:
        """Process user-supplied export file (JSON/HTML/CSV)."""
        pass
