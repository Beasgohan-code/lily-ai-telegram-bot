import type {
  ApiToken,
  CloudState,
  CreateResourceInput,
  CreateServiceInput,
  Deployment,
  DeploymentEnvironment,
  DeploymentStatus,
  DeploymentStrategy,
  EnvironmentVariable,
  LogEvent,
  NetworkRoute,
  Project,
  ResourceStatus,
  ScheduledJob,
} from './types'

const minutesAgo = (minutes: number) => new Date(Date.now() - minutes * 60_000).toISOString()
const hoursAgo = (hours: number) => minutesAgo(hours * 60)

export const STORAGE_KEY = 'northstar-cloud-control-plane-v2'

const env = (
  id: string,
  name: string,
  value: string,
  secret: boolean,
  scope: EnvironmentVariable['scope'] = 'production',
): EnvironmentVariable => ({ id, name, value, secret, scope })

export function makeId(prefix: string): string {
  return `${prefix}_${Math.random().toString(36).slice(2, 8)}${Date.now().toString(36).slice(-4)}`
}

export const seedState = (): CloudState => ({
  projects: [
    {
      id: 'aurora-storefront',
      name: 'Aurora storefront',
      description: 'The customer-facing commerce experience.',
      repository: 'northstar/aurora-storefront',
      branch: 'main',
      framework: 'Next.js',
      runtime: 'Node.js 22',
      region: 'Mumbai, India',
      status: 'live',
      url: 'https://aurora.northstar.app',
      health: 99.99,
      requests: '1.82M',
      bandwidth: '42.6 GB',
      latency: '54 ms',
      cpu: 38,
      memory: 63,
      plan: 'Pro',
      replicas: 2,
      lastDeploymentId: 'dpl_a8f21c',
      createdAt: hoursAgo(512),
      updatedAt: minutesAgo(8),
      environment: [
        env('env_a1', 'NEXT_PUBLIC_API_URL', 'https://api.aurora.northstar.app', false),
        env('env_a2', 'STRIPE_SECRET_KEY', 'sk_live_••••••••••••••••', true),
        env('env_a3', 'DATABASE_URL', 'postgresql://••••••••', true),
        env('env_a4', 'FEATURE_RECOMMENDATIONS', 'true', false, 'preview'),
      ],
      domains: [
        { id: 'dom_a1', hostname: 'aurora.northstar.app', type: 'platform', status: 'active', ssl: true },
        { id: 'dom_a2', hostname: 'shop.aurora.example', type: 'custom', status: 'active', ssl: true },
      ],
    },
    {
      id: 'beacon-api',
      name: 'Beacon API',
      description: 'Low-latency API for checkout, inventory, and accounts.',
      repository: 'northstar/beacon-api',
      branch: 'main',
      framework: 'FastAPI',
      runtime: 'Python 3.12',
      region: 'Mumbai, India',
      status: 'building',
      url: 'https://api.aurora.northstar.app',
      health: 99.98,
      requests: '884K',
      bandwidth: '17.2 GB',
      latency: '71 ms',
      cpu: 61,
      memory: 48,
      plan: 'Pro',
      replicas: 2,
      lastDeploymentId: 'dpl_b71e02',
      createdAt: hoursAgo(389),
      updatedAt: minutesAgo(2),
      environment: [
        env('env_b1', 'DATABASE_URL', 'postgresql://••••••••', true),
        env('env_b2', 'REDIS_URL', 'redis://••••••••', true),
        env('env_b3', 'LOG_LEVEL', 'info', false),
        env('env_b4', 'CORS_ORIGINS', 'https://aurora.northstar.app', false),
      ],
      domains: [{ id: 'dom_b1', hostname: 'api.aurora.northstar.app', type: 'custom', status: 'active', ssl: true }],
    },
    {
      id: 'pulse-worker',
      name: 'Pulse worker',
      description: 'Background jobs for receipts, syncs, and lifecycle events.',
      repository: 'northstar/pulse-worker',
      branch: 'main',
      framework: 'Node worker',
      runtime: 'Node.js 22',
      region: 'Singapore',
      status: 'sleeping',
      url: 'Internal service',
      health: 100,
      requests: '145K jobs',
      bandwidth: '4.8 GB',
      latency: '118 ms',
      cpu: 12,
      memory: 26,
      plan: 'Starter',
      replicas: 1,
      lastDeploymentId: 'dpl_c4d991',
      createdAt: hoursAgo(201),
      updatedAt: hoursAgo(4),
      environment: [
        env('env_c1', 'QUEUE_NAME', 'lifecycle-events', false),
        env('env_c2', 'SENTRY_DSN', 'https://••••••••', true),
        env('env_c3', 'WORKER_CONCURRENCY', '4', false),
      ],
      domains: [],
    },
    {
      id: 'docs-hub',
      name: 'Docs hub',
      description: 'Product docs and developer guides.',
      repository: 'northstar/docs-hub',
      branch: 'production',
      framework: 'Astro',
      runtime: 'Node.js 22',
      region: 'Frankfurt, Germany',
      status: 'live',
      url: 'https://docs.aurora.example',
      health: 100,
      requests: '218K',
      bandwidth: '8.1 GB',
      latency: '46 ms',
      cpu: 18,
      memory: 31,
      plan: 'Starter',
      replicas: 1,
      lastDeploymentId: 'dpl_d81af4',
      createdAt: hoursAgo(104),
      updatedAt: hoursAgo(23),
      environment: [env('env_d1', 'PUBLIC_STATUS_URL', 'https://status.aurora.example', false)],
      domains: [{ id: 'dom_d1', hostname: 'docs.aurora.example', type: 'custom', status: 'active', ssl: true }],
    },
  ],
  deployments: [
    {
      id: 'dpl_b91e03', projectId: 'beacon-api', commit: '91e03c7', message: 'feat: add idempotent checkout retries', branch: 'main', author: 'Ava Johnson', status: 'building', progress: 58, createdAt: minutesAgo(2), duration: '2m 14s', environment: 'production', strategy: 'canary', approvalState: 'pending', canaryPercent: 10, comparedTo: 'dpl_b71e02',
      logs: ['10:43:06  Cloning northstar/beacon-api (main)', '10:43:13  Restored build cache: py312-linux-amd64', '10:43:18  Installing locked dependencies', '10:43:42  Running tests: 218 passed', '10:44:03  Building application image', '10:44:48  Optimizing Python bytecode'],
    },
    {
      id: 'dpl_a8f21c', projectId: 'aurora-storefront', commit: 'a8f21c4', message: 'fix: improve mobile checkout spacing', branch: 'main', author: 'Mika Chen', status: 'live', progress: 100, createdAt: minutesAgo(8), duration: '1m 48s', environment: 'production', strategy: 'direct', approvalState: 'approved', canaryPercent: 100, comparedTo: 'dpl_a671b0',
      logs: ['10:36:09  Deployment requested from main', '10:36:16  Cache hit: node_modules', '10:36:31  Creating optimized production build', '10:37:09  Validating edge routes', '10:37:36  Promoting deployment to production', '10:37:57  Health checks passed — live'],
    },
    {
      id: 'dpl_b71e02', projectId: 'beacon-api', commit: 'b71e026', message: 'fix: normalize checkout idempotency keys', branch: 'main', author: 'Ava Johnson', status: 'live', progress: 100, createdAt: hoursAgo(27), duration: '1m 38s', environment: 'production', strategy: 'direct', approvalState: 'approved', canaryPercent: 100,
      logs: ['07:16:12  Repository checked out', '07:16:58  Unit tests passed', '07:17:50  Health checks passed — live'],
    },
    {
      id: 'dpl_a671b0', projectId: 'aurora-storefront', commit: 'a671b05', message: 'feat: add saved carts', branch: 'main', author: 'Mika Chen', status: 'live', progress: 100, createdAt: hoursAgo(35), duration: '2m 06s', environment: 'production', strategy: 'direct', approvalState: 'approved', canaryPercent: 100,
      logs: ['22:18:06  Deployment accepted', '22:19:20  Static generation complete', '22:20:12  Health checks passed — live'],
    },
    {
      id: 'dpl_d81af4', projectId: 'docs-hub', commit: 'd81af49', message: 'docs: add webhook quickstart', branch: 'production', author: 'Jon Bell', status: 'live', progress: 100, createdAt: hoursAgo(23), duration: '1m 09s', environment: 'production', strategy: 'direct', approvalState: 'approved', canaryPercent: 100,
      logs: ['11:20:09  Installing production dependencies', '11:20:30  Generating static routes', '11:20:51  Uploading immutable assets', '11:21:18  CDN propagation complete — live'],
    },
    {
      id: 'dpl_c4d991', projectId: 'pulse-worker', commit: 'c4d991a', message: 'chore: reduce idle worker resources', branch: 'main', author: 'Ava Johnson', status: 'live', progress: 100, createdAt: hoursAgo(30), duration: '58s', environment: 'production', strategy: 'direct', approvalState: 'approved', canaryPercent: 100,
      logs: ['08:12:02  Build cache restored', '08:12:37  Worker boot check passed', '08:13:00  Deployment is live'],
    },
  ],
  activity: [
    { id: 'act_1', icon: 'deploy', title: 'Beacon API is building', detail: 'Commit 91e03c7 from main', createdAt: minutesAgo(2), projectId: 'beacon-api' },
    { id: 'act_2', icon: 'deploy', title: 'Aurora storefront is live', detail: 'Production deployment a8f21c4 completed in 1m 48s', createdAt: minutesAgo(8), projectId: 'aurora-storefront' },
    { id: 'act_3', icon: 'secret', title: 'Production environment updated', detail: '1 encrypted variable changed in Beacon API', createdAt: hoursAgo(5), projectId: 'beacon-api' },
    { id: 'act_4', icon: 'alert', title: 'Storage forecast alert opened', detail: 'aurora-production-db is expected to exceed 80% in 9 days', createdAt: hoursAgo(5), projectId: 'beacon-api' },
    { id: 'act_5', icon: 'team', title: 'Priya Nair joined the workspace', detail: 'Added as Developer', createdAt: hoursAgo(28) },
  ],
  team: [
    { id: 'team_1', initials: 'AJ', name: 'Ava Johnson', email: 'ava@northstar.dev', role: 'Owner', color: '#8b5cf6', lastActive: 'Now' },
    { id: 'team_2', initials: 'MC', name: 'Mika Chen', email: 'mika@northstar.dev', role: 'Admin', color: '#06b6d4', lastActive: '8 min ago' },
    { id: 'team_3', initials: 'PN', name: 'Priya Nair', email: 'priya@northstar.dev', role: 'Developer', color: '#f97316', lastActive: '1h ago' },
    { id: 'team_4', initials: 'JB', name: 'Jon Bell', email: 'jon@northstar.dev', role: 'Viewer', color: '#ec4899', lastActive: 'Yesterday' },
  ],
  resources: [
    { id: 'res_postgres_aurora', name: 'aurora-production-db', kind: 'PostgreSQL', status: 'available', region: 'Mumbai, India', plan: 'Pro · HA', usage: 43, usageLabel: '43 GB / 100 GB', size: '2 vCPU · 8 GB RAM', connection: 'postgresql://••••••@db.northstar.internal:5432/aurora', backups: true, projectId: 'beacon-api', createdAt: hoursAgo(320) },
    { id: 'res_redis_aurora', name: 'aurora-cache', kind: 'Redis', status: 'available', region: 'Mumbai, India', plan: 'Standard', usage: 21, usageLabel: '106 MB / 512 MB', size: '1 GB memory', connection: 'redis://••••••@cache.northstar.internal:6379', backups: false, projectId: 'beacon-api', createdAt: hoursAgo(298) },
    { id: 'res_volume_docs', name: 'docs-assets', kind: 'Object storage', status: 'available', region: 'Frankfurt, Germany', plan: 'Standard', usage: 64, usageLabel: '12.8 GB / 20 GB', size: '20 GB included', connection: 's3://docs-assets', backups: true, projectId: 'docs-hub', createdAt: hoursAgo(100) },
    { id: 'res_volume_receipts', name: 'receipt-archive', kind: 'Volume', status: 'maintenance', region: 'Singapore', plan: 'Starter', usage: 17, usageLabel: '1.7 GB / 10 GB', size: '10 GB encrypted volume', connection: '/var/lib/receipts', backups: true, projectId: 'pulse-worker', createdAt: hoursAgo(173) },
  ],
  jobs: [
    { id: 'job_1', name: 'Daily reconciliation', type: 'cron', projectId: 'beacon-api', schedule: '0 2 * * *', status: 'running', lastRun: '2h ago', nextRun: 'in 22h', retries: 3 },
    { id: 'job_2', name: 'Lifecycle event worker', type: 'worker', projectId: 'pulse-worker', schedule: 'Queue: lifecycle-events', status: 'running', lastRun: 'Now', nextRun: 'Continuous', retries: 8 },
    { id: 'job_3', name: 'Docs search index', type: 'cron', projectId: 'docs-hub', schedule: '0 */6 * * *', status: 'paused', lastRun: '1d ago', nextRun: 'Paused', retries: 2 },
  ],
  alerts: [
    { id: 'alert_1', name: 'Checkout API latency', metric: 'P95 latency', threshold: '> 500 ms', window: 'for 5 minutes', channel: '#platform-alerts', enabled: true, state: 'healthy', projectId: 'beacon-api' },
    { id: 'alert_2', name: 'Storefront error budget', metric: '5xx error rate', threshold: '> 1%', window: 'for 10 minutes', channel: '#platform-alerts', enabled: true, state: 'healthy', projectId: 'aurora-storefront' },
    { id: 'alert_3', name: 'Database storage', metric: 'Disk usage', threshold: '> 80%', window: 'for 30 minutes', channel: 'Email owners', enabled: true, state: 'triggered', projectId: 'beacon-api' },
  ],
  incidents: [
    { id: 'inc_1', title: 'Database storage forecast warning', severity: 'medium', state: 'monitoring', projectId: 'beacon-api', createdAt: hoursAgo(5), updatedAt: minutesAgo(18), timeline: ['Alert triggered at 78% projected capacity.', 'Automatic backup integrity check passed.', 'Storage expansion scheduled for the next maintenance window.'] },
    { id: 'inc_2', title: 'Edge cache propagation delay', severity: 'low', state: 'resolved', projectId: 'docs-hub', createdAt: hoursAgo(97), updatedAt: hoursAgo(94), timeline: ['Frankfurt edge propagation exceeded the target.', 'Routes converged without customer impact.', 'Resolved automatically.'] },
  ],
  logs: [
    { id: 'log_1', timestamp: minutesAgo(1), level: 'info', projectId: 'beacon-api', message: 'GET /v1/checkout/health 200 24ms', requestId: 'req_81d3a', region: 'bom1' },
    { id: 'log_2', timestamp: minutesAgo(2), level: 'info', projectId: 'aurora-storefront', message: 'GET /products/aurora-jacket 200 61ms', requestId: 'req_3ca11', region: 'bom1' },
    { id: 'log_3', timestamp: minutesAgo(3), level: 'warn', projectId: 'beacon-api', message: 'cache retry completed after upstream timeout', requestId: 'req_39ba2', region: 'bom1' },
    { id: 'log_4', timestamp: minutesAgo(6), level: 'info', projectId: 'docs-hub', message: 'GET /guides/webhooks 200 37ms', requestId: 'req_adc93', region: 'fra1' },
    { id: 'log_5', timestamp: minutesAgo(8), level: 'debug', projectId: 'pulse-worker', message: 'job receipt.send completed in 412ms', requestId: 'job_38cfa', region: 'sin1' },
    { id: 'log_6', timestamp: minutesAgo(11), level: 'error', projectId: 'beacon-api', message: 'payment provider returned a retriable 503 response', requestId: 'req_17f9b', region: 'bom1' },
  ],
  routes: [
    { id: 'route_1', type: 'redirect', source: '/legacy/*', target: '/guides/$1', status: 'active', projectId: 'docs-hub' },
    { id: 'route_2', type: 'rewrite', source: '/api/*', target: 'https://api.aurora.northstar.app/$1', status: 'active', projectId: 'aurora-storefront' },
    { id: 'route_3', type: 'header', source: '/assets/*', target: 'Cache-Control: public, max-age=31536000, immutable', status: 'draft', projectId: 'aurora-storefront' },
  ],
  apiTokens: [
    { id: 'token_1', name: 'GitHub Actions deployer', prefix: 'ns_live_49c2', scopes: ['deploy:write', 'projects:read'], createdAt: hoursAgo(240), lastUsed: '8 min ago', revoked: false },
    { id: 'token_2', name: 'Read-only metrics', prefix: 'ns_live_a291', scopes: ['metrics:read'], createdAt: hoursAgo(470), lastUsed: '2d ago', revoked: false },
  ],
  deploymentPolicy: { requireProductionApproval: true, defaultStrategy: 'canary', previewBranches: true, protectedBranch: 'main' },
  billing: { plan: 'Pro', monthlyEstimate: 84.6, budgetAlert: 120, paymentMethod: 'Visa •••• 4242', includedHours: 750, usedHours: 412, includedTransferGb: 100, usedTransferGb: 72.7 },
  preferences: { compactMode: false, notifications: true, liveLogs: true },
})

