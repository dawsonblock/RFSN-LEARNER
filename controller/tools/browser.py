"""
Browser/network tools - fetch URLs, search web.

These are stubs that demonstrate the interface.
Real implementations would use httpx, playwright, etc.
"""

from __future__ import annotations

import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse


@dataclass(frozen=True)
class ToolResult:
    """Result from a tool execution."""

    success: bool
    output: Any
    error: str | None = None


def fetch_url(
    url: str,
    *,
    max_bytes: int = 100_000,
    timeout: int = 10,
) -> ToolResult:
    """Fetch content from a URL."""
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return ToolResult(False, None, f"Invalid scheme: {parsed.scheme}")

        req = urllib.request.Request(
            url,
            headers={"User-Agent": "RFSN-Agent/1.0"},
        )

        with urllib.request.urlopen(req, timeout=timeout) as response:
            content = response.read(max_bytes)

            # Try to decode as text
            charset = response.headers.get_content_charset() or "utf-8"
            try:
                text = content.decode(charset, errors="replace")
            except Exception:
                text = content.decode("utf-8", errors="replace")

            return ToolResult(
                True,
                {
                    "url": url,
                    "status": response.status,
                    "content_type": response.headers.get("Content-Type", ""),
                    "content": text[:max_bytes],
                    "truncated": len(content) >= max_bytes,
                },
            )

    except urllib.error.HTTPError as e:
        return ToolResult(False, None, f"HTTP {e.code}: {e.reason}")
    except urllib.error.URLError as e:
        return ToolResult(False, None, f"URL error: {e.reason}")
    except TimeoutError:
        return ToolResult(False, None, "Request timed out")
    except Exception as e:
        return ToolResult(False, None, str(e))


def search_web(query: str, *, max_results: int = 5) -> ToolResult:
    """
    Search the web (stub).

    Real implementation would use a search API.
    """
    # This is a stub - real implementation would call a search API
    return ToolResult(
        True,
        {
            "query": query,
            "results": [],
            "note": "Web search is a stub. Implement with your preferred search API.",
        },
    )


# Tool registry
BROWSER_TOOLS = {
    "fetch_url": fetch_url,
    "search_web": search_web,
}
