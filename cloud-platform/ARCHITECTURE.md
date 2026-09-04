# Northstar Cloud architecture

## What runs today

Northstar Cloud is currently a **client-side product prototype**:

```text
Browser
  └─ React + TypeScript dashboard
       ├─ seeded sample workspace
       ├─ localStorage persistence
       ├─ simulated deployment state machine
       ├─ local log/alert/resource/team state
       └─ redacted JSON export
```

The app never contacts GitHub, launches Docker, reads host files, creates a database, provisions DNS, or sends credentials over the network. It is safe to run locally and is useful for validating the product UX before operating real infrastructure.

## How a real deployment platform should work

A production implementation must put trusted server-side services behind the UI:

```text
Developer / CI
   │
   ├── signed OAuth / API token ──> Control API
   │                                  │
GitHub/GitLab webhook ────────────────┤
                                      ▼
                               Deployment planner
                                      │
                   policy / approval / quota checks
                                      │
                                      ▼
                         Isolated build worker pool
                  (short-lived containers or virtual machines)
                                      │
                 build image, test, scan, sign, cache artifacts
                                      │
                                      ▼
                      Private image registry / artifact store
                                      │
                                      ▼
                Runtime scheduler (Kubernetes, Nomad, etc.)
                    │                  │                 │
                 web service        worker            cron job
                    │                  │                 │
                    └───── health checks / autoscaling ┘
                                      │
                                      ▼
               Edge proxy + DNS validation + managed TLS/CDN
                                      │
                                      ▼
                             Application visitors
```

### A safe release lifecycle

1. **Repository event** — a GitHub App webhook is checked with its signature and mapped to an organization/project.
2. **Policy evaluation** — validate roles, quotas, protected branches, deployment approval requirements, and trusted build configuration. Reject arbitrary shell commands.
3. **Build** — dispatch only the approved commit SHA to a fresh isolated worker with CPU, RAM, filesystem, timeout, and egress limits.
4. **Supply-chain checks** — inspect dependencies/images, generate an SBOM, scan for known vulnerabilities, and sign the resulting artifact.
5. **Runtime rollout** — deploy an immutable image/version through a scheduler. Run readiness/health checks before routing traffic.
6. **Promotion** — use a preview URL, manual approval, and optionally weighted/canary traffic before 100% production promotion.
7. **Observe** — collect structured logs, metrics, traces, and audit events; redact secrets before any user sees them.
8. **Rollback** — promote the prior immutable healthy version; do not rebuild a different mutable branch.

## Can it be free?

- **The dashboard can be hosted free** as a static site on services with a free tier.
- **A real runtime cannot honestly promise unlimited free deployment.** CPU, memory, bandwidth, storage, container registry, database backups, DNS/TLS, and observability all have costs.
- You can make a low-cost or free-development option using **bring-your-own-cloud**: Docker on a local machine, a personal VPS, or a provider's limited free tier. The user supplies the infrastructure and remains responsible for its bill/limits.
- Never promise free hosting for arbitrary workloads. Abuse protection, fair-use limits, workload restrictions, and account verification are essential for a public platform.

## Recommended implementation order

1. Add authentication, organizations, RBAC, audit events, and an API database.
2. Implement GitHub App installation plus signed webhook ingestion.
3. Add a read-only project/deployment status API and replace localStorage behind a feature flag.
4. Add a single **bring-your-own Docker host** adapter with explicit service manifests, not free-form shell access.
5. Add an isolated build worker and private artifact registry.
6. Add a scheduler, health checks, preview environments, and rollback.
7. Add a real secrets manager, domains/TLS, resource provisioning, metrics, billing, and abuse controls.

## Security rules for the real backend

- Never run user-supplied shell commands directly on the control-plane host.
- Never store production secret values in the browser or return them after creation.
- Verify Git webhooks and protect every mutating request with RBAC and audit logging.
- Use immutable commit SHAs and signed artifacts; avoid deploying a moving branch name directly.
- Keep build workloads isolated from the control plane and from one another.
- Require rate limits, quotas, ownership boundaries, backups, and explicit retention policies.
