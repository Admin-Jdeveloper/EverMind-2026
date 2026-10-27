"""
MediaCompile — Browser Bookmark Import Connector.
Source of Truth: MediaCompile-prompt.md (Section 18: Phase 8 — Priority 1: Manual URL saving & browser bookmark import)

Supports:
1. Standard Netscape HTML Bookmark exports (Chrome, Firefox, Safari, Edge, Brave).
2. JSON bookmark export structure.
3. SSRF safe URL validation and duplicate detection.
4. Automatic text chunking and vector embedding generation.
"""

import json
import logging
from bs4 import BeautifulSoup
from typing import Dict, Any, List
from urllib.parse import urlparse

from content.models import ContentItem, ContentChunk
from content.security import validate_safe_url, SSRFProtectionError
from content.services import chunk_text
from content.embeddings import get_embedding_provider
from .base import BaseConnector, SyncResult

logger = logging.getLogger(__name__)

class BookmarkConnector(BaseConnector):
    provider_name = "bookmarks"
    display_name = "Browser Bookmarks Import"
    required_scopes = ["import:bookmarks-file"]

    def test_connection(self, credentials: Dict[str, Any]) -> bool:
        return True

    def sync_content(self, user, credentials: Dict[str, Any], limit: int = 50) -> SyncResult:
        # Browser bookmarks are user-imported files, not a pull API
        return SyncResult(success=True, items_synced=0, details={"note": "Use import_export_data for bookmark files."})

    def import_export_data(self, user, data: Any) -> SyncResult:
        """
        Parse either Netscape HTML Bookmark format or JSON bookmark export.
        """
        if isinstance(data, bytes):
            try:
                data_str = data.decode('utf-8')
            except UnicodeDecodeError:
                data_str = data.decode('latin-1', errors='replace')
        else:
            data_str = str(data)

        # 1. Try parsing as JSON first
        trimmed = data_str.strip()
        if trimmed.startswith('{') or trimmed.startswith('['):
            try:
                parsed_json = json.loads(trimmed)
                return self._process_json_bookmarks(user, parsed_json)
            except json.JSONDecodeError:
                pass

        # 2. Parse as Netscape HTML
        return self._process_html_bookmarks(user, data_str)

    def _process_json_bookmarks(self, user, data: Any) -> SyncResult:
        """Process JSON bookmark list or tree."""
        bookmarks = []
        def extract_items(node):
            if isinstance(node, list):
                for item in node:
                    extract_items(item)
            elif isinstance(node, dict):
                url = node.get('url') or node.get('uri') or node.get('href')
                title = node.get('title') or node.get('name') or url
                if url:
                    bookmarks.append({
                        "url": str(url).strip(),
                        "title": str(title).strip() if title else str(url).strip(),
                        "folder": node.get('folder', 'Imported Bookmarks')
                    })
                if 'children' in node and isinstance(node['children'], list):
                    extract_items(node['children'])

        extract_items(data)
        return self._persist_bookmarks(user, bookmarks)

    def _process_html_bookmarks(self, user, html_content: str) -> SyncResult:
        """Parse Netscape HTML bookmark format via BeautifulSoup."""
        soup = BeautifulSoup(html_content, 'html.parser')
        links = soup.find_all('a')
        bookmarks = []

        for link in links:
            url = link.get('href', '').strip()
            if not url or url.startswith('javascript:') or url.startswith('place:'):
                continue

            title = link.get_text().strip() or url
            # Look for enclosing folder DL/H3 if available
            parent_h3 = link.find_previous('h3')
            folder = parent_h3.get_text().strip() if parent_h3 else "Imported Bookmarks"

            bookmarks.append({
                "url": url,
                "title": title,
                "folder": folder
            })

        return self._persist_bookmarks(user, bookmarks)

    def _persist_bookmarks(self, user, bookmarks: List[Dict[str, str]]) -> SyncResult:
        """Deduplicate, SSRF-validate, and ingest bookmarks into ContentItem."""
        embedding_provider = get_embedding_provider()
        synced = 0
        skipped = 0

        for b in bookmarks:
            url = b["url"]
            title = b["title"]

            # Validate URL protocol and SSRF safety
            try:
                validate_safe_url(url)
            except SSRFProtectionError:
                skipped += 1
                continue

            # Deduplication: check if already exists for this user
            if ContentItem.objects.filter(user=user, source_url=url).exists():
                skipped += 1
                continue

            item_text = f"{title}\nSource: {url}\nFolder: {b.get('folder', 'Imported')}"
            item = ContentItem.objects.create(
                user=user,
                content_type=ContentItem.TYPE_URL,
                source_url=url,
                title=title,
                raw_text=item_text,
                metadata={"imported_via": "browser_bookmarks", "folder": b.get("folder")},
                ingestion_status=ContentItem.STATUS_COMPLETED
            )

            # Chunk and embed so it is immediately searchable
            chunks = chunk_text(item_text, chunk_size=500, chunk_overlap=50)
            for idx, c in enumerate(chunks):
                emb = embedding_provider.embed_text(c["text"])
                ContentChunk.objects.create(
                    content_item=item,
                    chunk_index=idx,
                    text=c["text"],
                    start_offset=c["start_offset"],
                    end_offset=c["end_offset"],
                    embedding=emb
                )
            synced += 1

        return SyncResult(
            success=True,
            items_synced=synced,
            items_skipped=skipped,
            details={"total_parsed": len(bookmarks), "synced": synced, "skipped": skipped}
        )
