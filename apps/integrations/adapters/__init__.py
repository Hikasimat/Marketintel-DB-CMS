"""Search provider adapters package."""

from apps.integrations.adapters.base import BaseSearchEngineAdapter
from apps.integrations.adapters.bing import BingWebmasterAdapter
from apps.integrations.adapters.google import GoogleSearchConsoleAdapter
from apps.integrations.adapters.indexnow import IndexNowAdapter

__all__ = [
    "BaseSearchEngineAdapter",
    "BingWebmasterAdapter",
    "GoogleSearchConsoleAdapter",
    "IndexNowAdapter",
]