export const cloneState = (state: CloudState): CloudState => JSON.parse(JSON.stringify(state)) as CloudState

/** Make a state saved by an older prototype build safe to render after new features ship. */
export function hydrateState(raw: unknown): CloudState {
  const base = seedState()
  if (!raw || typeof raw !== 'object') return base
  const saved = raw as Partial<CloudState>
  return {
    ...base,
    ...saved,
    projects: Array.isArray(saved.projects) ? saved.projects : base.projects,
    deployments: Array.isArray(saved.deployments) ? saved.deployments : base.deployments,
    activity: Array.isArray(saved.activity) ? saved.activity : base.activity,
    team: Array.isArray(saved.team) ? saved.team : base.team,
    resources: Array.isArray(saved.resources) ? saved.resources : base.resources,
    jobs: Array.isArray(saved.jobs) ? saved.jobs : base.jobs,
    alerts: Array.isArray(saved.alerts) ? saved.alerts : base.alerts,
    incidents: Array.isArray(saved.incidents) ? saved.incidents : base.incidents,
    logs: Array.isArray(saved.logs) ? saved.logs : base.logs,
    routes: Array.isArray(saved.routes) ? saved.routes : base.routes,
    apiTokens: Array.isArray(saved.apiTokens) ? saved.apiTokens : base.apiTokens,
    deploymentPolicy: { ...base.deploymentPolicy, ...(saved.deploymentPolicy ?? {}) },
    billing: { ...base.billing, ...(saved.billing ?? {}) },
    preferences: { ...base.preferences, ...(saved.preferences ?? {}) },
  }
}

