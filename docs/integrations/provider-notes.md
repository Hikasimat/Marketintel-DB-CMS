# Search & Analytics Provider Integration Specifications

- **Review Date:** 2026-10-28
- **Status:** All provider adapters verified with deterministic mock suites; live credential inventory documented.

---

## 1. Google Search Console (GSC) API

- **Official API:** Google Search Console API v1 (`https://searchconsole.googleapis.com/v1/`)
- **Required OAuth Scopes:**
  - `https://www.googleapis.com/auth/webmasters.readonly` (Inspect URLs, verify site ownership)
  - `https://www.googleapis.com/auth/webmasters` (Submit and manage sitemaps)
- **Supported Operations:**
  - `sites.get`: Verify site ownership.
  - `sitemaps.submit`: Submit dynamic XML sitemap URLs.
  - `urlInspection.index.inspect`: Retrieve crawl and indexing status for published URLs.
- **Verification Status:** `MOCK-PASS` in test suite; live credentials require customer Google Cloud Project OAuth client ID.

---

## 2. Google Indexing API Constraint Notice

> [!IMPORTANT]
> **Google Indexing API Scope Limitation:**  
> The Google Indexing API (`https://indexing.googleapis.com/v3/urlNotifications:publish`) is officially restricted by Google strictly to pages containing **`JobPosting`** or **`BroadcastEvent`** structured data embedded in a `VideoObject`.  
> 
> The CMS Backend explicitly enforces this constraint and does **NOT** misuse the Google Indexing API for general website or article indexing (which violates Google's API Terms of Service). General indexing is handled through Google Search Console sitemap submission and automated IndexNow/Bing discovery.

---

## 3. Bing Webmaster Tools API & IndexNow

### Bing Webmaster Tools API
- **Official API:** Bing Webmaster API (`https://ssl.bing.com/webmaster/api.svc/json/`)
- **Authentication:** OAuth 2.0 (`wl.offline_access`, `bingads.manage`) or API Key.
- **Operations:** Site verification, XML sitemap submission, URL crawl status queries.
- **Verification Status:** `MOCK-PASS` in test suite (`tests/integrations/test_api.py`).

### IndexNow Protocol
- **Official Standard:** [IndexNow.org](https://www.indexnow.org/) protocol supported by Microsoft Bing, Yandex, Seznam, and Naver.
- **Authentication:** Hex-encoded 32–128 character API key hosted at `https://<verified_domain>/<api_key>.txt`.
- **Operations:** `POST https://api.indexnow.org/indexnow`
  ```json
  {
    "host": "www.example.com",
    "key": "294a50d2871f49e4a3b7593c683b708e",
    "keyLocation": "https://www.example.com/294a50d2871f49e4a3b7593c683b708e.txt",
    "urlList": [
      "https://www.example.com/blog/article-1",
      "https://www.example.com/blog/article-2"
    ]
  }
  ```
- **Verification Status:** `MOCK-PASS` in test suite (`tests/integrations/test_api.py`).

---

## 4. Google Analytics 4 (GA4) Data API

- **Official API:** Google Analytics Data API v1beta (`https://analyticsdata.googleapis.com/v1beta/`)
- **Required OAuth Scopes:**
  - `https://www.googleapis.com/auth/analytics.readonly`
- **Supported Operations:**
  - `properties.runReport`: Query aggregate page views, sessions, user counts, and engagement metrics.
- **Constraints:**
  - Bounded to allowlisted dimensions (`pagePath`, `date`, `deviceCategory`, `country`).
  - Max 10,000 rows per query with pagination.
- **Verification Status:** `MOCK-PASS` in test suite (`tests/analytics/test_ga4_reports.py`).

---

## 5. Live vs Mock Verification Inventory

| Provider / Integration | Mock Verification | Live Verification | Reason for Live Blocker |
|------------------------|-------------------|-------------------|-------------------------|
| **Google Search Console** | `MOCK-PASS` (`tests/integrations/`) | `BLOCKED` | Requires live GCP OAuth app with verified domain. |
| **Bing Webmaster Tools** | `MOCK-PASS` (`tests/integrations/`) | `BLOCKED` | Requires live Microsoft account and Bing Webmaster API key. |
| **IndexNow** | `MOCK-PASS` (`tests/integrations/`) | `BLOCKED` | Requires public DNS resolution for customer domains. |
| **Google Analytics 4** | `MOCK-PASS` (`tests/analytics/`) | `BLOCKED` | Requires active GA4 property ID and user credentials. |
| **GitHub App** | `MOCK-PASS` (`tests/github/`) | `BLOCKED` | Requires live registered GitHub App with private RSA key. |
| **PostgreSQL 16** | `LIVE-PASS` | `LIVE-PASS` | Verified live in local Docker Compose container. |
| **Redis 7** | `LIVE-PASS` | `LIVE-PASS` | Verified live in local Docker Compose container. |
