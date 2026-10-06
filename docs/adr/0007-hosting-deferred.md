# 0007. Hosting is decided at the Beta phase

- Status: Accepted
- Date: 2026-10-06

## Context
No hosting is needed until Phase 5. Choosing now would be guessing.

## Decision
Develop locally with Docker Compose. Choose a managed platform plus managed PostgreSQL in
Phase 5, based on cost, backups, and ease of deploys from GitHub Actions.

## Consequences
- The app must stay platform-neutral: configuration via environment variables, containerized.