export function projectById(state: CloudState, id: string | null): Project | undefined {
  return state.projects.find((project) => project.id === id)
}

export function deploymentById(state: CloudState, id: string | null): Deployment | undefined {
  return state.deployments.find((deployment) => deployment.id === id)
}

export const statusLabel = (status: string): string => ({
  live: 'Live', building: 'Building', queued: 'Queued', deploying: 'Deploying', sleeping: 'Sleeping', stopped: 'Stopped', failed: 'Failed', rolled_back: 'Rolled back', available: 'Available', provisioning: 'Provisioning', maintenance: 'Maintenance', running: 'Running', paused: 'Paused', healthy: 'Healthy', triggered: 'Triggered', investigating: 'Investigating', monitoring: 'Monitoring', resolved: 'Resolved', active: 'Active', draft: 'Draft', pending: 'Awaiting approval', approved: 'Approved', not_required: 'No approval needed',
}[status] ?? status)

function newDeployment(
  state: CloudState,
  project: Project,
  environment: DeploymentEnvironment,
  strategy: DeploymentStrategy,
  message: string,
): Deployment {
  const isProduction = environment === 'production'
  const requiresApproval = isProduction && state.deploymentPolicy.requireProductionApproval
  const id = makeId('dpl')
  return {
    id,
    projectId: project.id,
    commit: Math.random().toString(16).slice(2, 9),
    message,
    branch: project.branch,
    author: 'You',
    status: 'queued',
    progress: 8,
    createdAt: new Date().toISOString(),
    duration: 'Just now',
    environment,
    strategy,
    approvalState: requiresApproval ? 'pending' : 'approved',
    canaryPercent: strategy === 'canary' && isProduction ? 10 : 100,
    comparedTo: project.lastDeploymentId || undefined,
    previewUrl: environment === 'preview' ? `https://${project.id}-${id.slice(-5)}.preview.northstar.app` : undefined,
    logs: [
      `${environment === 'preview' ? 'Preview' : 'Production'} deployment requested`,
      `Checking out ${project.repository}@${project.branch}`,
      'Waiting for an isolated build worker…',
    ],
  }
}

