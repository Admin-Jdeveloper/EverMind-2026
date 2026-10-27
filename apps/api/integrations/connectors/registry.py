"""
MediaCompile — Connector Registry & Third-Party Policy Service.
Source of Truth: MediaCompile-prompt.md (Section 18: Phase 8 — Social and External Integrations)
"""

from typing import Dict, Any, List, Optional
from .base import BaseConnector
from .bookmarks import BookmarkConnector
from .youtube import YouTubeConnector
from .reddit import RedditConnector

_CONNECTORS: Dict[str, BaseConnector] = {
    "bookmarks": BookmarkConnector(),
    "youtube": YouTubeConnector(),
    "reddit": RedditConnector(),
}

# Policy-restricted / optional platform guidance
PLATFORM_POLICIES = {
    "x": {
        "name": "Twitter / X",
        "status": "manual_export_only",
        "description": "Direct automated sync requires enterprise API tiers. Use manual URL saving or upload your X account archive export.",
        "scopes": ["tweet.read", "bookmark.read"],
        "policy_notice": "Strictly adheres to X Developer Agreement. No unauthorized web scraping or credential harvesting."
    },
    "instagram": {
        "name": "Instagram",
        "status": "manual_export_only",
        "description": "Meta Graph API restricts personal saved bookmarks. Save post URLs directly or import via personal data archive.",
        "scopes": ["user_profile"],
        "policy_notice": "Strictly adheres to Meta Developer Policy. No login bypass or unofficial screen scraping."
    },
    "linkedin": {
        "name": "LinkedIn",
        "status": "manual_export_only",
        "description": "LinkedIn does not expose consumer bookmark APIs. Use the MediaCompile URL saver to archive articles and posts.",
        "scopes": ["r_liteprofile"],
        "policy_notice": "Strictly adheres to LinkedIn User Agreement."
    }
}

def get_connector(provider: str) -> Optional[BaseConnector]:
    """Retrieve active connector instance by provider slug."""
    return _CONNECTORS.get(provider.lower().strip())

def list_supported_connectors() -> List[Dict[str, Any]]:
    """Return catalogue of all active connectors and policy notices for optional platforms."""
    catalogue = [
        {
            "id": "bookmarks",
            "name": "Browser Bookmarks Import",
            "category": "Browser Imports",
            "status": "active",
            "status_label": "Fully Supported",
            "description": "Import bookmarks from Chrome, Firefox, Safari, Edge, or Brave via HTML or JSON export.",
            "scopes": ["import:bookmarks-file"],
            "supports_api_sync": False,
            "supports_file_import": True,
        },
        {
            "id": "youtube",
            "name": "YouTube Videos & Playlists",
            "category": "Video & Audio",
            "status": "active",
            "status_label": "OAuth & Takeout Export Supported",
            "description": "Sync saved videos, transcripts, and metadata via official YouTube Data API v3 or Google Takeout export.",
            "scopes": ["https://www.googleapis.com/auth/youtube.readonly"],
            "supports_api_sync": True,
            "supports_file_import": True,
        },
        {
            "id": "reddit",
            "name": "Reddit Saved Posts",
            "category": "Social Feeds",
            "status": "active",
            "status_label": "OAuth & GDPR Export Supported",
            "description": "Sync your saved posts and discussions via official Reddit OAuth or personal CSV/JSON archive export.",
            "scopes": ["identity", "read", "history"],
            "supports_api_sync": True,
            "supports_file_import": True,
        },
    ]

    for p_id, p_info in PLATFORM_POLICIES.items():
        catalogue.append({
            "id": p_id,
            "name": p_info["name"],
            "category": "Optional / Export Only",
            "status": p_info["status"],
            "status_label": "Manual Export Recommended",
            "description": p_info["description"],
            "scopes": p_info["scopes"],
            "policy_notice": p_info["policy_notice"],
            "supports_api_sync": False,
            "supports_file_import": False,
        })

    return catalogue
