# Antigravity CMS Backend Development Package

This package contains a reusable Antigravity skill and a full backend-only project prompt for a standalone headless CMS service with SEO, search-engine integrations, GA4 reporting, cookie consent, and privacy-conscious visitor analytics.

## Contents

- `.agents/skills/cms-backend-sde-workflow/SKILL.md` — reusable SDE workflow skill with role assignments, required stage gates, security review, test matrix, and evidence-based reporting.
- `ANTIGRAVITY_BACKEND_PROJECT_PROMPT.md` — detailed implementation prompt for the standalone backend service.

## Install the skill into a project

Copy the `.agents/` folder from this package into the root of your Antigravity workspace. The resulting path should be:

```text
<project-root>/.agents/skills/cms-backend-sde-workflow/SKILL.md
```

Antigravity's documented default workspace skill location is `.agents/skills`. Current guidance and format: https://www.antigravity.google/docs/skills

## Use the project prompt

Open the target backend repository in Antigravity, ensure the skill above is inside the workspace, then paste the contents of `ANTIGRAVITY_BACKEND_PROJECT_PROMPT.md` into the agent. You can explicitly mention `/cms-backend-sde-workflow` if your Antigravity surface supports skill slash commands.

## Scope notes

- Backend only: no React admin interface, no consent banner UI, and no MarketIntel DB code changes.
- The service exposes APIs/contracts; a future frontend or site-side adapter still needs to render SEO tags, load analytics tags where consent permits, present consent choices, and send browser events.
- Search-engine URL submission does not guarantee indexing or ranking.
- Real external integration tests require configured provider credentials. Mocked provider tests must be reported separately from live checks.