export function createService(state: CloudState, input: CreateServiceInput): { state: CloudState; project: Project; deployment: Deployment } {
  const next = cloneState(state)
  const baseId = input.name.trim().toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '').slice(0, 36) || 'untitled-service'
  const id = next.projects.some((project) => project.id === baseId) ? `${baseId}-${Math.random().toString(36).slice(2, 5)}` : baseId
  const now = new Date().toISOString()
  const project: Project = {
    id,
    name: input.name.trim() || 'Untitled service',
    description: input.description.trim() || 'A new service deployed with Northstar.',
    repository: input.repository.trim() || 'your-org/your-repository',
    branch: input.branch.trim() || 'main',
    framework: input.framework,
    runtime: input.runtime,
    region: input.region,
    status: 'queued',
    url: `https://${id}.northstar.app`,
    health: 100,
    requests: '0',
    bandwidth: '0 B',
    latency: '—',
    cpu: 0,
    memory: 0,
    plan: input.plan,
    replicas: 1,
    lastDeploymentId: '',
    createdAt: now,
    updatedAt: now,
    environment: input.env,
    domains: [{ id: makeId('dom'), hostname: `${id}.northstar.app`, type: 'platform', status: 'active', ssl: true }],
  }
  const deployment = newDeployment(next, project, 'production', next.deploymentPolicy.defaultStrategy, 'Initial deployment from dashboard')
  project.lastDeploymentId = deployment.id
  next.projects.unshift(project)
  next.deployments.unshift(deployment)
  next.activity.unshift({ id: makeId('act'), icon: 'deploy', title: `${project.name} was queued`, detail: `Initial deployment from ${project.branch}`, createdAt: now, projectId: project.id })
  return { state: next, project, deployment }
}

