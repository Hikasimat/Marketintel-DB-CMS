"""Base search provider interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseSearchEngineAdapter(ABC):
    """Abstract search provider adapter enforcing isolated boundaries."""

    @abstractmethod
    def submit_sitemap(self, sitemap_url: str) -> dict[str, Any]:
        """Submit an XML sitemap to the search provider."""
        raise NotImplementedError

    @abstractmethod
    def submit_urls(self, urls: list[str]) -> dict[str, Any]:
        """Submit one or more article/page URLs for crawl priority or indexing."""
        raise NotImplementedError

    def inspect_url(self, url: str) -> dict[str, Any]:
        """Inspect indexing status for a single URL (if supported by provider)."""
        raise NotImplementedError("URL Inspection is not supported by this provider.")
