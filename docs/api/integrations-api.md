# External Search & GitHub Integrations API Reference

## 1. Search Provider Integrations (GSC, Bing, IndexNow)

### Connect Search Provider Credential
```http
POST /api/v1/workspaces/{workspace_id}/sites/{site_id}/integrations/providers/
Authorization: Bearer <access_token>
```
**Request (IndexNow):**
```json
{
  "provider_type": "INDEXNOW",
  "api_key": "294a50d2871f49e4a3b7593c683b708e"
}
```
**Request (Google Search Console OAuth):**
```json
{
  "provider_type": "GOOGLE_SEARCH_CONSOLE",
  "oauth_code": "4/0AeanS0...",
  "redirect_uri": "https://admin.example.com/oauth/callback"
}
```
All tokens and credentials are encrypted using AES-256-GCM envelope encryption prior to persistence. Plaintext secrets are never returned in responses or logs.

### Trigger Immediate Search Indexing Notification
```http
POST /api/v1/workspaces/{workspace_id}/sites/{site_id}/integrations/index-now/
Authorization: Bearer <access_token>
```
**Request:**
```json
{
  "urls": [
    "https://blog.acme.com/getting-started-headless-cms"
  ]
}
```
Enqueues an asynchronous Celery task with exponential backoff and jitter.

### Query Indexing Job Status
```http
GET /api/v1/workspaces/{workspace_id}/sites/{site_id}/integrations/jobs/{job_id}/
Authorization: Bearer <access_token>
```
**Response (200 OK):**
```json
{
  "id": "e3a89041-3b7c-48d6-95f2-95f082e668da",
  "provider_type": "INDEXNOW",
  "status": "COMPLETED",
  "urls_submitted": 1,
  "attempt_count": 1,
  "created_at": "2026-10-28T12:35:00Z"
}
```

---

## 2. GitHub App Integration Endpoints (Feature-Flagged)

Requires `GITHUB_APP_ENABLED=true`.

### Connect GitHub Repository to Site
```http
POST /api/v1/workspaces/{workspace_id}/sites/{site_id}/github/connect/
Authorization: Bearer <access_token>
```
**Request:**
```json
{
  "installation_id": 12345,
  "repo_full_name": "acme-corp/nextjs-frontend",
  "selected_branch": "main"
}
```

### Analyze Repository Framework
```http
POST /api/v1/workspaces/{workspace_id}/sites/{site_id}/github/analyze/
Authorization: Bearer <access_token>
```
**Response (200 OK):**
```json
{
  "detected_framework": "NEXT_JS",
  "confidence": "HIGH",
  "manual_integration_required": false,
  "integration_guide_url": "https://docs.cms.internal/integrations/nextjs",
  "reason": "Detected NEXT_JS from package.json and configuration manifests.",
  "manifest_summary": {
    "package_name": "nextjs-frontend",
    "framework": "NEXT_JS",
    "dependencies_count": 12
  }
}
```

### Open Non-Destructive Integration Pull Request
```http
POST /api/v1/workspaces/{workspace_id}/sites/{site_id}/github/open-pr/
Authorization: Bearer <access_token>
```
**Request:**
```json
{
  "pr_title": "Setup CMS Integration Client",
  "commit_message": "Add CMS boilerplate configuration"
}
```
**Response (201 Created):**
```json
{
  "pr_number": 42,
  "pr_url": "https://github.com/acme-corp/nextjs-frontend/pull/42",
  "base_branch": "main",
  "new_branch": "cms-integration-acme-tech-blog",
  "committed_files": [
    "cms.config.json",
    "lib/cms.ts"
  ]
}
```
Commits are strictly written to the new integration branch; the default branch is never modified directly.