const nextStage = (status: DeploymentStatus): { status: DeploymentStatus; progress: number; log: string; duration: string } | null => {
  if (status === 'queued') return { status: 'building', progress: 34, log: 'A secure build worker was assigned', duration: '18s' }
  if (status === 'building') return { status: 'deploying', progress: 74, log: 'Build completed; running release checks', duration: '54s' }
  if (status === 'deploying') return { status: 'live', progress: 100, log: 'Health checks passed — deployment is live', duration: '1m 23s' }
  return null
}

export function progressDeployments(state: CloudState): CloudState {
  const next = cloneState(state)
  let changed = false
  for (const deployment of next.deployments) {
    if (deployment.status === 'deploying' && deployment.environment === 'production' && deployment.approvalState === 'pending') continue
    const stage = nextStage(deployment.status)
    if (!stage) continue
    changed = true
    const before = deployment.status
    deployment.status = stage.status
    deployment.progress = stage.progress
    deployment.duration = stage.duration
    deployment.logs.push(`${new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}  ${stage.log}`)
    const project = next.projects.find((item) => item.id === deployment.projectId)
    if (project && deployment.environment !== 'preview') {
      project.status = stage.status === 'live' ? 'live' : stage.status === 'queued' ? 'queued' : 'building'
      project.updatedAt = new Date().toISOString()
      if (stage.status === 'live') {
        if ((deployment.canaryPercent ?? 100) >= 100) project.lastDeploymentId = deployment.id
        project.cpu = Math.max(project.cpu, 24)
        project.memory = Math.max(project.memory, 32)
      }
    }
    if (stage.status === 'live' || before === 'queued') {
      next.activity.unshift({
        id: makeId('act'),
        icon: 'deploy',
        title: stage.status === 'live' ? `${project?.name ?? 'Service'} is live` : `${project?.name ?? 'Service'} started building`,
        detail: deployment.environment === 'preview' ? `Preview release ${deployment.commit} is available` : stage.status === 'live' ? `Deployment ${deployment.commit} passed health checks` : 'A secure build worker has started the release',
        createdAt: new Date().toISOString(),
        projectId: deployment.projectId,
      })
    }
  }
  return changed ? next : state
}

