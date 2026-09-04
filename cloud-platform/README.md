# Northstar Cloud

A **standalone** deployment-control-plane prototype — it has no imports, routes, data, or runtime relationship with the Lily Telegram bot in the repository root.

Northstar is inspired by the workflow of modern deployment products: connect a repository, define runtime settings, manage environment variables and domains, follow a deployment, inspect health metrics, invite a team, and roll back safely. It intentionally uses original branding, UI, and code rather than reproducing any provider’s design or proprietary implementation.

## Stack

- **React 19 + TypeScript** for the dashboard
- **Vite** for a fast local development/build workflow
- **Browser `localStorage`** for a self-contained interactive demo
- No backend, cloud credentials, or third-party API calls are required to run it

TypeScript/React is a practical modern web-dashboard stack. The commercial hosting platforms have different private internal architectures, so this project deliberately does not claim to clone their infrastructure or source code.

## Included features

- Responsive cloud-workspace dashboard
- Services/projects overview with live, building, queued, sleeping, stopped, and failed states
- Four-step **new service** wizard: repository, runtime/region, environment variables, and a safe review screen
- Simulated release pipeline that advances from queued → build → release → live and appends build output
- Preview deployments, protected production approvals, configurable direct/canary strategy, canary traffic controls, and rollback history
- Project side panel with service metrics, runtime configuration, deployment history, environment variables, and domains
- Secret masking with an explicit show/hide control; exported workspace snapshots redact secret values
- Global custom-domain manager, TLS/DNS-pending state, and redirect/rewrite/header edge-route drafts
- Start/stop state controls and previous-release rollback logic
- **Operations center** with streaming-style local logs, search/severity filters, alert rules, and incident timelines
- **Infrastructure resources** for PostgreSQL, Redis, volumes, object storage, cron jobs, workers, backup status, and provisioning states
- Observability screen with request trend, uptime, latency, transfer, CPU, and memory views
- Service template marketplace for Next.js, FastAPI, Django, workers, and Docker services
- Team management, role-based access UX, deployment policies, scoped API-token creation/revocation, and billing/usage controls
- Command palette (`⌘/Ctrl + K`) and `N` shortcut for a new service
- Browser-persistent changes, a redacted export, and reset-demo control
- Mobile navigation and accessible dialogs, labels, keyboard focus states, and status labels

## Run it locally

```bash
cd cloud-platform
npm install
npm run dev
```

Then open the URL shown by Vite (normally `http://localhost:4173`).

Production bundle check:

```bash
npm run build
```

## Important scope: UI/control-plane MVP, not a cloud provider

This project is a working web application and interaction prototype. Its deployments are intentionally simulated in the browser: it **does not** clone repositories, execute user commands, start containers, provision domains, or store real secrets. That boundary makes it safe to explore the product experience without accidentally exposing infrastructure.

A real Render/Vercel/Railway-scale platform needs separate, production-grade systems behind this UI:

1. Authentication, organizations, RBAC, billing, and auditable approvals.
2. A GitHub/GitLab App integration using scoped OAuth tokens and webhook signature verification.
3. Immutable build workers running in sandboxed containers/VMs with network and resource limits.
4. An image registry, artifact store, build cache, and software supply-chain scanning.
5. A scheduler/orchestrator (for example Kubernetes, Nomad, or a managed container runtime) for web services, cron jobs, workers, and autoscaling.
6. Encrypted server-side secret storage with key rotation — never browser `localStorage` for real credentials.
7. Managed routing, DNS verification, TLS issuance, CDN/edge caching, health checks, logs, traces, and metrics.
8. Quotas, abuse prevention, rate limits, backups, incident response, and regional failover.

The screens and state model are structured so a future API layer can replace the local storage adapter without redesigning the product surface. See [ARCHITECTURE.md](./ARCHITECTURE.md) for the safe end-to-end deployment flow, the real infrastructure required, and realistic free-tier/BYOC options.

## Project structure

```text
cloud-platform/
├── ARCHITECTURE.md  # current prototype vs. real deployment-platform design
├── src/
│   ├── App.tsx       # UI, interactive dashboard, wizard, dialogs, local actions
│   ├── data.ts       # seeded demo state and safe state transitions
│   ├── types.ts      # control-plane domain types
│   ├── styles.css    # responsive visual system
│   └── main.tsx      # React entry point
├── index.html
├── package.json
├── tsconfig.json
└── vite.config.ts
```

## Suggested next implementation phase

Keep the React/TypeScript frontend, then add a separate TypeScript API service with a database and a **strict, non-shell-based worker protocol**. Start with read-only project status and audit logs; add repository registration and signed deployment requests next; only later introduce isolated build workers and a scheduler. Never accept raw shell commands or store production secrets in browser state.
