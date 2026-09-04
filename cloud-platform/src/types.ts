export type ServiceStatus = 'live' | 'building' | 'queued' | 'sleeping' | 'stopped' | 'failed'
export type DeploymentStatus = 'live' | 'building' | 'queued' | 'deploying' | 'failed' | 'rolled_back'
export type DeploymentEnvironment = 'production' | 'preview'
export type DeploymentStrategy = 'direct' | 'canary'
export type Page = 'overview' | 'projects' | 'deployments' | 'operations' | 'resources' | 'network' | 'templates' | 'observability' | 'team' | 'settings'

export interface EnvironmentVariable {
  id: string
  name: string
  value: string
  secret: boolean
  scope: 'production' | 'preview' | 'development'
}

export interface Domain {
  id: string
  hostname: string
  type: 'platform' | 'custom'
  status: 'active' | 'pending'
  ssl: boolean
}

export interface Project {
  id: string
  name: string
  description: string
  repository: string
  branch: string
  framework: string
  runtime: string
  region: string
  status: ServiceStatus
  url: string
  health: number
  requests: string
  bandwidth: string
  latency: string
  cpu: number
  memory: number
  plan: string
  replicas: number
  lastDeploymentId: string
  createdAt: string
  updatedAt: string
  environment: EnvironmentVariable[]
  domains: Domain[]
}

export interface Deployment {
  id: string
  projectId: string
  commit: string
  message: string
  branch: string
  author: string
  status: DeploymentStatus
  progress: number
  createdAt: string
  duration: string
  logs: string[]
  environment?: DeploymentEnvironment
  strategy?: DeploymentStrategy
  approvalState?: 'not_required' | 'pending' | 'approved'
  previewUrl?: string
  canaryPercent?: number
  comparedTo?: string
}

export interface ActivityItem {
  id: string
  icon: 'deploy' | 'domain' | 'team' | 'secret' | 'rollback' | 'service' | 'resource' | 'alert' | 'security' | 'route'
  title: string
  detail: string
  createdAt: string
  projectId?: string
}

export interface TeamMember {
  id: string
  initials: string
  name: string
  email: string
  role: 'Owner' | 'Admin' | 'Developer' | 'Viewer'
  color: string
  lastActive: string
}

export type ResourceKind = 'PostgreSQL' | 'Redis' | 'Volume' | 'Object storage'
export type ResourceStatus = 'available' | 'provisioning' | 'maintenance'

export interface ManagedResource {
  id: string
  name: string
  kind: ResourceKind
  status: ResourceStatus
  region: string
  plan: string
  usage: number
  usageLabel: string
  size: string
  connection: string
  backups: boolean
  projectId?: string
  createdAt: string
}

export interface ScheduledJob {
  id: string
  name: string
  type: 'cron' | 'worker'
  projectId: string
  schedule: string
  status: 'running' | 'paused'
  lastRun: string
  nextRun: string
  retries: number
}

export interface AlertRule {
  id: string
  name: string
  metric: string
  threshold: string
  window: string
  channel: string
  enabled: boolean
  state: 'healthy' | 'triggered'
  projectId?: string
}

export interface Incident {
  id: string
  title: string
  severity: 'critical' | 'high' | 'medium' | 'low'
  state: 'investigating' | 'monitoring' | 'resolved'
  projectId?: string
  createdAt: string
  updatedAt: string
  timeline: string[]
}

export interface LogEvent {
  id: string
  timestamp: string
  level: 'info' | 'warn' | 'error' | 'debug'
  projectId: string
  message: string
  requestId: string
  region: string
}

export interface NetworkRoute {
  id: string
  type: 'redirect' | 'rewrite' | 'header'
  source: string
  target: string
  status: 'active' | 'draft'
  projectId?: string
}

export interface ApiToken {
  id: string
  name: string
  prefix: string
  scopes: string[]
  createdAt: string
  lastUsed: string
  revoked: boolean
}

export interface DeploymentPolicy {
  requireProductionApproval: boolean
  defaultStrategy: DeploymentStrategy
  previewBranches: boolean
  protectedBranch: string
}

export interface BillingState {
  plan: 'Starter' | 'Pro' | 'Scale'
  monthlyEstimate: number
  budgetAlert: number
  paymentMethod: string
  includedHours: number
  usedHours: number
  includedTransferGb: number
  usedTransferGb: number
}

export interface CloudState {
  projects: Project[]
  deployments: Deployment[]
  activity: ActivityItem[]
  team: TeamMember[]
  resources: ManagedResource[]
  jobs: ScheduledJob[]
  alerts: AlertRule[]
  incidents: Incident[]
  logs: LogEvent[]
  routes: NetworkRoute[]
  apiTokens: ApiToken[]
  deploymentPolicy: DeploymentPolicy
  billing: BillingState
  preferences: {
    compactMode: boolean
    notifications: boolean
    liveLogs: boolean
  }
}

export interface CreateServiceInput {
  name: string
  description: string
  repository: string
  branch: string
  framework: string
  runtime: string
  region: string
  plan: string
  env: EnvironmentVariable[]
}

export interface CreateResourceInput {
  name: string
  kind: ResourceKind
  region: string
  plan: string
  projectId?: string
}