export function requestDeployment(state: CloudState, projectId: string): { state: CloudState; deployment?: Deployment } {
  const project = state.projects.find((item) => item.id === projectId)
  if (!project) return { state }
  const next = cloneState(state)
  const current = next.projects.find((item) => item.id === projectId)!
  const deployment = newDeployment(next, current, 'production', next.deploymentPolicy.defaultStrategy, 'Manual deployment from dashboard')
  current.status = 'queued'
  current.updatedAt = new Date().toISOString()
  next.deployments.unshift(deployment)
  next.activity.unshift({ id: makeId('act'), icon: 'deploy', title: `New deployment queued for ${current.name}`, detail: `Manual ${deployment.strategy} release from ${current.branch}`, createdAt: new Date().toISOString(), projectId })
  return { state: next, deployment }
}

export function requestPreviewDeployment(state: CloudState, projectId: string): { state: CloudState; deployment?: Deployment } {
  const project = state.projects.find((item) => item.id === projectId)
  if (!project) return { state }
  const next = cloneState(state)
  const current = next.projects.find((item) => item.id === projectId)!
  const deployment = newDeployment(next, current, 'preview', 'direct', 'Preview deployment from dashboard')
  next.deployments.unshift(deployment)
  next.activity.unshift({ id: makeId('act'), icon: 'deploy', title: `Preview queued for ${current.name}`, detail: `Temporary preview from ${current.branch}`, createdAt: new Date().toISOString(), projectId })
  return { state: next, deployment }
}

export function approveDeployment(state: CloudState, deploymentId: string): CloudState {
  const next = cloneState(state)
  const deployment = next.deployments.find((item) => item.id === deploymentId)
  if (!deployment || deployment.approvalState !== 'pending') return state
  deployment.approvalState = 'approved'
  deployment.logs.push('Production promotion approved by You')
  next.activity.unshift({ id: makeId('act'), icon: 'security', title: 'Production release approved', detail: `${deployment.commit} passed its deployment policy gate`, createdAt: new Date().toISOString(), projectId: deployment.projectId })
  return next
}

export function setCanaryTraffic(state: CloudState, deploymentId: string, percent: number): CloudState {
  const next = cloneState(state)
  const deployment = next.deployments.find((item) => item.id === deploymentId)
  if (!deployment) return state
  const bounded = Math.max(0, Math.min(100, Math.round(percent / 5) * 5))
  deployment.canaryPercent = bounded
  deployment.logs.push(`Canary traffic adjusted to ${bounded}%`)
  if (bounded === 100 && deployment.status === 'live' && deployment.environment === 'production') {
    const project = next.projects.find((item) => item.id === deployment.projectId)
    if (project) project.lastDeploymentId = deployment.id
  }
  next.activity.unshift({ id: makeId('act'), icon: 'deploy', title: 'Canary traffic updated', detail: `${bounded}% of production traffic now targets ${deployment.commit}`, createdAt: new Date().toISOString(), projectId: deployment.projectId })
  return next
}

export function setProjectStatus(state: CloudState, projectId: string, status: Project['status']): CloudState {
  const next = cloneState(state)
  const project = next.projects.find((item) => item.id === projectId)
  if (!project) return state
  project.status = status
  project.updatedAt = new Date().toISOString()
  next.activity.unshift({ id: makeId('act'), icon: 'service', title: `${project.name} ${status === 'stopped' ? 'was stopped' : status === 'sleeping' ? 'was put to sleep' : 'was started'}`, detail: status === 'stopped' ? 'No further requests will be served until started.' : 'Service configuration was updated from the dashboard.', createdAt: new Date().toISOString(), projectId })
  return next
}

