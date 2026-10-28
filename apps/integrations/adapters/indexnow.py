"""IndexNow isolated protocol adapter."""

from __future__ import annotations

from typing import Any

import requests

from apps.integrations.adapters.base import BaseSearchEngineAdapter


class IndexNowAdapter(BaseSearchEngineAdapter):
    """Adapter for the IndexNow protocol (supported by Bing, Yandex, Naver, Seznam).

    Specification:
    - POST https://api.indexnow.org/indexnow
    - Content-Type: application/json; charset=utf-8
    - Max 10,000 URLs per submission
    - Successful HTTP responses: 200 (OK), 202 (Accepted)
    """

    ENDPOINT = "https://api.indexnow.org/indexnow"
    MAX_URLS = 10000

    def __init__(
        self,
        host: str,
        key: str,
        key_location: str | None = None,
        session: requests.Session | None = None,
    ) -> None:
        self.host = host
        self.key = key
        self.key_location = key_location or f"https://{host}/{key}.txt"
        self.session = session or requests.Session()

    def submit_sitemap(self, sitemap_url: str) -> dict[str, Any]:
        """IndexNow is URL-based, not sitemap-based."""
        raise NotImplementedError(
            "IndexNow does not support XML sitemap submissions. "
            "Submit article/page URLs directly via submit_urls."
        )

    def submit_urls(self, urls: list[str]) -> dict[str, Any]:
        """Submit batch of URLs to the IndexNow central endpoint."""
        if not urls:
            return {"status": "SUCCESS", "provider": "INDEXNOW", "submitted_count": 0}

        if len(urls) > self.MAX_URLS:
            raise ValueError(
                f"IndexNow batches cannot exceed {self.MAX_URLS} URLs. Received {len(urls)}."
            )

        payload = {
            "host": self.host,
            "key": self.key,
            "keyLocation": self.key_location,
            "urlList": urls,
        }
        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "User-Agent": "CMS-IndexNow-Adapter/1.0",
        }

        resp = self.session.post(self.ENDPOINT, json=payload, headers=headers, timeout=15)
        # 200: OK (URL submitted successfully)
        # 202: Accepted (URL received, IndexNow key pending validation)
        if resp.status_code in (200, 202):
            return {
                "status": "SUCCESS",
                "provider": "INDEXNOW",
                "code": resp.status_code,
                "submitted_count": len(urls),
            }

        return {
            "status": "ERROR",
            "provider": "INDEXNOW",
            "code": resp.status_code,
            "error": resp.text,
        }
