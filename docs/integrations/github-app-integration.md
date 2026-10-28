# GitHub App Integration Architecture & Operational Guide

## Overview

The CMS Backend provides an isolated, enterprise-grade integration with GitHub through a dedicated GitHub App. This allows customers to connect frontend repository codebases to their headless CMS sites, automatically detect framework configurations, and open non-destructive Pull Requests with boilerplate client code.

The integration is fully feature-flagged (`GITHUB_APP_ENABLED`), tenant-isolated, and enforces strict security invariants when handling untrusted customer repository contents.

---

## Architectural Invariants & Security Principles

### 1. Zero Code Execution on Untrusted Repositories (GH-3)
Customer repositories and manifests (`package.json`, configuration files) are treated as **untrusted data**:
- **No Subprocess/Shell Execution:** The service never executes `npm install`, `npm build`, `eval()`, `exec()`, or subshell commands.
- **Data-Only Manifest Parsing:** Manifests are parsed using safe JSON and static AST/string inspection.
- **Strict Payload Limits:** Manifest files fetched from GitHub are strictly capped at **500 KB** (`MAX_MANIFEST_SIZE_BYTES = 512,000`). Oversized files are rejected before parsing.
- **Anti-Traversal & Sanitization:** Manifest paths are checked against directory traversal (`..`), absolute roots, Windows drive specifications, and null-byte (`\0`) injection.

### 2. Non-Destructive Pull Request Workflow (GH-4)
- **Isolated Branch Creation:** The system strictly creates a dedicated non-default branch (`cms-integration-{site_slug}` or user-specified safe branch).
- **Default Branch Immutability:** Commits are **never** written directly to the target default or base branch (`main`, `master`).
- **No Auto-Merge or Auto-Deploy:** Pull Requests require manual human review and approval by the repository maintainer. The CMS Backend never issues merge or deploy API calls.

### 3. Signed Inbound Webhooks & Replay Defense (GH-6)
- **HMAC-SHA256 Verification:** Inbound GitHub webhooks at `/api/v1/webhooks/github/` verify the `X-Hub-Signature-256` header against `GITHUB_APP_WEBHOOK_SECRET` using constant-time comparison (`hmac.compare_digest`).
- **Delivery ID Deduplication:** Every webhook delivery records its `X-GitHub-Delivery` ID in the `GitHubWebhookDelivery` table. Duplicate delivery IDs from replays or network retries are acknowledged safely without re-processing.
- **Automated Secret Scrubbing:** Sensitive keys (`private_key`, `github_private_key`, `webhook_secret`) are automatically redacted from structured logs and audit records via `apps/common/logging.py`.

### 4. Feature Flag Gating (GH-7)
When `GITHUB_APP_ENABLED=false` (the default in self-hosted or minimal environments), all integration routes reject requests with HTTP 403 Forbidden.

---

## Supported Frontend Frameworks (GH-3, GH-5)

| Framework | Detection Manifests / Dependencies | Generated Patch Files |
|-----------|-------------------------------------|-----------------------|
| **Next.js** | `next` in dependencies or `next.config.*` | `cms.config.json`, `lib/cms.ts` |
| **Vite (React)** | `vite` + `react` in dependencies or `vite.config.*` | `cms.config.json`, `src/cmsClient.ts` |
| **Astro** | `astro` in dependencies or `astro.config.*` | `cms.config.json`, `src/lib/cms.js` |
| **Nuxt** | `nuxt` in dependencies or `nuxt.config.*` | `cms.config.json`, `cms-client.js` |
| **Remix** | `@remix-run/react` or `remix.config.*` | `cms.config.json`, `cms-client.js` |
| **Unsupported** | Missing or non-matching dependencies | Returns `manual_integration_required=true` and link to manual guide |

---

## API Endpoints

### 1. Webhooks
- `POST /api/v1/webhooks/github/`: Inbound GitHub App webhook receiver (handles `installation`, `installation_repositories`).

### 2. Workspace GitHub App Installations
- `GET /api/v1/workspaces/{workspace_id}/github/installations/`: List active authorized installations for the workspace.
- `POST /api/v1/workspaces/{workspace_id}/github/installations/`: Register newly authorized GitHub App installation (Admin/Owner only).
- `GET /api/v1/workspaces/{workspace_id}/github/installations/{installation_id}/`: Retrieve installation details.
- `DELETE /api/v1/workspaces/{workspace_id}/github/installations/{installation_id}/`: Deactivate installation and disconnect sites.
- `GET /api/v1/workspaces/{workspace_id}/github/installations/{installation_id}/repositories/`: List accessible repositories under the installation.

### 3. Site Repository Connections
- `GET /api/v1/workspaces/{workspace_id}/sites/{site_id}/github/connection/`: View site repository connection details.
- `DELETE /api/v1/workspaces/{workspace_id}/sites/{site_id}/github/connection/`: Disconnect repository from site.
- `POST /api/v1/workspaces/{workspace_id}/sites/{site_id}/github/connect/`: Connect repository and branch to site.
- `POST /api/v1/workspaces/{workspace_id}/sites/{site_id}/github/analyze/`: Trigger safe static framework analysis.
- `POST /api/v1/workspaces/{workspace_id}/sites/{site_id}/github/open-pr/`: Generate integration branch and open Pull Request.

---

## Verification & Audit Trail
All mutations (`GITHUB_APP_INSTALLED`, `GITHUB_APP_UNINSTALLED`, `GITHUB_REPO_CONNECTED`, `GITHUB_REPO_DISCONNECTED`, `GITHUB_FRAMEWORK_ANALYZED`, `GITHUB_PR_OPENED`) create immutable records in the `audit_event` log table with tenant scoping and secret scrubbing.
