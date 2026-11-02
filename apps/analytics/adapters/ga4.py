"""Google Analytics 4 Data API and Admin API isolated reporting adapter (ANA-2, ANA-3)."""

from __future__ import annotations

import logging
from typing import Any

import requests

logger = logging.getLogger(__name__)


class GA4ReportingAdapter:
    """Isolated client for Google Analytics Data API v1beta."""

    BASE_URL = "https://analyticsdata.googleapis.com/v1beta"

    def __init__(
        self,
        property_id: str,
        access_token: str,
        session: requests.Session | None = None,
    ) -> None:
        self.property_id = property_id.removeprefix("properties/")
        self.access_token = access_token
        self.session = session or requests.Session()

    def _get_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
            "User-Agent": "CMS-GA4-Reporting-Adapter/1.0",
        }

    def run_report(
        self,
        start_date: str,
        end_date: str,
        metrics: list[str],
        dimensions: list[str] | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        """Execute runReport against Google Analytics Data API v1beta."""
        endpoint = f"{self.BASE_URL}/properties/{self.property_id}:runReport"

        payload: dict[str, Any] = {
            "dateRanges": [{"startDate": start_date, "endDate": end_date}],
            "metrics": [{"name": m} for m in metrics],
            "limit": min(limit, 1000),
        }
        if dimensions:
            payload["dimensions"] = [{"name": d} for d in dimensions]

        try:
            resp = self.session.post(
                endpoint, json=payload, headers=self._get_headers(), timeout=15
            )
        except requests.RequestException as exc:
            logger.error("GA4 Data API network error: %s", exc)
            return {
                "status": "ERROR",
                "code": 503,
                "error": f"Upstream connection failed: {exc}",
            }

        if resp.status_code == 200:
            data = resp.json()
            metric_headers = [h.get("name") for h in data.get("metricHeaders", [])]
            dimension_headers = [h.get("name") for h in data.get("dimensionHeaders", [])]

            rows = []
            for r in data.get("rows", []):
                dim_values = [v.get("value") for v in r.get("dimensionValues", [])]
                met_values = [v.get("value") for v in r.get("metricValues", [])]
                row_dict: dict[str, Any] = {}
                for idx, dh in enumerate(dimension_headers):
                    if idx < len(dim_values):
                        row_dict[dh] = dim_values[idx]
                for idx, mh in enumerate(metric_headers):
                    if idx < len(met_values):
                        row_dict[mh] = met_values[idx]
                rows.append(row_dict)

            return {
                "status": "SUCCESS",
                "property_id": self.property_id,
                "date_range": {"start_date": start_date, "end_date": end_date},
                "row_count": data.get("rowCount", len(rows)),
                "rows": rows,
            }

        logger.warning("GA4 Data API returned error code %d: %s", resp.status_code, resp.text)
        return {
            "status": "ERROR",
            "code": resp.status_code,
            "error": resp.text,
        }

    def run_realtime_report(
        self,
        metrics: list[str],
        dimensions: list[str] | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        """Execute runRealtimeReport against Google Analytics Data API v1beta."""
        endpoint = f"{self.BASE_URL}/properties/{self.property_id}:runRealtimeReport"

        payload: dict[str, Any] = {
            "metrics": [{"name": m} for m in metrics],
            "limit": min(limit, 1000),
        }
        if dimensions:
            payload["dimensions"] = [{"name": d} for d in dimensions]

        try:
            resp = self.session.post(
                endpoint, json=payload, headers=self._get_headers(), timeout=15
            )
        except requests.RequestException as exc:
            logger.error("GA4 Realtime Data API network error: %s", exc)
            return {
                "status": "ERROR",
                "code": 503,
                "error": f"Upstream connection failed: {exc}",
            }

        if resp.status_code == 200:
            data = resp.json()
            metric_headers = [h.get("name") for h in data.get("metricHeaders", [])]
            dimension_headers = [h.get("name") for h in data.get("dimensionHeaders", [])]

            rows = []
            for r in data.get("rows", []):
                dim_values = [v.get("value") for v in r.get("dimensionValues", [])]
                met_values = [v.get("value") for v in r.get("metricValues", [])]
                row_dict: dict[str, Any] = {}
                for idx, dh in enumerate(dimension_headers):
                    if idx < len(dim_values):
                        row_dict[dh] = dim_values[idx]
                for idx, mh in enumerate(metric_headers):
                    if idx < len(met_values):
                        row_dict[mh] = met_values[idx]
                rows.append(row_dict)

            return {
                "status": "SUCCESS",
                "property_id": self.property_id,
                "row_count": data.get("rowCount", len(rows)),
                "rows": rows,
            }

        return {
            "status": "ERROR",
            "code": resp.status_code,
            "error": resp.text,
        }

    def get_overview(self, start_date: str, end_date: str) -> dict[str, Any]:
        """Fetch standard traffic and engagement overview."""
        metrics = [
            "activeUsers",
            "sessions",
            "screenPageViews",
            "engagementRate",
            "bounceRate",
            "averageSessionDuration",
        ]
        return self.run_report(start_date=start_date, end_date=end_date, metrics=metrics)

    def get_traffic_sources(self, start_date: str, end_date: str) -> dict[str, Any]:
        """Fetch acquisition breakdown by channel, source, and medium."""
        metrics = ["sessions", "activeUsers", "newUsers"]
        dimensions = ["sessionDefaultChannelGroup", "sessionSource", "sessionMedium"]
        return self.run_report(
            start_date=start_date,
            end_date=end_date,
            metrics=metrics,
            dimensions=dimensions,
        )

    def get_top_pages(self, start_date: str, end_date: str) -> dict[str, Any]:
        """Fetch top pages breakdown by pagePath and pageTitle."""
        metrics = ["screenPageViews", "activeUsers", "userEngagementDuration"]
        dimensions = ["pagePath", "pageTitle"]
        return self.run_report(
            start_date=start_date,
            end_date=end_date,
            metrics=metrics,
            dimensions=dimensions,
        )

    def get_audience(self, start_date: str, end_date: str) -> dict[str, Any]:
        """Fetch audience demographics, devices, and countries."""
        metrics = ["activeUsers", "sessions"]
        dimensions = ["country", "city", "deviceCategory", "operatingSystem"]
        return self.run_report(
            start_date=start_date,
            end_date=end_date,
            metrics=metrics,
            dimensions=dimensions,
        )

    def get_events(self, start_date: str, end_date: str) -> dict[str, Any]:
        """Fetch event breakdown by eventName."""
        metrics = ["eventCount", "totalUsers"]
        dimensions = ["eventName"]
        return self.run_report(
            start_date=start_date,
            end_date=end_date,
            metrics=metrics,
            dimensions=dimensions,
        )

    def get_realtime(self) -> dict[str, Any]:
        """Fetch realtime active users in the last 30 minutes."""
        metrics = ["activeUsers"]
        dimensions = ["country", "city", "unifiedScreenName"]
        return self.run_realtime_report(metrics=metrics, dimensions=dimensions)


class GA4AdminAdapter:
    """Isolated client for Google Analytics Admin API v1beta."""

    BASE_URL = "https://analyticsadmin.googleapis.com/v1beta"

    def __init__(self, access_token: str, session: requests.Session | None = None) -> None:
        self.access_token = access_token
        self.session = session or requests.Session()

    def _get_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
            "User-Agent": "CMS-GA4-Admin-Adapter/1.0",
        }

    def list_account_summaries(self) -> list[dict[str, Any]]:
        """List GA4 accounts and properties accessible to the authorized user."""
        endpoint = f"{self.BASE_URL}/accountSummaries"
        try:
            resp = self.session.get(endpoint, headers=self._get_headers(), timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                summaries = []
                for acc in data.get("accountSummaries", []):
                    account_name = acc.get("displayName", "")
                    for prop in acc.get("propertySummaries", []):
                        raw_id = prop.get("property", "")
                        clean_id = raw_id.removeprefix("properties/")
                        summaries.append(
                            {
                                "account_name": account_name,
                                "property_id": clean_id,
                                "property_name": prop.get("displayName", ""),
                                "property_resource": raw_id,
                            }
                        )
                return summaries
        except requests.RequestException as exc:
            logger.error("GA4 Admin API list_account_summaries error: %s", exc)
        return []

    def list_data_streams(self, property_id: str) -> list[dict[str, Any]]:
        """List web data streams and their measurement IDs for a GA4 property."""
        clean_prop_id = property_id.removeprefix("properties/")
        endpoint = f"{self.BASE_URL}/properties/{clean_prop_id}/dataStreams"
        try:
            resp = self.session.get(endpoint, headers=self._get_headers(), timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                streams = []
                for ds in data.get("dataStreams", []):
                    web_stream = ds.get("webStreamData", {})
                    measurement_id = web_stream.get("measurementId", "")
                    streams.append(
                        {
                            "stream_name": ds.get("displayName", ""),
                            "stream_type": ds.get("type", ""),
                            "measurement_id": measurement_id,
                            "default_uri": web_stream.get("defaultUri", ""),
                        }
                    )
                return streams
        except requests.RequestException as exc:
            logger.error("GA4 Admin API list_data_streams error: %s", exc)
        return []
