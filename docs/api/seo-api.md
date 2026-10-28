# Technical SEO Engine API Reference

## 1. SEO Settings & Canonical Validation

### Configure Site SEO Defaults
```http
PUT /api/v1/workspaces/{workspace_id}/sites/{site_id}/seo/settings/
Authorization: Bearer <access_token>
```
**Request:**
```json
{
  "title_template": "%s | Acme Tech Blog",
  "default_meta_description": "Engineering insights and headless architecture updates.",
  "default_robots": "index, follow",
  "default_og_image": "https://assets.acme.com/og-default.png"
}
```

### Configure Page-Level SEO & Canonical URL
```http
POST /api/v1/workspaces/{workspace_id}/sites/{site_id}/articles/{article_id}/seo/
Authorization: Bearer <access_token>
```
**Request:**
```json
{
  "meta_title": "Headless CMS Architecture Guide",
  "meta_description": "In-depth guide on decoupled headless CMS architecture.",
  "canonical_url": "https://blog.acme.com/getting-started-headless-cms",
  "robots_directive": "index, follow",
  "structured_data": {
    "@context": "https://schema.org",
    "@type": "Article",
    "headline": "Headless CMS Architecture Guide"
  }
}
```
Canonical URLs must match the site's verified domains or explicit cross-domain canonical allowlists.

---

## 2. Redirect Management & Cycle Detection

### Create URL Redirect
```http
POST /api/v1/workspaces/{workspace_id}/sites/{site_id}/seo/redirects/
Authorization: Bearer <access_token>
```
**Request:**
```json
{
  "source_path": "/old-blog/intro",
  "destination_url": "/getting-started-headless-cms",
  "http_status_code": 301
}
```
> [!NOTE]
> The backend automatically validates against self-redirects, cycles (`A -> B -> A`), and chain depths exceeding 5 hops.

---

## 3. Dynamic Sitemap & Robots.txt Delivery

### Public XML Sitemap
```http
GET /api/v1/public/sites/{site_slug}/sitemap.xml
```
**Response (200 OK, application/xml):**
```xml
<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>https://blog.acme.com/getting-started-headless-cms</loc>
    <lastmod>2026-10-28T12:30:00Z</lastmod>
    <changefreq>weekly</changefreq>
  </url>
</urlset>
```
Excludes drafts, future-scheduled posts, and pages with `noindex` directives.

### Public Robots.txt
```http
GET /api/v1/public/sites/{site_slug}/robots.txt
```
**Response (200 OK, text/plain):**
```text
User-agent: *
Allow: /

Sitemap: https://api.cms.example.com/api/v1/public/sites/acme-tech-blog/sitemap.xml
```

---

## 4. Automated Technical SEO Audit

```http
POST /api/v1/workspaces/{workspace_id}/sites/{site_id}/seo/audit/
Authorization: Bearer <access_token>
```
**Response (200 OK):**
```json
{
  "overall_score": 96,
  "pages_audited": 24,
  "issues": [
    {
      "severity": "WARNING",
      "article_id": "c1f7b882-628d-426b-8c65-27f7f035616e",
      "message": "Meta description length (42 chars) is below recommended 50-160 characters."
    }
  ]
}
```