export function addDomain(state: CloudState, projectId: string, hostname: string): CloudState {
  const next = cloneState(state)
  const project = next.projects.find((item) => item.id === projectId)
  const clean = hostname.trim().toLowerCase().replace(/^https?:\/\//, '').replace(/\/$/, '')
  if (!project || !clean || project.domains.some((domain) => domain.hostname === clean)) return state
  project.domains.push({ id: makeId('dom'), hostname: clean, type: 'custom', status: 'pending', ssl: false })
  project.updatedAt = new Date().toISOString()
  next.activity.unshift({ id: makeId('act'), icon: 'domain', title: `Domain added to ${project.name}`, detail: `${clean} is waiting for DNS verification`, createdAt: new Date().toISOString(), projectId })
  return next
}

export function removeDomain(state: CloudState, projectId: string, domainId: string): CloudState {
  const next = cloneState(state)
  const project = next.projects.find((item) => item.id === projectId)
  const domain = project?.domains.find((item) => item.id === domainId)
  if (!project || !domain || domain.type === 'platform') return state
  project.domains = project.domains.filter((item) => item.id !== domainId)
  project.updatedAt = new Date().toISOString()
  return next
}

export function addEnvironmentVariable(state: CloudState, projectId: string, variable: Omit<EnvironmentVariable, 'id'>): CloudState {
  const next = cloneState(state)
  const project = next.projects.find((item) => item.id === projectId)
  if (!project || !variable.name.trim()) return state
  const name = variable.name.trim().toUpperCase()
  const existing = project.environment.find((item) => item.name === name && item.scope === variable.scope)
  if (existing) { existing.value = variable.value; existing.secret = variable.secret } else project.environment.push({ ...variable, id: makeId('env'), name })
  project.updatedAt = new Date().toISOString()
  next.activity.unshift({ id: makeId('act'), icon: 'secret', title: `Environment updated for ${project.name}`, detail: variable.secret ? 'An encrypted variable was saved locally.' : `${name} was saved locally.`, createdAt: new Date().toISOString(), projectId })
  return next
}

export function removeEnvironmentVariable(state: CloudState, projectId: string, variableId: string): CloudState {
  const next = cloneState(state)
  const project = next.projects.find((item) => item.id === projectId)
  if (!project) return state
  project.environment = project.environment.filter((item) => item.id !== variableId)
  project.updatedAt = new Date().toISOString()
  return next
}

export function rollbackProject(state: CloudState, projectId: string): { state: CloudState; success: boolean } {
  const next = cloneState(state)
  const project = next.projects.find((item) => item.id === projectId)
  if (!project) return { state, success: false }
  const live = next.deployments.filter((item) => item.projectId === projectId && item.status === 'live' && item.environment !== 'preview')
  if (live.length < 2) return { state, success: false }
  const current = live.find((item) => item.id === project.lastDeploymentId) ?? live[0]
  const previous = live.find((item) => item.id !== current.id)
  if (!previous) return { state, success: false }
  current.status = 'rolled_back'
  current.logs.push('Rollback requested from dashboard')
  previous.logs.push('Promoted again after rollback')
  project.lastDeploymentId = previous.id
  project.status = 'live'
  project.updatedAt = new Date().toISOString()
  next.activity.unshift({ id: makeId('act'), icon: 'rollback', title: `${project.name} was rolled back`, detail: `Production now serves ${previous.commit}`, createdAt: new Date().toISOString(), projectId })
  return { state: next, success: true }
}

export function createResource(state: CloudState, input: CreateResourceInput): { state: CloudState; resource: CloudState['resources'][number] } {
  const next = cloneState(state)
  const resource = {
    id: makeId('res'),
    name: input.name.trim() || `new-${input.kind.toLowerCase().replace(/\s+/g, '-')}`,
    kind: input.kind,
    status: 'provisioning' as ResourceStatus,
    region: input.region,
    plan: input.plan,
    usage: 0,
    usageLabel: input.kind === 'Redis' ? '0 MB / 256 MB' : '0 GB / 10 GB',
    size: input.kind === 'PostgreSQL' ? '1 vCPU · 2 GB RAM' : input.kind === 'Redis' ? '256 MB memory' : '10 GB included',
    connection: input.kind === 'Volume' ? '/var/lib/data' : `${input.kind.toLowerCase().replace(/\s+/g, '+')}://••••••`,
    backups: input.kind !== 'Redis',
    projectId: input.projectId,
    createdAt: new Date().toISOString(),
  }
  next.resources.unshift(resource)
  next.activity.unshift({ id: makeId('act'), icon: 'resource', title: `${resource.name} is provisioning`, detail: `${resource.kind} in ${resource.region}`, createdAt: resource.createdAt, projectId: resource.projectId })
  return { state: next, resource }
}

export function completeProvisioning(state: CloudState): CloudState {
  const next = cloneState(state)
  let changed = false
  for (const resource of next.resources) {
    if (resource.status === 'provisioning') { resource.status = 'available'; changed = true }
  }
  return changed ? next : state
}

export function toggleJob(state: CloudState, jobId: string): CloudState {
  const next = cloneState(state)
  const job = next.jobs.find((item) => item.id === jobId)
  if (!job) return state
  job.status = job.status === 'running' ? 'paused' : 'running'
  job.nextRun = job.status === 'running' ? (job.type === 'worker' ? 'Continuous' : 'in 6h') : 'Paused'
  next.activity.unshift({ id: makeId('act'), icon: 'service', title: `${job.name} ${job.status}`, detail: job.status === 'running' ? 'Schedule is active again.' : 'Schedule was paused from the dashboard.', createdAt: new Date().toISOString(), projectId: job.projectId })
  return next
}

export function toggleAlert(state: CloudState, alertId: string): CloudState {
  const next = cloneState(state)
  const alert = next.alerts.find((item) => item.id === alertId)
  if (!alert) return state
  alert.enabled = !alert.enabled
  next.activity.unshift({ id: makeId('act'), icon: 'alert', title: `${alert.name} ${alert.enabled ? 'enabled' : 'muted'}`, detail: alert.enabled ? 'Alert delivery resumed.' : 'Alert delivery paused from the dashboard.', createdAt: new Date().toISOString(), projectId: alert.projectId })
  return next
}

export function resolveIncident(state: CloudState, incidentId: string): CloudState {
  const next = cloneState(state)
  const incident = next.incidents.find((item) => item.id === incidentId)
  if (!incident || incident.state === 'resolved') return state
  incident.state = 'resolved'
  incident.updatedAt = new Date().toISOString()
  incident.timeline.push('Marked resolved by You in the local control plane.')
  next.activity.unshift({ id: makeId('act'), icon: 'alert', title: `${incident.title} resolved`, detail: 'Incident status was updated.', createdAt: incident.updatedAt, projectId: incident.projectId })
  return next
}

const logMessages: Omit<LogEvent, 'id' | 'timestamp'>[] = [
  { level: 'info', projectId: 'aurora-storefront', message: 'GET /collections/new-arrivals 200 48ms', requestId: 'req_a238d', region: 'bom1' },
  { level: 'info', projectId: 'beacon-api', message: 'POST /v1/checkout 201 82ms', requestId: 'req_4bf21', region: 'bom1' },
  { level: 'debug', projectId: 'pulse-worker', message: 'job webhook.dispatch completed in 219ms', requestId: 'job_219af', region: 'sin1' },
  { level: 'info', projectId: 'docs-hub', message: 'GET /api-reference 200 41ms', requestId: 'req_aa462', region: 'fra1' },
]

export function appendLiveLog(state: CloudState): CloudState {
  if (!state.preferences.liveLogs) return state
  const next = cloneState(state)
  const template = logMessages[Math.floor(Math.random() * logMessages.length)]
  next.logs.unshift({ ...template, id: makeId('log'), timestamp: new Date().toISOString() })
  next.logs = next.logs.slice(0, 120)
  return next
}

export function addNetworkRoute(state: CloudState, route: Omit<NetworkRoute, 'id' | 'status'>): CloudState {
  const next = cloneState(state)
  if (!route.source.trim() || !route.target.trim()) return state
  const nextRoute: NetworkRoute = { ...route, id: makeId('route'), source: route.source.trim(), target: route.target.trim(), status: 'draft' }
  next.routes.unshift(nextRoute)
  next.activity.unshift({ id: makeId('act'), icon: 'route', title: 'Network route created', detail: `${nextRoute.type}: ${nextRoute.source} → ${nextRoute.target}`, createdAt: new Date().toISOString(), projectId: nextRoute.projectId })
  return next
}

export function toggleRoute(state: CloudState, routeId: string): CloudState {
  const next = cloneState(state)
  const route = next.routes.find((item) => item.id === routeId)
  if (!route) return state
  route.status = route.status === 'active' ? 'draft' : 'active'
  return next
}

export function removeRoute(state: CloudState, routeId: string): CloudState {
  const next = cloneState(state)
  next.routes = next.routes.filter((item) => item.id !== routeId)
  return next
}

export function createApiToken(state: CloudState, name: string, scopes: string[]): { state: CloudState; token?: string } {
  const cleanName = name.trim()
  if (!cleanName || !scopes.length) return { state }
  const next = cloneState(state)
  const suffix = Math.random().toString(36).slice(2, 10)
  const token = `ns_live_${suffix}${Math.random().toString(36).slice(2, 8)}`
  const apiToken: ApiToken = { id: makeId('token'), name: cleanName, prefix: token.slice(0, 12), scopes, createdAt: new Date().toISOString(), lastUsed: 'Never', revoked: false }
  next.apiTokens.unshift(apiToken)
  next.activity.unshift({ id: makeId('act'), icon: 'security', title: 'API token created', detail: `${cleanName} has ${scopes.length} scoped permission${scopes.length === 1 ? '' : 's'}`, createdAt: apiToken.createdAt })
  return { state: next, token }
}

export function revokeApiToken(state: CloudState, tokenId: string): CloudState {
  const next = cloneState(state)
  const token = next.apiTokens.find((item) => item.id === tokenId)
  if (!token || token.revoked) return state
  token.revoked = true
  token.lastUsed = 'Revoked'
  next.activity.unshift({ id: makeId('act'), icon: 'security', title: 'API token revoked', detail: token.name, createdAt: new Date().toISOString() })
  return next
}

export function updateDeploymentPolicy(state: CloudState, patch: Partial<CloudState['deploymentPolicy']>): CloudState {
  const next = cloneState(state)
  next.deploymentPolicy = { ...next.deploymentPolicy, ...patch }
  next.activity.unshift({ id: makeId('act'), icon: 'security', title: 'Deployment policy updated', detail: 'Production protection settings changed locally.', createdAt: new Date().toISOString() })
  return next
}

export function updateBilling(state: CloudState, patch: Partial<CloudState['billing']>): CloudState {
  const next = cloneState(state)
  next.billing = { ...next.billing, ...patch }
  return next
}
