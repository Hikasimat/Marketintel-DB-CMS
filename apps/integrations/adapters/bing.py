"""Bing Webmaster Tools isolated API adapter."""

from __future__ import annotations

import urllib.parse
from typing import Any

import requests

from apps.integrations.adapters.base import BaseSearchEngineAdapter


class BingWebmasterAdapter(BaseSearchEngineAdapter):
    """Adapter for Bing Webmaster Tools API.

    Supports:
    - Sitemap submission
    - URL batch submission (SubmitUrlBatch)
    """

    BASE_URL = "https://ssl.bing.com/webmaster/api.svc/json"

    def __init__(
        self,
        site_url: str,
        api_key: str,
        session: requests.Session | None = None,
    ) -> None:
        self.site_url = site_url.rstrip("/")
        self.api_key = api_key
        self.session = session or requests.Session()

    def _get_headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json; charset=utf-8",
            "User-Agent": "CMS-Bing-Webmaster-Adapter/1.0",
        }

    def submit_sitemap(self, sitemap_url: str) -> dict[str, Any]:
        """Submit XML sitemap to Bing Webmaster Tools."""
        params = {
            "siteUrl": self.site_url,
            "sitemapUrl": sitemap_url,
            "apikey": self.api_key,
        }
        query_string = urllib.parse.urlencode(params)
        url = f"{self.BASE_URL}/SubmitSitemap?{query_string}"

        resp = self.session.get(url, headers=self._get_headers(), timeout=10)
        if resp.status_code == 200:
            return {"status": "SUCCESS", "provider": "BING", "sitemap_url": sitemap_url}
        return {
            "status": "ERROR",
            "provider": "BING",
            "code": resp.status_code,
            "error": resp.text,
        }

    def submit_urls(self, urls: list[str]) -> dict[str, Any]:
        """Submit URLs to Bing Webmaster Tools via SubmitUrlbatch."""
        if not urls:
            return {"status": "SUCCESS", "provider": "BING", "submitted_count": 0}

        endpoint = f"{self.BASE_URL}/SubmitUrlbatch?apikey={self.api_key}"
        payload = {
            "siteUrl": self.site_url,
            "urlList": urls,
        }
        resp = self.session.post(endpoint, json=payload, headers=self._get_headers(), timeout=15)
        if resp.status_code == 200:
            return {
                "status": "SUCCESS",
                "provider": "BING",
                "submitted_count": len(urls),
            }
        return {
            "status": "ERROR",
            "provider": "BING",
            "code": resp.status_code,
            "error": resp.text,
        }
