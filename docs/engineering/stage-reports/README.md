# Stage Reports

One report per stage: `stage-XX.md`. A stage may only start after the previous report shows **Gate: PASS**.

## Template

```markdown
# Stage XX — <name>

- Date:
- Roles performed: (state whether real subagents or sequential role passes)

## Scope
## Files/modules changed
## Acceptance criteria and evidence
| Req ID | Criterion | Evidence (test / command) | Result |
## Commands run and actual results
| Command | Result (pass/fail/skip counts, exit code) |
## Coverage and static/security scans
## External checks
| Check | LIVE-PASS / MOCK-PASS / BLOCKED | Notes |
## Review findings and remediation
| # | Severity | Finding | Resolution |
## Remaining risks / blockers
## Gate: PASS | BLOCKED | FAIL
## Next stage allowed: YES | NO
```

## Index

| Stage | Name | Gate | Report |
|-------|------|------|--------|
| 0 | Discovery and requirements | PASS | [stage-00.md](stage-00.md) |
| 1 | Project foundation | — | — |
| 2 | Authentication, tenancy, audit | — | — |
| 3 | Sites/domains and content | — | — |
| 4 | SEO engine | — | — |
| 5 | Search provider integrations | — | — |
| 6 | Analytics | — | — |
| 7 | Consent backend | — | — |
| 8 | GitHub onboarding (feature-flagged) | — | — |
| 9 | QA and production readiness | — | — |
