"""Google Search Console isolated API adapter."""

from __future__ import annotations

import logging
import urllib.parse
from typing import Any

import requests

from apps.integrations.adapters.base import BaseSearchEngineAdapter

logger = logging.getLogger(__name__)


class GoogleSearchConsoleAdapter(BaseSearchEngineAdapter):
    """Adapter for Google Search Console API.

    Adheres strictly to official documentation:
    - Sites & Properties listing via Webmasters API sites.list
    - Sitemaps management via Webmasters API sitemaps endpoints
    - Search Analytics performance via searchAnalytics.query
    - URL status inspection via URL Inspection API
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

    def list_sites(self) -> list[dict[str, Any]]:
        """List all verified and accessible sites/properties in Search Console."""
        url = "https://www.googleapis.com/webmasters/v3/sites"
        try:
            resp = self.session.get(url, headers=self._get_headers(), timeout=15)
            if resp.status_code == 200:
                entries = resp.json().get("siteEntry", [])
                results = []
                for entry in entries:
                    raw_url = entry.get("siteUrl", "")
                    is_domain = raw_url.startswith("sc-domain:")
                    results.append(
                        {
                            "site_url": raw_url,
                            "type": "DOMAIN" if is_domain else "URL_PREFIX",
                            "permission_level": entry.get("permissionLevel", "siteFullUser"),
                        }
                    )
                return results
        except requests.RequestException as exc:
            logger.error("GSC list_sites network error: %s", exc)
        return []

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

    def list_sitemaps(self) -> list[dict[str, Any]]:
        """List all sitemaps submitted for this site/property."""
        encoded_site = urllib.parse.quote_plus(self.site_url)
        url = f"https://www.googleapis.com/webmasters/v3/sites/{encoded_site}/sitemaps"
        try:
            resp = self.session.get(url, headers=self._get_headers(), timeout=15)
            if resp.status_code == 200:
                return resp.json().get("sitemap", [])
        except requests.RequestException as exc:
            logger.error("GSC list_sitemaps network error: %s", exc)
        return []

    def delete_sitemap(self, sitemap_url: str) -> dict[str, Any]:
        """Delete a sitemap from Google Search Console."""
        encoded_site = urllib.parse.quote_plus(self.site_url)
        encoded_sitemap = urllib.parse.quote_plus(sitemap_url)
        url = f"https://www.googleapis.com/webmasters/v3/sites/{encoded_site}/sitemaps/{encoded_sitemap}"
        try:
            resp = self.session.delete(url, headers=self._get_headers(), timeout=10)
            if resp.status_code in (200, 204):
                return {"status": "SUCCESS", "message": "Sitemap deleted successfully."}
            return {"status": "ERROR", "code": resp.status_code, "error": resp.text}
        except requests.RequestException as exc:
            return {"status": "ERROR", "code": 503, "error": str(exc)}

    def query_search_analytics(
        self,
        start_date: str,
        end_date: str,
        dimensions: list[str] | None = None,
        row_limit: int = 1000,
        search_type: str = "web",
        start_row: int = 0,
    ) -> dict[str, Any]:
        """Query Search Analytics performance data (clicks, impressions, ctr, position)."""
        encoded_site = urllib.parse.quote_plus(self.site_url)
        url = f"https://www.googleapis.com/webmasters/v3/sites/{encoded_site}/searchAnalytics/query"

        payload: dict[str, Any] = {
            "startDate": start_date,
            "endDate": end_date,
            "rowLimit": min(row_limit, 25000),
            "startRow": max(start_row, 0),
            "type": search_type,
        }
        if dimensions:
            payload["dimensions"] = dimensions

        try:
            resp = self.session.post(url, json=payload, headers=self._get_headers(), timeout=20)
            if resp.status_code == 200:
                data = resp.json()
                raw_rows = data.get("rows", [])
                formatted_rows = []
                dim_names = dimensions or []
                for r in raw_rows:
                    keys = r.get("keys", [])
                    entry: dict[str, Any] = {
                        "clicks": r.get("clicks", 0),
                        "impressions": r.get("impressions", 0),
                        "ctr": r.get("ctr", 0.0),
                        "position": r.get("position", 0.0),
                    }
                    for idx, d_name in enumerate(dim_names):
                        if idx < len(keys):
                            entry[d_name] = keys[idx]
                    formatted_rows.append(entry)

                return {
                    "status": "SUCCESS",
                    "site_url": self.site_url,
                    "date_range": {"start_date": start_date, "end_date": end_date},
                    "search_type": search_type,
                    "row_count": len(formatted_rows),
                    "rows": formatted_rows,
                }
            return {"status": "ERROR", "code": resp.status_code, "error": resp.text}
        except requests.RequestException as exc:
            return {"status": "ERROR", "code": 503, "error": str(exc)}

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
