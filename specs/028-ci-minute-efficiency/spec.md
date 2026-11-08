# 028 — Reduce duplicate CI compute

Owner concern: hosted Actions allowance is running out. Deliver an immediate reduction without reducing test coverage or moving PR code onto a trusted household host.

Foundation CI runs once for each PR event, on pushes to main after merge, manually on demand, and on its existing weekly schedule. Feature-branch pushes alone no longer start a second identical full suite. Preserve all four job names/commands, security audits, PostgreSQL/restore/browser coverage, read-only token, SHA pins, timeouts, concurrency and synthetic-only inputs. Package candidate continues requiring successful main-push CI for its exact main commit.

No product/runtime/API/database/dependency changes, new runner, machine registration, cloud purchase, repository administration or billing-account change. Existing GitHub-hosted policy remains active. Document current official self-hosted billing, Linux/Docker compatibility and a separate isolated-runner design decision. No live Butler/NAS access for PR jobs. Artifacts/caches have independent limits; savings apply to duplicate pre-merge compute, not every Actions charge.

Acceptance: offline manifest check preserves PR/main/manual/schedule routing, all four unconditional jobs and exact-main package prerequisite; make check passes; published feature push produces no Foundation CI run; opening the PR produces one exact-head run with all four jobs. Ready only after that run succeeds. Canonical Kanban records prior implementation review merged and this candidate In progress. No artificial second push run or costly manual dispatch merely to prove an unchanged trigger.
