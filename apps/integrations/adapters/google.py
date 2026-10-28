"""Google Search Console isolated API adapter."""

from __future__ import annotations

import urllib.parse
from typing import Any

import requests

from apps.integrations.adapters.base import BaseSearchEngineAdapter


class GoogleSearchConsoleAdapter(BaseSearchEngineAdapter):
    """Adapter for Google Search Console API.

    Adheres strictly to official documentation:
    - Sitemaps are submitted via the Webmasters API.
    - URL status is inspected via the URL Inspection API.
    - Google's Indexing API is NOT used for standard articles, as official
      Google documentation restricts it to JobPosting and BroadcastEvent metadata.
    """

    def __init__(
        self,
        site_url: str,
        access_token: str,
        session: requests.Session | None = None,
    ) -> None:
        self.site_url = site_url.rstrip("/")
        self.access_token = access_token
        self.session = session or requests.Session()

    def _get_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
            "User-Agent": "CMS-Search-Console-Adapter/1.0",
        }

    def submit_sitemap(self, sitemap_url: str) -> dict[str, Any]:
        """Submit XML sitemap to Google Search Console via Webmasters API."""
        encoded_site = urllib.parse.quote_plus(self.site_url)
        encoded_sitemap = urllib.parse.quote_plus(sitemap_url)
        url = f"https://www.googleapis.com/webmasters/v3/sites/{encoded_site}/sitemaps/{encoded_sitemap}"

        resp = self.session.put(url, headers=self._get_headers(), timeout=10)
        if resp.status_code in (200, 204):
            return {"status": "SUCCESS", "provider": "GOOGLE", "sitemap_url": sitemap_url}
        return {
            "status": "ERROR",
            "provider": "GOOGLE",
            "code": resp.status_code,
            "error": resp.text,
        }

    def inspect_url(self, url: str) -> dict[str, Any]:
        """Inspect indexing status of an article URL via Search Console URL Inspection API."""
        endpoint = "https://searchconsole.googleapis.com/v1/urlInspection/index:inspect"
        payload = {
            "inspectionUrl": url,
            "siteUrl": self.site_url,
        }
        resp = self.session.post(endpoint, json=payload, headers=self._get_headers(), timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            inspection_result = data.get("inspectionResult", {})
            index_status_result = inspection_result.get("indexStatusResult", {})
            return {
                "status": "SUCCESS",
                "provider": "GOOGLE",
                "verdict": index_status_result.get("verdict", "UNKNOWN"),
                "coverage_state": index_status_result.get("coverageState", "UNKNOWN"),
                "raw_result": data,
            }
        return {
            "status": "ERROR",
            "provider": "GOOGLE",
            "code": resp.status_code,
            "error": resp.text,
        }

    def submit_urls(self, urls: list[str]) -> dict[str, Any]:
        """Disallow arbitrary page submission per official Google guidelines."""
        raise ValueError(
            "Google Indexing API does not support standard article submissions. "
            "Google restricts this API exclusively to JobPosting and BroadcastEvent metadata. "
            "Use sitemap submission or URL Inspection instead."
        )
