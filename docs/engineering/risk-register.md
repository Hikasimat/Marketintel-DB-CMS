# Risk Register

Scale: Likelihood (L) and Impact (I) are rated 1–3. Score = L×I. Owner = SDE role.

| ID | Risk | L | I | Score | Mitigation / response | Owner | Status |
|----|------|---|---|-------|----------------------|-------|--------|
| R-01 | Docker engine not running on dev host, so PostgreSQL/Redis tests cannot run | 3 | 3 | 9 | User will start Docker Desktop (agreed in Stage 0). Stage 1 gate requires PG-backed tests; if Docker is unavailable, the gate is `BLOCKED` (not faked) | DevOps | OPEN |
| R-02 | Live provider credentials (Google, Bing, GitHub App, GA4) unavailable | 3 | 2 | 6 | Deterministic mocks + contract tests; live checks marked `BLOCKED`; documented in final report | Integration | ACCEPTED (expected) |
| R-03 | Provider API changes or doc drift (scopes, endpoints, Bing auth method) | 2 | 2 | 4 | Verify official docs at Stage 5/6/8 with dated `provider-notes.md`; adapters isolated | Integration | OPEN |
| R-04 | Python 3.14 is the host default; some deps may lack 3.14 wheels | 2 | 2 | 4 | Pin the runtime to 3.12/3.13 via `py -3.12`/`-3.13` venv and Docker image; record in Stage 1 | Architect | OPEN |
| R-05 | Workspace on OneDrive: file sync can lock files / slow venv and `.git` | 2 | 2 | 4 | Create venv outside OneDrive or exclude it; if issues appear, recommend moving the repo | DevOps | OPEN |
| R-06 | Scope size (10 stages, many integrations) leads to rushed, under-tested stages | 3 | 3 | 9 | Strict stage gates; stop for user review at agreed checkpoints; no stage combining | Orchestrator | OPEN |
| R-07 | Tenant isolation regression as apps grow | 2 | 3 | 6 | Central scoping helpers, generated IDOR suite over all families, grep test for unscoped managers in views | Security | OPEN |
| R-08 | SSRF via future features that fetch URLs (crawler/audit, IndexNow key check) | 2 | 3 | 6 | Single SafeClient egress path, forbidden-import test, SSRF suite | Security | OPEN |
| R-09 | Misleading claims about indexing/consent compliance | 2 | 3 | 6 | Status vocabulary, docs language review in every stage report | Requirements | OPEN |
| R-10 | Vite SPA customers expect SEO without prerendering | 3 | 2 | 6 | Rendering contract doc + integration guide caveat | Architect | OPEN |
| R-11 | Encryption key loss makes stored provider tokens unrecoverable | 1 | 3 | 3 | Key rotation list, backup guidance, re-auth flow documented | DevOps | OPEN |
| R-12 | GitHub integration expands the attack surface (private code, write access) | 2 | 3 | 6 | Feature flag off by default, minimal permissions, PR-only writes, hostile-repo tests | Security | OPEN |
| R-13 | Analytics/consent legal expectations differ by jurisdiction | 2 | 2 | 4 | Configurable behavior, explicit "not legal certification" docs | Requirements | ACCEPTED |
| R-14 | README references `.agents/skills/cms-backend-sde-workflow/` and `ANTIGRAVITY_BACKEND_PROJECT_PROMPT.md` at the root, but the actual paths are `.agents/skills/sde-workflow/` and `prompts/…` | 3 | 1 | 3 | Doc-only inconsistency; the skill still loads. Root README will be rewritten for the service in Stage 1 while preserving package notes | Orchestrator | OPEN |
| R-15 | No CI remote yet; CI workflow cannot be executed remotely | 3 | 1 | 3 | Run the CI-equivalent commands locally as gate evidence; CI marked unexecuted until a remote exists | DevOps | OPEN |
