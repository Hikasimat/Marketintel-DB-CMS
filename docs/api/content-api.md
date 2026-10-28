# Content Management & Delivery API Reference

## 1. Sites & Custom Domain Management

### Create Site
```http
POST /api/v1/workspaces/{workspace_id}/sites/
Authorization: Bearer <access_token>
```
**Request:**
```json
{
  "name": "Acme Tech Blog",
  "slug": "acme-tech-blog"
}
```

### Add Custom Domain & Initiate DNS TXT Verification
```http
POST /api/v1/workspaces/{workspace_id}/sites/{site_id}/domains/
Authorization: Bearer <access_token>
```
**Request:**
```json
{
  "hostname": "blog.acme.com"
}
```
**Response (201 Created):**
```json
{
  "id": "118fb48a-a279-44f2-9599-281ce13f3640",
  "hostname": "blog.acme.com",
  "status": "PENDING",
  "verification_txt_record": "cms-verification=37a1f592d37c4493b827e8a9f0294158"
}
```

### Verify Domain
```http
POST /api/v1/workspaces/{workspace_id}/sites/{site_id}/domains/{domain_id}/verify/
Authorization: Bearer <access_token>
```
Performs secure DNS lookup against the domain. Rejects private, loopback, or metadata IP ranges (SSRF defense).

---

## 2. Content Authoring & Publishing

### Create Draft Article
```http
POST /api/v1/workspaces/{workspace_id}/sites/{site_id}/articles/
Authorization: Bearer <access_token>
```
**Request:**
```json
{
  "title": "Getting Started with Headless CMS",
  "slug": "getting-started-headless-cms",
  "content": {
    "body": "This is a technical guide to our API-first architecture.",
    "author": "Tech Lead"
  }
}
```

### Publish Article
```http
POST /api/v1/workspaces/{workspace_id}/sites/{site_id}/articles/{article_id}/publish/
Authorization: Bearer <access_token>
```
- Creates an immutable published revision snapshot in `content_revision`.
- Enqueues asynchronous search engine discovery tasks (Google Search Console, IndexNow).

### Rollback to Prior Revision
```http
POST /api/v1/workspaces/{workspace_id}/sites/{site_id}/articles/{article_id}/revisions/{revision_id}/rollback/
Authorization: Bearer <access_token>
```

---

## 3. Public Content Delivery API (Read-Only)

Public content delivery endpoints are unauthenticated and rate-limited. They strictly expose **published articles only** and enforce CT-6 Origin header checks.

### Fetch Published Article by Slug
```http
GET /api/v1/public/sites/{site_slug}/articles/{article_slug}/
Origin: https://blog.acme.com
```
**Response (200 OK):**
```json
{
  "title": "Getting Started with Headless CMS",
  "slug": "getting-started-headless-cms",
  "content": {
    "body": "This is a technical guide to our API-first architecture.",
    "author": "Tech Lead"
  },
  "published_at": "2026-10-28T12:30:00Z"
}
```
If the article is in draft status, scheduled for the future, or the site slug is invalid, returns `HTTP 404 Not Found`.
