"""Google Ads API isolated client for GAQL queries, customer listing, and safe mutations."""

from __future__ import annotations

import logging
from typing import Any

import requests

logger = logging.getLogger(__name__)


class GoogleAdsAdapter:
    """Isolated client for Google Ads API v17 REST endpoints."""

    BASE_URL = "https://googleads.googleapis.com/v17"

    def __init__(
        self,
        customer_id: str,
        access_token: str,
        developer_token: str = "",
        manager_customer_id: str = "",
        session: requests.Session | None = None,
    ) -> None:
        self.customer_id = customer_id.replace("-", "").strip()
        self.access_token = access_token
        self.developer_token = developer_token or "mock-developer-token"
        self.manager_customer_id = manager_customer_id.replace("-", "").strip()
        self.session = session or requests.Session()

    def _get_headers(self) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "developer-token": self.developer_token,
            "Content-Type": "application/json",
            "User-Agent": "CMS-Google-Ads-Adapter/1.0",
        }
        if self.manager_customer_id:
            headers["login-customer-id"] = self.manager_customer_id
        return headers

    def list_accessible_customers(self) -> list[str]:
        """List customer resource names accessible to the OAuth token."""
        url = f"{self.BASE_URL}/customers:listAccessibleCustomers"
        try:
            resp = self.session.get(url, headers=self._get_headers(), timeout=15)
            if resp.status_code == 200:
                return resp.json().get("resourceNames", [])
        except requests.RequestException as exc:
            logger.error("Google Ads list_accessible_customers error: %s", exc)
        return []

    def query(self, query: str) -> list[dict[str, Any]]:
        """Execute a Google Ads Query Language (GAQL) search query."""
        if not self.customer_id:
            return []

        url = f"{self.BASE_URL}/customers/{self.customer_id}/googleAds:search"
        payload = {"query": query}

        try:
            resp = self.session.post(url, json=payload, headers=self._get_headers(), timeout=20)
            if resp.status_code == 200:
                data = resp.json()
                return data.get("results", [])
            logger.warning("GAQL query returned status %d: %s", resp.status_code, resp.text)
        except requests.RequestException as exc:
            logger.error("GAQL query network error: %s", exc)
        return []

    def get_campaigns(self, start_date: str, end_date: str) -> list[dict[str, Any]]:
        """Fetch campaign performance metrics using GAQL."""
        query = (
            "SELECT "  # noqa: S608
            "campaign.id, "
            "campaign.name, "
            "campaign.status, "
            "campaign_budget.amount_micros, "
            "metrics.impressions, "
            "metrics.clicks, "
            "metrics.cost_micros, "
            "metrics.conversions, "
            "metrics.ctr, "
            "metrics.average_cpc "
            "FROM campaign "
            f"WHERE segments.date BETWEEN '{start_date}' AND '{end_date}' "
            "ORDER BY metrics.impressions DESC"
        )
        results = self.query(query)
        campaigns = []
        for r in results:
            c = r.get("campaign", {})
            m = r.get("metrics", {})
            b = r.get("campaignBudget", {})
            cost_micros = int(m.get("costMicros", 0))
            campaigns.append(
                {
                    "campaign_id": str(c.get("id", "")),
                    "campaign_name": c.get("name", ""),
                    "status": c.get("status", "UNKNOWN"),
                    "budget_amount": float(b.get("amountMicros", 0)) / 1_000_000,
                    "impressions": int(m.get("impressions", 0)),
                    "clicks": int(m.get("clicks", 0)),
                    "cost": float(cost_micros) / 1_000_000,
                    "conversions": float(m.get("conversions", 0.0)),
                    "ctr": float(m.get("ctr", 0.0)),
                    "average_cpc": float(m.get("averageCpc", 0)) / 1_000_000,
                }
            )
        return campaigns

    def get_ad_groups(self, start_date: str, end_date: str) -> list[dict[str, Any]]:
        """Fetch ad group performance metrics using GAQL."""
        query = (
            "SELECT "  # noqa: S608
            "ad_group.id, "
            "ad_group.name, "
            "ad_group.status, "
            "campaign.id, "
            "campaign.name, "
            "metrics.impressions, "
            "metrics.clicks, "
            "metrics.cost_micros, "
            "metrics.conversions, "
            "metrics.ctr "
            "FROM ad_group "
            f"WHERE segments.date BETWEEN '{start_date}' AND '{end_date}' "
            "ORDER BY metrics.impressions DESC"
        )
        results = self.query(query)
        ad_groups = []
        for r in results:
            ag = r.get("adGroup", {})
            c = r.get("campaign", {})
            m = r.get("metrics", {})
            ad_groups.append(
                {
                    "ad_group_id": str(ag.get("id", "")),
                    "ad_group_name": ag.get("name", ""),
                    "status": ag.get("status", "UNKNOWN"),
                    "campaign_id": str(c.get("id", "")),
                    "campaign_name": c.get("name", ""),
                    "impressions": int(m.get("impressions", 0)),
                    "clicks": int(m.get("clicks", 0)),
                    "cost": float(m.get("costMicros", 0)) / 1_000_000,
                    "conversions": float(m.get("conversions", 0.0)),
                    "ctr": float(m.get("ctr", 0.0)),
                }
            )
        return ad_groups

    def get_keywords(self, start_date: str, end_date: str) -> list[dict[str, Any]]:
        """Fetch keyword performance metrics using GAQL."""
        query = (
            "SELECT "  # noqa: S608
            "ad_group_criterion.criterion_id, "
            "ad_group_criterion.keyword.text, "
            "ad_group_criterion.keyword.match_type, "
            "ad_group_criterion.status, "
            "metrics.impressions, "
            "metrics.clicks, "
            "metrics.cost_micros, "
            "metrics.conversions, "
            "metrics.average_cpc "
            "FROM keyword_view "
            f"WHERE segments.date BETWEEN '{start_date}' AND '{end_date}' "
            "ORDER BY metrics.clicks DESC"
        )
        results = self.query(query)
        keywords = []
        for r in results:
            crit = r.get("adGroupCriterion", {})
            kw = crit.get("keyword", {})
            m = r.get("metrics", {})
            keywords.append(
                {
                    "criterion_id": str(crit.get("criterionId", "")),
                    "keyword_text": kw.get("text", ""),
                    "match_type": kw.get("matchType", "UNKNOWN"),
                    "status": crit.get("status", "UNKNOWN"),
                    "impressions": int(m.get("impressions", 0)),
                    "clicks": int(m.get("clicks", 0)),
                    "cost": float(m.get("costMicros", 0)) / 1_000_000,
                    "conversions": float(m.get("conversions", 0.0)),
                    "average_cpc": float(m.get("averageCpc", 0)) / 1_000_000,
                }
            )
        return keywords

    def set_campaign_status(self, campaign_id: str, new_status: str) -> dict[str, Any]:
        """Mutate campaign status (PAUSED or ENABLED)."""
        clean_cid = str(campaign_id).strip()
        resource_name = f"customers/{self.customer_id}/campaigns/{clean_cid}"
        url = f"{self.BASE_URL}/customers/{self.customer_id}/campaigns:mutate"

        payload = {
            "operations": [
                {
                    "update": {
                        "resourceName": resource_name,
                        "status": new_status,
                    },
                    "updateMask": "status",
                }
            ]
        }
        try:
            resp = self.session.post(url, json=payload, headers=self._get_headers(), timeout=15)
            if resp.status_code == 200:
                return {"status": "SUCCESS", "campaign_id": clean_cid, "new_status": new_status}
            return {"status": "ERROR", "code": resp.status_code, "error": resp.text}
        except requests.RequestException as exc:
            return {"status": "ERROR", "code": 503, "error": str(exc)}

    def update_campaign_budget(
        self, budget_resource_name: str, amount_micros: int
    ) -> dict[str, Any]:
        """Update campaign budget amount in micros."""
        url = f"{self.BASE_URL}/customers/{self.customer_id}/campaignBudgets:mutate"
        payload = {
            "operations": [
                {
                    "update": {
                        "resourceName": budget_resource_name,
                        "amountMicros": str(amount_micros),
                    },
                    "updateMask": "amount_micros",
                }
            ]
        }
        try:
            resp = self.session.post(url, json=payload, headers=self._get_headers(), timeout=15)
            if resp.status_code == 200:
                return {
                    "status": "SUCCESS",
                    "resource_name": budget_resource_name,
                    "amount_micros": amount_micros,
                }
            return {"status": "ERROR", "code": resp.status_code, "error": resp.text}
        except requests.RequestException as exc:
            return {"status": "ERROR", "code": 503, "error": str(exc)}
