import { useEffect, useState, type CSSProperties, type FormEvent, type ReactNode } from 'react'
import {
  STORAGE_KEY,
  addDomain,
  addEnvironmentVariable,
  addNetworkRoute,
  appendLiveLog,
  approveDeployment,
  cloneState,
  completeProvisioning,
  createApiToken,
  createResource,
  createService,
  deploymentById,
  hydrateState,
  makeId,
  progressDeployments,
  projectById,
  removeDomain,
  removeEnvironmentVariable,
  removeRoute,
  requestDeployment,
  requestPreviewDeployment,
  revokeApiToken,
  rollbackProject,
  seedState,
  setCanaryTraffic,
  setProjectStatus,
  statusLabel,
  toggleAlert,
  toggleJob,
  toggleRoute,
  updateBilling,
  updateDeploymentPolicy,
  resolveIncident,
} from './data'
import type {
  ActivityItem,
  CloudState,
  CreateResourceInput,
  CreateServiceInput,
  Deployment,
  DeploymentStrategy,
  Domain,
  EnvironmentVariable,
  NetworkRoute,
  Page,
  Project,
  ResourceKind,
  ServiceStatus,
  TeamMember,
} from './types'

type IconName =
  | 'grid'
  | 'box'
  | 'rocket'
  | 'chart'
  | 'users'
  | 'settings'
  | 'plus'
  | 'search'
  | 'command'
  | 'bell'
  | 'chevronDown'
  | 'arrowUpRight'
  | 'dots'
  | 'github'
  | 'terminal'
  | 'globe'
  | 'key'
  | 'database'
  | 'clock'
  | 'check'
  | 'warning'
  | 'x'
  | 'copy'
  | 'refresh'
  | 'stop'
  | 'moon'
  | 'menu'
  | 'filter'
  | 'activity'
  | 'arrowLeft'
  | 'trash'
  | 'lock'
  | 'download'
  | 'sliders'
  | 'server'
  | 'eye'
  | 'eyeOff'
  | 'layers'
  | 'sparkles'
  | 'info'

function Icon({ name, size = 18, stroke = 1.8 }: { name: IconName; size?: number; stroke?: number }) {
  const common = { width: size, height: size, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: stroke, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const, 'aria-hidden': true }
  const shapes: Record<IconName, ReactNode> = {
    grid: <><rect x="3" y="3" width="7" height="7" rx="1" /><rect x="14" y="3" width="7" height="7" rx="1" /><rect x="3" y="14" width="7" height="7" rx="1" /><rect x="14" y="14" width="7" height="7" rx="1" /></>,
    box: <><path d="m12 3 8 4.5v9L12 21l-8-4.5v-9L12 3Z" /><path d="m4 7.5 8 4.5 8-4.5M12 12v9" /></>,
    rocket: <><path d="M14.5 4.5c2.9-2.9 5.5-2.5 5.5-2.5s.4 2.6-2.5 5.5l-4.2 4.2-3-3 4.2-4.2Z" /><path d="m10.3 8.7-4.4.7-3 3 4.2 1.2M13.3 11.7l.7 4.4-3 3-1.2-4.2M7.5 16.5 4 20m3.5-3.5-2-2" /><circle cx="15.5" cy="6.5" r="1" /></>,
    chart: <><path d="M3 3v18h18" /><path d="m7 15 3-3 3 2 5-6" /></>,
    users: <><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" /><circle cx="9" cy="7" r="4" /><path d="M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75" /></>,
    settings: <><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.7 1.7 0 0 0 .34 1.88l.06.06-2.12 2.12-.06-.06a1.7 1.7 0 0 0-1.88-.34 1.7 1.7 0 0 0-1.03 1.55V20.3h-3v-.09A1.7 1.7 0 0 0 10.68 18.66a1.7 1.7 0 0 0-1.88.34l-.06.06-2.12-2.12.06-.06A1.7 1.7 0 0 0 7.02 15a1.7 1.7 0 0 0-1.55-1.03H5.4v-3h.07A1.7 1.7 0 0 0 7.02 9.94a1.7 1.7 0 0 0-.34-1.88l-.06-.06 2.12-2.12.06.06a1.7 1.7 0 0 0 1.88.34A1.7 1.7 0 0 0 11.71 4.73V4.6h3v.13a1.7 1.7 0 0 0 1.03 1.55 1.7 1.7 0 0 0 1.88-.34l.06-.06L19.8 8l-.06.06a1.7 1.7 0 0 0-.34 1.88 1.7 1.7 0 0 0 1.55 1.03h.13v3h-.13A1.7 1.7 0 0 0 19.4 15Z" /></>,
    plus: <path d="M12 5v14M5 12h14" />,
    search: <><circle cx="11" cy="11" r="6.5" /><path d="m16 16 4.5 4.5" /></>,
    command: <><path d="M9 7a3 3 0 1 0-3 3h12a3 3 0 1 1-3 3H6a3 3 0 1 0 3 3" /></>,
    bell: <><path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4" /></>,
    chevronDown: <path d="m6 9 6 6 6-6" />,
    arrowUpRight: <><path d="M7 17 17 7" /><path d="M8 7h9v9" /></>,
    dots: <><circle cx="5" cy="12" r="1" fill="currentColor" /><circle cx="12" cy="12" r="1" fill="currentColor" /><circle cx="19" cy="12" r="1" fill="currentColor" /></>,
    github: <><path d="M15 22v-3.9c.04-1 .34-1.58.68-1.9 2.24-.25 4.6-1.1 4.6-5.1 0-1.14-.4-2.07-1.08-2.8.11-.27.47-1.32-.1-2.75 0 0-.88-.28-2.88 1.07A10.1 10.1 0 0 0 11 6.62a10.1 10.1 0 0 0-2.62.35C6.38 5.62 5.5 5.9 5.5 5.9c-.57 1.43-.21 2.48-.1 2.75A4.05 4.05 0 0 0 4.32 11.45c0 3.99 2.35 4.84 4.58 5.1.34.32.64.9.68 1.9V22" /><path d="M9 22v-3.9" /></>,
    terminal: <><path d="m5 7 4 5-4 5M12 18h7" /></>,
    globe: <><circle cx="12" cy="12" r="9" /><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18" /></>,
    key: <><circle cx="8" cy="15" r="4" /><path d="m11 12 9-9M15 6l3 3M17 4l3 3" /></>,
    database: <><ellipse cx="12" cy="5" rx="8" ry="3" /><path d="M4 5v7c0 1.66 3.58 3 8 3s8-1.34 8-3V5M4 12v7c0 1.66 3.58 3 8 3s8-1.34 8-3v-7" /></>,
    clock: <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3.5 2" /></>,
    check: <path d="m5 12 4 4L19 6" />,
    warning: <><path d="M10.2 4.1 2.8 17a2 2 0 0 0 1.74 3h14.92A2 2 0 0 0 21.2 17L13.8 4.1a2.08 2.08 0 0 0-3.6 0Z" /><path d="M12 9v4M12 17h.01" /></>,
    x: <path d="m6 6 12 12M18 6 6 18" />,
    copy: <><rect x="8" y="8" width="11" height="11" rx="2" /><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2" /></>,
    refresh: <><path d="M20 11a8 8 0 0 0-14.9-3.9L3 9" /><path d="M3 4v5h5M4 13a8 8 0 0 0 14.9 3.9L21 15" /><path d="M21 20v-5h-5" /></>,
    stop: <rect x="6" y="6" width="12" height="12" rx="2" />,
    moon: <path d="M20.7 15.3A8.5 8.5 0 0 1 8.7 3.3 8.5 8.5 0 1 0 20.7 15.3Z" />,
    menu: <><path d="M4 7h16M4 12h16M4 17h16" /></>,
    filter: <path d="M4 5h16M7 12h10M10 19h4" />,
    activity: <path d="M3 12h3l2.2-6 4.1 12 2.4-7H21" />,
    arrowLeft: <><path d="m15 18-6-6 6-6" /><path d="M9 12h11" /></>,
    trash: <><path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3" /></>,
    lock: <><rect x="5" y="10" width="14" height="10" rx="2" /><path d="M8 10V7a4 4 0 0 1 8 0v3" /></>,
    download: <><path d="M12 3v12M7 10l5 5 5-5M5 21h14" /></>,
    sliders: <><path d="M4 6h16M4 12h16M4 18h16" /><circle cx="9" cy="6" r="2" fill="var(--surface-raised)" /><circle cx="15" cy="12" r="2" fill="var(--surface-raised)" /><circle cx="8" cy="18" r="2" fill="var(--surface-raised)" /></>,
    server: <><rect x="3" y="3" width="18" height="7" rx="2" /><rect x="3" y="14" width="18" height="7" rx="2" /><path d="M7 7h.01M7 18h.01" /></>,
    eye: <><path d="M2.5 12s3.5-6 9.5-6 9.5 6 9.5 6-3.5 6-9.5 6-9.5-6-9.5-6Z" /><circle cx="12" cy="12" r="2.5" /></>,
    eyeOff: <><path d="m3 3 18 18M10.6 6.2A10.7 10.7 0 0 1 12 6c6 0 9.5 6 9.5 6a18 18 0 0 1-3 3.8M6.2 6.2A18.9 18.9 0 0 0 2.5 12S6 18 12 18c1.3 0 2.5-.28 3.6-.73" /><path d="M9.9 9.9a3 3 0 0 0 4.2 4.2" /></>,
    layers: <><path d="m12 3 9 5-9 5-9-5 9-5Z" /><path d="m3 12 9 5 9-5M3 16l9 5 9-5" /></>,
    sparkles: <><path d="m12 3-1.2 4.8L6 9l4.8 1.2L12 15l1.2-4.8L18 9l-4.8-1.2L12 3Z" /><path d="m5 15-.6 2.4L2 18l2.4.6L5 21l.6-2.4L8 18l-2.4-.6L5 15ZM19 15l-.6 2.4L16 18l2.4.6L19 21l.6-2.4L22 18l-2.4-.6L19 15Z" /></>,
    info: <><circle cx="12" cy="12" r="9" /><path d="M12 11v5M12 8h.01" /></>,
  }
  return <svg {...common}>{shapes[name]}</svg>
}

const navItems: { id: Page; label: string; icon: IconName }[] = [
  { id: 'overview', label: 'Overview', icon: 'grid' },
  { id: 'projects', label: 'Projects', icon: 'box' },
  { id: 'deployments', label: 'Deployments', icon: 'rocket' },
  { id: 'operations', label: 'Operations', icon: 'activity' },
  { id: 'resources', label: 'Resources', icon: 'database' },
  { id: 'network', label: 'Network', icon: 'globe' },
  { id: 'templates', label: 'Templates', icon: 'layers' },
  { id: 'observability', label: 'Observability', icon: 'chart' },
  { id: 'team', label: 'Team & access', icon: 'users' },
]

const serviceStatuses: ServiceStatus[] = ['live', 'building', 'queued', 'sleeping', 'stopped', 'failed']

function relativeTime(value: string): string {
  const delta = Math.max(0, Date.now() - new Date(value).getTime())
  const minutes = Math.round(delta / 60_000)
  if (minutes < 1) return 'Just now'
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.round(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.round(hours / 24)
  return `${days}d ago`
}

function initials(name: string): string {
  return name.split(/\s+/).filter(Boolean).slice(0, 2).map((part) => part[0]).join('').toUpperCase() || 'NS'
}

function shortCommit(commit: string): string {
  return commit === 'pending' ? 'pending' : commit.slice(0, 7)
}

function maskValue(value: string): string {
  if (!value) return '••••••••'
  if (value.includes('••')) return value
  return value.length > 8 ? `${value.slice(0, 3)}••••••${value.slice(-2)}` : '••••••••'
}

function StatusPill({ status }: { status: string }) {
  return <span className={`status-pill ${status}`}><span className="status-dot" />{statusLabel(status)}</span>
}

function Avatar({ member, size = 'normal' }: { member: Pick<TeamMember, 'name' | 'initials' | 'color'>; size?: 'small' | 'normal' | 'large' }) {
  return <span className={`avatar ${size}`} style={{ '--avatar-color': member.color } as CSSProperties}>{member.initials || initials(member.name)}</span>
}

function ServiceGlyph({ project, size = 'normal' }: { project: Project; size?: 'small' | 'normal' }) {
  const letters = project.name.split(/\s+/).slice(0, 2).map((word) => word[0]).join('').toUpperCase()
  return <span className={`service-glyph ${size}`}><span>{letters}</span></span>
}

function MetricCard({ icon, label, value, detail, trend, tone = 'default' }: { icon: IconName; label: string; value: string | number; detail: string; trend?: string; tone?: 'default' | 'violet' | 'cyan' | 'orange' }) {
  return (
    <article className={`metric-card ${tone}`}>
      <div className="metric-icon"><Icon name={icon} size={17} /></div>
      <div className="metric-label-row"><span>{label}</span>{trend && <span className="metric-trend">{trend}</span>}</div>
      <strong>{value}</strong>
      <p>{detail}</p>
    </article>
  )
}

function ProgressBar({ value, tone = 'violet' }: { value: number; tone?: 'violet' | 'cyan' | 'green' | 'orange' }) {
  return <span className={`progress-track ${tone}`}><span style={{ width: `${Math.max(0, Math.min(value, 100))}%` }} /></span>
}

function EmptyState({ icon, title, description, action }: { icon: IconName; title: string; description: string; action?: ReactNode }) {
  return <div className="empty-state">
    <span className="empty-icon"><Icon name={icon} size={23} /></span>
    <h3>{title}</h3>
    <p>{description}</p>
    {action}
  </div>
}

function ActivityIcon({ type }: { type: ActivityItem['icon'] }) {
  const icon: Record<ActivityItem['icon'], IconName> = {
    deploy: 'rocket', domain: 'globe', team: 'users', secret: 'key', rollback: 'refresh', service: 'server', resource: 'database', alert: 'warning', security: 'lock', route: 'globe',
  }
  return <span className={`activity-icon ${type}`}><Icon name={icon[type]} size={15} /></span>
}

function App() {
  const [cloud, setCloud] = useState<CloudState>(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY)
      return saved ? hydrateState(JSON.parse(saved)) : seedState()
    } catch {
      return seedState()
    }
  })
  const [page, setPage] = useState<Page>('overview')
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [newServiceOpen, setNewServiceOpen] = useState(false)
  const [templateDraft, setTemplateDraft] = useState<Partial<CreateServiceInput> | null>(null)
  const [newResourceOpen, setNewResourceOpen] = useState(false)
  const [newTokenOpen, setNewTokenOpen] = useState(false)
  const [revealedToken, setRevealedToken] = useState<string | null>(null)
  const [commandOpen, setCommandOpen] = useState(false)
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null)
  const [selectedDeploymentId, setSelectedDeploymentId] = useState<string | null>(null)
  const [inviteOpen, setInviteOpen] = useState(false)
  const [toast, setToast] = useState<string | null>(null)

  const selectedProject = projectById(cloud, selectedProjectId)
  const selectedDeployment = deploymentById(cloud, selectedDeploymentId)

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(cloud))
  }, [cloud])

  useEffect(() => {
    const timer = window.setInterval(() => setCloud((current) => completeProvisioning(appendLiveLog(progressDeployments(current)))), 5000)
    return () => window.clearInterval(timer)
  }, [])

  useEffect(() => {
    if (!toast) return undefined
    const timer = window.setTimeout(() => setToast(null), 3500)
    return () => window.clearTimeout(timer)
  }, [toast])

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const element = event.target as HTMLElement
      const typing = ['INPUT', 'TEXTAREA', 'SELECT'].includes(element.tagName) || element.isContentEditable
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault()
        setCommandOpen(true)
      }
      if (event.key === 'Escape') {
        setCommandOpen(false)
        setNewServiceOpen(false)
        setNewResourceOpen(false)
        setNewTokenOpen(false)
        setRevealedToken(null)
        setInviteOpen(false)
        setSelectedProjectId(null)
        setSelectedDeploymentId(null)
      }
      if (!typing && event.key.toLowerCase() === 'n') {
        event.preventDefault()
        setNewServiceOpen(true)
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [])

  const openProject = (id: string) => {
    setSelectedProjectId(id)
    setSidebarOpen(false)
  }

  const navigate = (nextPage: Page) => {
    setPage(nextPage)
    setSidebarOpen(false)
  }

  const notify = (message: string) => setToast(message)

  const handleCreateService = (input: CreateServiceInput) => {
    const result = createService(cloud, input)
    setCloud(result.state)
    setNewServiceOpen(false)
    setSelectedProjectId(result.project.id)
    notify(`${result.project.name} was queued for deployment.`)
  }

  const handleDeployment = (projectId: string) => {
    const result = requestDeployment(cloud, projectId)
    setCloud(result.state)
    if (result.deployment) {
      setSelectedDeploymentId(result.deployment.id)
      notify('A new deployment is queued.')
    }
  }

  const handlePreviewDeployment = (projectId: string) => {
    const result = requestPreviewDeployment(cloud, projectId)
    setCloud(result.state)
    if (result.deployment) {
      setSelectedDeploymentId(result.deployment.id)
      notify('Preview deployment queued. It will not change production traffic.')
    }
  }

  const handleApproveDeployment = (deploymentId: string) => {
    setCloud((current) => approveDeployment(current, deploymentId))
    notify('Production promotion approved. Release checks will continue.')
  }

  const handleCanaryTraffic = (deploymentId: string, percent: number) => {
    setCloud((current) => setCanaryTraffic(current, deploymentId, percent))
    notify(`Canary traffic moved to ${percent}%.`)
  }

  const handleProjectStatus = (projectId: string, status: ServiceStatus) => {
    setCloud((current) => setProjectStatus(current, projectId, status))
    notify(status === 'stopped' ? 'Service stopped.' : 'Service updated.')
  }

  const handleRollback = (projectId: string) => {
    const result = rollbackProject(cloud, projectId)
    if (result.success) {
      setCloud(result.state)
      notify('Rollback complete. The previous healthy deployment is live.')
    } else {
      notify('A previous live deployment is required before rollback.')
    }
  }

  const handleAddEnv = (projectId: string, variable: Omit<EnvironmentVariable, 'id'>) => {
    setCloud((current) => addEnvironmentVariable(current, projectId, variable))
    notify(`${variable.name.toUpperCase()} saved locally.`)
  }

  const handleAddDomain = (projectId: string, hostname: string) => {
    if (!hostname.trim()) return
    setCloud((current) => addDomain(current, projectId, hostname))
    notify('Domain added. Point its DNS record to continue verification.')
  }

  const handleInvite = (name: string, email: string, role: TeamMember['role']) => {
    const member: TeamMember = {
      id: makeId('team'),
      initials: initials(name),
      name,
      email,
      role,
      color: ['#8b5cf6', '#06b6d4', '#f97316', '#ec4899'][cloud.team.length % 4],
      lastActive: 'Invitation pending',
    }
    setCloud((current) => {
      const next = cloneState(current)
      next.team.push(member)
      next.activity.unshift({
        id: makeId('act'), icon: 'team', title: `${name} was invited`, detail: `Invitation created for ${role} access`, createdAt: new Date().toISOString(),
      })
      return next
    })
    setInviteOpen(false)
    notify(`Invitation created for ${email}.`)
  }

  const handleCreateResource = (input: CreateResourceInput) => {
    const result = createResource(cloud, input)
    setCloud(result.state)
    setNewResourceOpen(false)
    notify(`${result.resource.name} is provisioning in ${result.resource.region}.`)
  }

  const handleCreateToken = (name: string, scopes: string[]) => {
    const result = createApiToken(cloud, name, scopes)
    setCloud(result.state)
    setNewTokenOpen(false)
    if (result.token) {
      setRevealedToken(result.token)
      notify('A new scoped API token was created.')
    }
  }

  const exportConfiguration = () => {
    const safeCopy = cloneState(cloud)
    safeCopy.projects = safeCopy.projects.map((project) => ({
      ...project,
      environment: project.environment.map((variable) => ({ ...variable, value: variable.secret ? '[REDACTED]' : variable.value })),
    }))
    const blob = new Blob([JSON.stringify(safeCopy, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = 'northstar-cloud-export.json'
    anchor.click()
    URL.revokeObjectURL(url)
    notify('Redacted workspace export downloaded.')
  }

  const resetDemo = () => {
    if (!window.confirm('Reset all local demo data? This cannot be undone.')) return
    setCloud(seedState())
    setSelectedProjectId(null)
    setSelectedDeploymentId(null)
    notify('The local demo workspace was reset.')
  }

  const pageMeta: Record<Page, { eyebrow: string; title: string; text: string }> = {
    overview: { eyebrow: 'Workspace', title: 'Good afternoon, Ava', text: 'Your services are healthy and ready to ship.' },
    projects: { eyebrow: 'Workspace', title: 'Projects', text: 'Everything you deploy, in one focused workspace.' },
    deployments: { eyebrow: 'Delivery', title: 'Deployments', text: 'Track builds, releases, and safe rollbacks.' },
    operations: { eyebrow: 'Operations', title: 'Operations center', text: 'Stream logs, manage alerts, and coordinate incidents.' },
    resources: { eyebrow: 'Infrastructure', title: 'Resources', text: 'Databases, caches, volumes, workers, and scheduled jobs.' },
    network: { eyebrow: 'Edge', title: 'Network', text: 'Domains, TLS, redirects, rewrites, and edge routing.' },
    templates: { eyebrow: 'Accelerate', title: 'Templates', text: 'Start production-shaped services in a few focused steps.' },
    observability: { eyebrow: 'Operations', title: 'Observability', text: 'A calm, useful view of traffic and service health.' },
    team: { eyebrow: 'Workspace', title: 'Team & access', text: 'Give each collaborator exactly the access they need.' },
    settings: { eyebrow: 'Workspace', title: 'Settings', text: 'Configure your local Northstar experience.' },
  }

  return <div className={`app-shell ${cloud.preferences.compactMode ? 'compact' : ''}`}>
    <aside className={`sidebar ${sidebarOpen ? 'open' : ''}`} aria-label="Primary navigation">
      <div className="brand-row">
        <button className="brand" onClick={() => navigate('overview')} aria-label="Go to overview">
          <span className="brand-mark"><i /><i /><i /></span>
          <span>northstar</span>
        </button>
        <button className="icon-button sidebar-close" onClick={() => setSidebarOpen(false)} aria-label="Close navigation"><Icon name="x" /></button>
      </div>

      <button className="workspace-switcher" onClick={() => notify('Workspace switching is ready to connect to your auth layer.')}>
        <span className="workspace-symbol">N</span>
        <span><strong>Northstar Labs</strong><small>Personal workspace</small></span>
        <Icon name="chevronDown" size={16} />
      </button>

      <nav className="navigation">
        <span className="nav-label">Workspace</span>
        {navItems.map((item) => <button key={item.id} onClick={() => navigate(item.id)} className={`nav-item ${page === item.id ? 'active' : ''}`}>
          <Icon name={item.icon} size={18} /><span>{item.label}</span>
        </button>)}
        <div className="nav-spacer" />
        <span className="nav-label">Manage</span>
        <button onClick={() => navigate('settings')} className={`nav-item ${page === 'settings' ? 'active' : ''}`}><Icon name="settings" size={18} /><span>Settings</span></button>
      </nav>

      <div className="sidebar-bottom">
        <div className="plan-card">
          <span className="plan-icon"><Icon name="sparkles" size={15} /></span>
          <div><strong>Pro workspace</strong><p>Usage resets in 12 days</p></div>
          <button onClick={() => notify('Billing is a prototype screen — connect Stripe or your billing provider for production.')} aria-label="View plan"><Icon name="arrowUpRight" size={15} /></button>
        </div>
        <button className="user-card" onClick={() => navigate('team')}>
          <Avatar member={cloud.team[0]} size="small" />
          <span><strong>Ava Johnson</strong><small>ava@northstar.dev</small></span>
          <Icon name="dots" size={17} />
        </button>
      </div>
    </aside>

    {sidebarOpen && <button className="sidebar-scrim" aria-label="Close navigation" onClick={() => setSidebarOpen(false)} />}

    <main className="main-content">
      <header className="topbar">
        <button className="icon-button mobile-menu" onClick={() => setSidebarOpen(true)} aria-label="Open navigation"><Icon name="menu" /></button>
        <div className="breadcrumbs"><span>Northstar Labs</span><span className="breadcrumb-separator">/</span><strong>{pageMeta[page].title}</strong></div>
        <div className="topbar-actions">
          <button className="command-trigger" onClick={() => setCommandOpen(true)}><Icon name="search" size={16} /><span>Search or jump to…</span><kbd>⌘ K</kbd></button>
          <button className="icon-button notification-button" onClick={() => notify('You are all caught up.')} aria-label="Notifications"><Icon name="bell" size={18} /><span /></button>
          <button className="avatar-button" onClick={() => navigate('team')} aria-label="Open team"><Avatar member={cloud.team[0]} size="small" /></button>
        </div>
      </header>

      <div className="page-scroll">
        {page === 'overview' && <OverviewPage cloud={cloud} onOpenProject={openProject} onNewService={() => { setTemplateDraft(null); setNewServiceOpen(true) }} onDeploy={handleDeployment} onViewDeployment={setSelectedDeploymentId} />}
        {page === 'projects' && <ProjectsPage projects={cloud.projects} onOpenProject={openProject} onNewService={() => { setTemplateDraft(null); setNewServiceOpen(true) }} />}
        {page === 'deployments' && <DeploymentsPage deployments={cloud.deployments} projects={cloud.projects} onOpenDeployment={setSelectedDeploymentId} onDeploy={handleDeployment} onPreview={handlePreviewDeployment} />}
        {page === 'operations' && <OperationsPage cloud={cloud} onOpenProject={openProject} onToggleLogs={(enabled) => setCloud((current) => ({ ...current, preferences: { ...current.preferences, liveLogs: enabled } }))} onToggleAlert={(id) => setCloud((current) => toggleAlert(current, id))} onResolveIncident={(id) => setCloud((current) => resolveIncident(current, id))} onNotify={notify} />}
        {page === 'resources' && <ResourcesPage cloud={cloud} onNewResource={() => setNewResourceOpen(true)} onToggleJob={(id) => setCloud((current) => toggleJob(current, id))} onOpenProject={openProject} />}
        {page === 'network' && <NetworkPage cloud={cloud} onOpenProject={openProject} onAddDomain={handleAddDomain} onAddRoute={(route) => setCloud((current) => addNetworkRoute(current, route))} onToggleRoute={(id) => setCloud((current) => toggleRoute(current, id))} onRemoveRoute={(id) => setCloud((current) => removeRoute(current, id))} onNotify={notify} />}
        {page === 'templates' && <TemplatesPage onUseTemplate={(draft) => { setTemplateDraft(draft); setNewServiceOpen(true) }} />}
        {page === 'observability' && <ObservabilityPage cloud={cloud} onOpenProject={openProject} />}
        {page === 'team' && <TeamPage cloud={cloud} onInvite={() => setInviteOpen(true)} onCreateToken={() => setNewTokenOpen(true)} onRevokeToken={(id) => setCloud((current) => revokeApiToken(current, id))} onUpdatePolicy={(patch) => setCloud((current) => updateDeploymentPolicy(current, patch))} onUpdateBilling={(patch) => setCloud((current) => updateBilling(current, patch))} onNotify={notify} />}
        {page === 'settings' && <SettingsPage cloud={cloud} onChange={(patch) => setCloud((current) => ({ ...current, preferences: { ...current.preferences, ...patch } }))} onExport={exportConfiguration} onReset={resetDemo} />}
      </div>
    </main>

    {newServiceOpen && <DeployWizard initialValues={templateDraft ?? undefined} onClose={() => { setNewServiceOpen(false); setTemplateDraft(null) }} onCreate={handleCreateService} />}
    {newResourceOpen && <ResourceModal projects={cloud.projects} onClose={() => setNewResourceOpen(false)} onCreate={handleCreateResource} />}
    {newTokenOpen && <TokenModal onClose={() => setNewTokenOpen(false)} onCreate={handleCreateToken} />}
    {revealedToken && <TokenRevealModal token={revealedToken} onClose={() => setRevealedToken(null)} />}
    {selectedProject && <ProjectDrawer project={selectedProject} deployments={cloud.deployments.filter((item) => item.projectId === selectedProject.id)} onClose={() => setSelectedProjectId(null)} onDeploy={() => handleDeployment(selectedProject.id)} onSetStatus={(status) => handleProjectStatus(selectedProject.id, status)} onRollback={() => handleRollback(selectedProject.id)} onAddEnvironment={(variable) => handleAddEnv(selectedProject.id, variable)} onRemoveEnvironment={(id) => setCloud((current) => removeEnvironmentVariable(current, selectedProject.id, id))} onAddDomain={(hostname) => handleAddDomain(selectedProject.id, hostname)} onRemoveDomain={(id) => setCloud((current) => removeDomain(current, selectedProject.id, id))} onViewDeployment={setSelectedDeploymentId} onNotify={notify} />}
    {selectedDeployment && <DeploymentModal deployment={selectedDeployment} project={projectById(cloud, selectedDeployment.projectId)} onClose={() => setSelectedDeploymentId(null)} onOpenProject={() => { setSelectedDeploymentId(null); setSelectedProjectId(selectedDeployment.projectId) }} onApprove={() => handleApproveDeployment(selectedDeployment.id)} onSetCanary={(percent) => handleCanaryTraffic(selectedDeployment.id, percent)} />}
    {commandOpen && <CommandPalette projects={cloud.projects} onClose={() => setCommandOpen(false)} onNavigate={navigate} onNewService={() => { setCommandOpen(false); setTemplateDraft(null); setNewServiceOpen(true) }} onOpenProject={(id) => { setCommandOpen(false); openProject(id) }} />}
    {inviteOpen && <InviteModal onClose={() => setInviteOpen(false)} onInvite={handleInvite} />}
    {toast && <div className="toast" role="status"><span><Icon name="check" size={17} /></span>{toast}<button onClick={() => setToast(null)} aria-label="Dismiss notification"><Icon name="x" size={15} /></button></div>}
  </div>
}

function OverviewPage({ cloud, onOpenProject, onNewService, onDeploy, onViewDeployment }: { cloud: CloudState; onOpenProject: (id: string) => void; onNewService: () => void; onDeploy: (id: string) => void; onViewDeployment: (id: string) => void }) {
  const live = cloud.projects.filter((project) => project.status === 'live').length
  const activeDeployment = cloud.deployments.find((deployment) => ['queued', 'building', 'deploying'].includes(deployment.status))
  const activeProject = activeDeployment ? cloud.projects.find((project) => project.id === activeDeployment.projectId) : undefined
  const healthy = cloud.projects.filter((project) => project.health >= 99.9).length

  return <div className="page-content overview-page">
    <section className="welcome-row">
      <div><p className="eyebrow">Workspace overview</p><h1>Good afternoon, Ava <span>✦</span></h1><p className="page-intro">Your infrastructure is calm, healthy, and ready for the next release.</p></div>
      <button className="primary-button" onClick={onNewService}><Icon name="plus" size={17} />New service</button>
    </section>

    <section className="metric-grid" aria-label="Workspace metrics">
      <MetricCard icon="server" label="Live services" value={`${live} / ${cloud.projects.length}`} detail="Across 3 regions" trend="All healthy" tone="violet" />
      <MetricCard icon="rocket" label="Deployments" value="24" detail="in the last 30 days" trend="↑ 18%" tone="cyan" />
      <MetricCard icon="activity" label="Requests" value="3.07M" detail="in the last 30 days" trend="↑ 12.4%" tone="orange" />
      <MetricCard icon="check" label="Health checks" value={`${healthy}/${cloud.projects.length}`} detail="passing at last check" trend="99.99%" />
    </section>

    <section className="overview-layout">
      <div className="content-stack">
        <div className="section-heading"><div><p className="eyebrow">Deploy now</p><h2>Ship a change</h2></div><button className="text-button" onClick={() => { const target = activeDeployment?.id ?? cloud.deployments[0]?.id; if (target) onViewDeployment(target) }}>{activeDeployment ? 'View activity' : 'View history'}<Icon name="arrowUpRight" size={15} /></button></div>
        <article className="deployment-hero">
          <div className="deployment-hero-glow" />
          <div className="deployment-hero-top">
            <span className="hero-icon"><Icon name="rocket" size={20} /></span>
            <div className="hero-copy"><p>{activeDeployment ? 'Current deployment' : 'Latest deployment'}</p><h3>{activeProject?.name ?? cloud.projects[0]?.name}</h3><span>{activeDeployment ? 'Release in progress — logs are updating automatically.' : 'Production is serving the last healthy release.'}</span></div>
            <StatusPill status={activeDeployment?.status ?? 'live'} />
          </div>
          {activeDeployment ? <>
            <div className="deploy-progress-row"><span>{statusLabel(activeDeployment.status)}</span><strong>{activeDeployment.progress}%</strong></div><ProgressBar value={activeDeployment.progress} tone="cyan" />
            <div className="deployment-hero-footer"><span><Icon name="github" size={15} />{activeProject?.repository}</span><span><Icon name="clock" size={15} />Started {relativeTime(activeDeployment.createdAt)}</span><button className="soft-button small" onClick={() => onViewDeployment(activeDeployment.id)}>Open logs <Icon name="arrowUpRight" size={14} /></button></div>
          </> : <div className="deployment-empty"><span>Everything is deployed.</span><button className="soft-button small" onClick={() => onDeploy(cloud.projects[0].id)}><Icon name="rocket" size={14} />Deploy again</button></div>}
        </article>

        <div className="section-heading services-heading"><div><p className="eyebrow">Services</p><h2>Your projects</h2></div><button className="text-button" onClick={() => onOpenProject(cloud.projects[0].id)}>Manage all <Icon name="arrowUpRight" size={15} /></button></div>
        <div className="overview-project-list">
          {cloud.projects.slice(0, 4).map((project) => <button className="project-list-row" key={project.id} onClick={() => onOpenProject(project.id)}>
            <ServiceGlyph project={project} size="small" />
            <span className="project-list-name"><strong>{project.name}</strong><small>{project.framework} · {project.region}</small></span>
            <StatusPill status={project.status} />
            <span className="project-list-stat"><strong>{project.latency}</strong><small>latency</small></span>
            <Icon name="arrowUpRight" size={16} />
          </button>)}
        </div>
      </div>

      <aside className="activity-panel">
        <div className="section-heading"><div><p className="eyebrow">Live feed</p><h2>Recent activity</h2></div><button className="icon-button subtle" onClick={() => onViewDeployment(cloud.deployments[0].id)} aria-label="View deployments"><Icon name="dots" size={17} /></button></div>
        <div className="activity-list">
          {cloud.activity.slice(0, 5).map((item) => <button className="activity-row" key={item.id} onClick={() => item.projectId && onOpenProject(item.projectId)}>
            <ActivityIcon type={item.icon} /><span><strong>{item.title}</strong><small>{item.detail}</small></span><time>{relativeTime(item.createdAt)}</time>
          </button>)}
        </div>
        <div className="activity-footer"><span><i />All systems operational</span><button onClick={() => onOpenProject(cloud.projects[0].id)}>Status <Icon name="arrowUpRight" size={13} /></button></div>
      </aside>
    </section>
  </div>
}

function ProjectsPage({ projects, onOpenProject, onNewService }: { projects: Project[]; onOpenProject: (id: string) => void; onNewService: () => void }) {
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState<'all' | ServiceStatus>('all')
  const filtered = projects.filter((project) => (filter === 'all' || project.status === filter) && `${project.name} ${project.repository} ${project.framework}`.toLowerCase().includes(query.toLowerCase()))
  return <div className="page-content">
    <section className="page-title-row"><div><p className="eyebrow">Workspace</p><h1>Projects</h1><p className="page-intro">Deploy frontend apps, APIs, workers, and any containerized service.</p></div><button className="primary-button" onClick={onNewService}><Icon name="plus" size={17} />New service</button></section>
    <div className="toolbar"><label className="search-field"><Icon name="search" size={17} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search projects" /></label><div className="filter-pills" aria-label="Project status filter">{(['all', 'live', 'building', 'sleeping', 'stopped'] as const).map((item) => <button key={item} onClick={() => setFilter(item)} className={filter === item ? 'selected' : ''}>{item === 'all' ? 'All services' : statusLabel(item)}</button>)}</div></div>
    {filtered.length ? <div className="project-grid">{filtered.map((project) => <ProjectCard key={project.id} project={project} onOpen={() => onOpenProject(project.id)} />)}</div> : <EmptyState icon="search" title="No matching services" description="Try another search or create a new service." action={<button className="soft-button" onClick={onNewService}>Create service</button>} />}
  </div>
}

function ProjectCard({ project, onOpen }: { project: Project; onOpen: () => void }) {
  return <article className="project-card">
    <div className="project-card-top"><ServiceGlyph project={project} /><button className="icon-button subtle" onClick={onOpen} aria-label={`Open ${project.name}`}><Icon name="dots" size={18} /></button></div>
    <button className="project-card-main" onClick={onOpen}><div className="project-card-title"><h2>{project.name}</h2><StatusPill status={project.status} /></div><p>{project.description}</p><span className="repo-line"><Icon name="github" size={15} />{project.repository}<span>·</span>{project.branch}</span></button>
    <div className="project-stat-grid"><span><small>Requests</small><strong>{project.requests}</strong></span><span><small>Latency</small><strong>{project.latency}</strong></span><span><small>Region</small><strong>{project.region.split(',')[0]}</strong></span></div>
    <button className="project-card-footer" onClick={onOpen}><span>Updated {relativeTime(project.updatedAt)}</span><span>Open <Icon name="arrowUpRight" size={14} /></span></button>
  </article>
}

function DeploymentsPage({ deployments, projects, onOpenDeployment, onDeploy, onPreview }: { deployments: Deployment[]; projects: Project[]; onOpenDeployment: (id: string) => void; onDeploy: (id: string) => void; onPreview: (id: string) => void }) {
  const [filter, setFilter] = useState<'all' | 'active' | 'live' | 'preview'>('all')
  const [target, setTarget] = useState(projects[0]?.id ?? '')
  const filtered = deployments.filter((deployment) => {
    if (filter === 'all') return true
    if (filter === 'active') return ['queued', 'building', 'deploying'].includes(deployment.status)
    if (filter === 'preview') return deployment.environment === 'preview'
    return deployment.status === 'live'
  })
  const waitingForApproval = deployments.filter((item) => item.approvalState === 'pending' && item.status === 'deploying').length
  return <div className="page-content">
    <section className="page-title-row"><div><p className="eyebrow">Delivery</p><h1>Deployments</h1><p className="page-intro">Preview, validate, approve, canary, and roll back each release with a visible trail.</p></div><div className="page-actions"><select className="compact-select" value={target} onChange={(event) => setTarget(event.target.value)} aria-label="Target service">{projects.map((project) => <option key={project.id} value={project.id}>{project.name}</option>)}</select><button className="soft-button" onClick={() => target && onPreview(target)}><Icon name="layers" size={16} />Create preview</button><button className="primary-button" onClick={() => target && onDeploy(target)}><Icon name="rocket" size={17} />Deploy production</button></div></section>
    <section className="pipeline-overview-card"><div className="pipeline-overview-title"><span className="pipeline-emblem"><Icon name="rocket" size={18} /></span><div><p className="eyebrow">Protected delivery</p><h2>Build → preview → approval → canary → production</h2><span>Production deployments pause at the approval gate and begin at 10% canary traffic.</span></div></div><div className="pipeline-overview-stats"><span><strong>{waitingForApproval}</strong><small>approval gates</small></span><span><strong>10%</strong><small>default canary</small></span><span><strong>2</strong><small>rollback-ready releases</small></span></div></section>
    <div className="deploy-summary-grid"><article><span className="summary-ring green"><Icon name="check" size={19} /></span><div><strong>{deployments.filter((item) => item.status === 'live').length}</strong><span>successful releases</span></div></article><article><span className="summary-ring violet"><Icon name="rocket" size={18} /></span><div><strong>{deployments.filter((item) => ['queued', 'building', 'deploying'].includes(item.status)).length}</strong><span>active deployments</span></div></article><article><span className="summary-ring orange"><Icon name="clock" size={18} /></span><div><strong>1m 26s</strong><span>average build time</span></div></article></div>
    <div className="deployment-table-card"><div className="table-toolbar"><div className="filter-pills">{(['all', 'active', 'preview', 'live'] as const).map((item) => <button key={item} className={filter === item ? 'selected' : ''} onClick={() => setFilter(item)}>{item === 'all' ? 'All' : item === 'active' ? 'In progress' : item === 'preview' ? 'Previews' : 'Successful'}</button>)}</div><button className="icon-button subtle" aria-label="Filter deployments"><Icon name="filter" size={17} /></button></div>
      <div className="deployment-table-head advanced"><span>Deployment</span><span>Environment</span><span>Pipeline</span><span>Status</span><span>Started</span><span /></div>
      <div className="deployment-table-body">{filtered.map((deployment) => { const project = projects.find((item) => item.id === deployment.projectId); return <button key={deployment.id} className="deployment-table-row advanced" onClick={() => onOpenDeployment(deployment.id)}><span className="deployment-cell-main"><ServiceGlyph project={project ?? fallbackProject} size="small" /><span><strong>{project?.name ?? 'Unknown service'}</strong><small><code>{shortCommit(deployment.commit)}</code>{deployment.message}</small></span></span><span className={`environment-badge ${deployment.environment ?? 'production'}`}>{deployment.environment === 'preview' ? 'Preview' : 'Production'}</span><span className="pipeline-cell"><strong>{deployment.strategy === 'canary' ? `${deployment.canaryPercent ?? 10}% canary` : 'Direct'}</strong><small>{deployment.approvalState === 'pending' ? 'Approval required' : deployment.approvalState === 'approved' ? 'Approved' : 'No approval'}</small></span><StatusPill status={deployment.status} /><span>{relativeTime(deployment.createdAt)}</span><Icon name="arrowUpRight" size={16} /></button> })}</div>
    </div>
  </div>
}

const fallbackProject: Project = { id: 'unknown', name: 'Unknown', description: '', repository: '', branch: '', framework: '', runtime: '', region: '', status: 'failed', url: '', health: 0, requests: '', bandwidth: '', latency: '', cpu: 0, memory: 0, plan: '', replicas: 0, lastDeploymentId: '', createdAt: '', updatedAt: '', environment: [], domains: [] }

function OperationsPage({ cloud, onOpenProject, onToggleLogs, onToggleAlert, onResolveIncident, onNotify }: { cloud: CloudState; onOpenProject: (id: string) => void; onToggleLogs: (enabled: boolean) => void; onToggleAlert: (id: string) => void; onResolveIncident: (id: string) => void; onNotify: (message: string) => void }) {
  const [tab, setTab] = useState<'logs' | 'alerts' | 'incidents'>('logs')
  const [query, setQuery] = useState('')
  const [level, setLevel] = useState<'all' | 'info' | 'warn' | 'error' | 'debug'>('all')
  const visibleLogs = cloud.logs.filter((log) => (level === 'all' || log.level === level) && `${log.message} ${log.requestId} ${log.region}`.toLowerCase().includes(query.toLowerCase()))
  const openIncidents = cloud.incidents.filter((incident) => incident.state !== 'resolved').length
  return <div className="page-content operations-page">
    <section className="page-title-row"><div><p className="eyebrow">Operations</p><h1>Operations center</h1><p className="page-intro">See release activity, stream safe demo logs, and respond to alerts without context switching.</p></div><div className="page-actions"><span className="live-stream-indicator"><i className={cloud.preferences.liveLogs ? 'on' : ''} />{cloud.preferences.liveLogs ? 'Live stream connected' : 'Stream paused'}</span><button className="soft-button" onClick={() => onToggleLogs(!cloud.preferences.liveLogs)}><Icon name={cloud.preferences.liveLogs ? 'stop' : 'activity'} size={15} />{cloud.preferences.liveLogs ? 'Pause stream' : 'Resume stream'}</button></div></section>
    <section className="ops-kpi-grid"><article><span className="ops-kpi-icon"><Icon name="activity" size={18} /></span><div><strong>{cloud.logs.length}</strong><small>events retained locally</small></div></article><article><span className="ops-kpi-icon orange"><Icon name="warning" size={18} /></span><div><strong>{cloud.alerts.filter((alert) => alert.state === 'triggered').length}</strong><small>alerts need attention</small></div></article><article><span className="ops-kpi-icon violet"><Icon name="clock" size={18} /></span><div><strong>{openIncidents}</strong><small>open incidents</small></div></article><article><span className="ops-kpi-icon green"><Icon name="check" size={18} /></span><div><strong>99.99%</strong><small>30-day availability</small></div></article></section>
    <div className="ops-tabs"><button className={tab === 'logs' ? 'active' : ''} onClick={() => setTab('logs')}><Icon name="terminal" size={15} />Logs</button><button className={tab === 'alerts' ? 'active' : ''} onClick={() => setTab('alerts')}><Icon name="warning" size={15} />Alerts <span>{cloud.alerts.filter((alert) => alert.state === 'triggered').length}</span></button><button className={tab === 'incidents' ? 'active' : ''} onClick={() => setTab('incidents')}><Icon name="activity" size={15} />Incidents</button></div>
    {tab === 'logs' && <section className="logs-workspace"><div className="logs-toolbar"><label className="search-field"><Icon name="search" size={16} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search message, request ID, or region" /></label><div className="filter-pills">{(['all', 'info', 'warn', 'error', 'debug'] as const).map((item) => <button key={item} className={level === item ? 'selected' : ''} onClick={() => setLevel(item)}>{item}</button>)}</div><button className="soft-button small" onClick={() => onNotify('Filtered demo logs are ready to export after a production API is connected.')}><Icon name="download" size={14} />Export</button></div><div className="live-log-terminal"><div className="terminal-title"><span><i /><i /><i /></span><strong>northstar / live events</strong><small>{visibleLogs.length} matching events</small></div><div className="live-log-body">{visibleLogs.map((log) => { const project = cloud.projects.find((item) => item.id === log.projectId); return <button key={log.id} className={`live-log-line ${log.level}`} onClick={() => onOpenProject(log.projectId)}><time>{new Date(log.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}</time><span className="log-level">{log.level}</span><span className="log-project">{project?.name ?? log.projectId}</span><code>{log.message}</code><span className="log-meta">{log.region} · {log.requestId}</span></button>})}{!visibleLogs.length && <EmptyState icon="search" title="No matching logs" description="Change the search or severity filter to see other local events." />}</div></div><p className="local-callout"><Icon name="lock" size={14} />Demo log stream only — production logs should be redacted server-side, access-controlled, and retained by policy.</p></section>}
    {tab === 'alerts' && <section className="operations-card"><div className="operations-card-heading"><div><p className="eyebrow">Alert rules</p><h2>Signal before noise</h2><span>Rules are scoped to a service and can notify the right team channel.</span></div><button className="soft-button" onClick={() => onNotify('Alert rule creation would be backed by your monitoring API.') }><Icon name="plus" size={15} />New rule</button></div><div className="alert-list">{cloud.alerts.map((alert) => { const project = cloud.projects.find((item) => item.id === alert.projectId); return <div className="alert-row" key={alert.id}><span className={`alert-state ${alert.state}`}><Icon name={alert.state === 'triggered' ? 'warning' : 'check'} size={15} /></span><span className="alert-copy"><strong>{alert.name}</strong><small>{project?.name ?? 'Workspace'} · {alert.metric} {alert.threshold} {alert.window}</small></span><span className="alert-channel">{alert.channel}</span><StatusPill status={alert.state} /><Toggle checked={alert.enabled} onChange={() => onToggleAlert(alert.id)} /></div>})}</div></section>}
    {tab === 'incidents' && <section className="incident-stack">{cloud.incidents.map((incident) => { const project = cloud.projects.find((item) => item.id === incident.projectId); return <article className={`incident-card ${incident.severity}`} key={incident.id}><div className="incident-card-head"><span className="incident-severity">{incident.severity}</span><StatusPill status={incident.state} /><time>Updated {relativeTime(incident.updatedAt)}</time></div><h2>{incident.title}</h2><p>{project?.name ?? 'Workspace'} · Opened {relativeTime(incident.createdAt)}</p><ol>{incident.timeline.slice(-3).map((event, index) => <li key={`${event}-${index}`}>{event}</li>)}</ol><footer>{incident.state !== 'resolved' ? <button className="soft-button small" onClick={() => onResolveIncident(incident.id)}><Icon name="check" size={14} />Mark resolved</button> : <span className="resolved-note"><Icon name="check" size={14} />Resolved</span>}<button className="text-button" onClick={() => incident.projectId && onOpenProject(incident.projectId)}>Open service <Icon name="arrowUpRight" size={14} /></button></footer></article>})}</section>}
  </div>
}

function ResourcesPage({ cloud, onNewResource, onToggleJob, onOpenProject }: { cloud: CloudState; onNewResource: () => void; onToggleJob: (id: string) => void; onOpenProject: (id: string) => void }) {
  const [tab, setTab] = useState<'resources' | 'jobs'>('resources')
  const resourcesByKind = cloud.resources.reduce<Record<string, number>>((summary, resource) => ({ ...summary, [resource.kind]: (summary[resource.kind] ?? 0) + 1 }), {})
  return <div className="page-content resources-page">
    <section className="page-title-row"><div><p className="eyebrow">Infrastructure</p><h1>Resources</h1><p className="page-intro">Provision stateful resources alongside the apps and workers that rely on them.</p></div><button className="primary-button" onClick={onNewResource}><Icon name="plus" size={17} />New resource</button></section>
    <section className="resource-topology"><div className="topology-copy"><span className="topology-icon"><Icon name="database" size={20} /></span><div><p className="eyebrow">Environment topology</p><h2>{cloud.resources.length} managed resources across 3 regions</h2><span>Connections are masked. The production implementation should inject credentials through a server-side secret manager.</span></div></div><div className="kind-summary">{Object.entries(resourcesByKind).map(([kind, count]) => <span key={kind}><strong>{count}</strong><small>{kind}</small></span>)}</div></section>
    <div className="ops-tabs resource-tabs"><button className={tab === 'resources' ? 'active' : ''} onClick={() => setTab('resources')}><Icon name="database" size={15} />Managed resources</button><button className={tab === 'jobs' ? 'active' : ''} onClick={() => setTab('jobs')}><Icon name="clock" size={15} />Jobs & workers <span>{cloud.jobs.length}</span></button></div>
    {tab === 'resources' && <section className="resource-card-grid">{cloud.resources.map((resource) => { const project = cloud.projects.find((item) => item.id === resource.projectId); return <article className="managed-resource-card" key={resource.id}><div className="managed-resource-head"><span className={`resource-kind-icon ${resource.kind.toLowerCase().replace(/\s+/g, '-')}`}><Icon name={resource.kind === 'PostgreSQL' ? 'database' : resource.kind === 'Redis' ? 'layers' : 'server'} size={17} /></span><StatusPill status={resource.status} /></div><h2>{resource.name}</h2><p>{resource.kind} · {resource.plan}</p><div className="resource-usage"><span><small>Usage</small><strong>{resource.usageLabel}</strong></span><ProgressBar value={resource.usage} tone={resource.usage > 75 ? 'orange' : 'cyan'} /></div><div className="resource-details"><span><Icon name="globe" size={14} />{resource.region}</span><span><Icon name="server" size={14} />{resource.size}</span><span><Icon name="refresh" size={14} />{resource.backups ? 'Backups enabled' : 'No snapshots'}</span></div><footer><button className="text-button" onClick={() => resource.projectId && onOpenProject(resource.projectId)}>{project?.name ?? 'No attached service'} <Icon name="arrowUpRight" size={13} /></button><button className="icon-button subtle" onClick={() => navigator.clipboard?.writeText(resource.connection).catch(() => undefined)} aria-label={`Copy ${resource.name} connection`}><Icon name="copy" size={15} /></button></footer></article>})}</section>}
    {tab === 'jobs' && <section className="jobs-card"><div className="jobs-card-heading"><div><p className="eyebrow">Runtime work</p><h2>Schedules and workers</h2><span>Pause a job without changing the source repository.</span></div><button className="soft-button" onClick={() => onNewResource()}><Icon name="plus" size={15} />Add worker</button></div><div className="job-list">{cloud.jobs.map((job) => { const project = cloud.projects.find((item) => item.id === job.projectId); return <div className="job-row" key={job.id}><span className={`job-type ${job.type}`}><Icon name={job.type === 'cron' ? 'clock' : 'activity'} size={16} /></span><span className="job-copy"><strong>{job.name}</strong><small>{project?.name ?? job.projectId} · {job.schedule}</small></span><span className="job-run"><small>Last run</small><strong>{job.lastRun}</strong></span><span className="job-run"><small>Next</small><strong>{job.nextRun}</strong></span><StatusPill status={job.status} /><button className="soft-button small" onClick={() => onToggleJob(job.id)}>{job.status === 'running' ? <><Icon name="stop" size={13} />Pause</> : <><Icon name="activity" size={13} />Resume</>}</button></div>})}</div></section>}
  </div>
}

function NetworkPage({ cloud, onOpenProject, onAddDomain, onAddRoute, onToggleRoute, onRemoveRoute, onNotify }: { cloud: CloudState; onOpenProject: (id: string) => void; onAddDomain: (projectId: string, hostname: string) => void; onAddRoute: (route: Omit<NetworkRoute, 'id' | 'status'>) => void; onToggleRoute: (id: string) => void; onRemoveRoute: (id: string) => void; onNotify: (message: string) => void }) {
  const [tab, setTab] = useState<'domains' | 'routes'>('domains')
  const [domainProject, setDomainProject] = useState(cloud.projects[0]?.id ?? '')
  const [domain, setDomain] = useState('')
  const [routeType, setRouteType] = useState<NetworkRoute['type']>('redirect')
  const [routeSource, setRouteSource] = useState('')
  const [routeTarget, setRouteTarget] = useState('')
  const [routeProject, setRouteProject] = useState<string | undefined>(cloud.projects[0]?.id)
  const allDomains = cloud.projects.flatMap((project) => project.domains.map((domain) => ({ ...domain, project })))
  const addDomainFromNetwork = () => { if (!domainProject || !domain.trim()) return; onAddDomain(domainProject, domain); setDomain(''); onNotify('Domain added as pending. Complete DNS verification to activate it.') }
  const addRoute = () => { if (!routeSource.trim() || !routeTarget.trim()) { onNotify('Add both a source pattern and target first.'); return } onAddRoute({ type: routeType, source: routeSource, target: routeTarget, projectId: routeProject }); setRouteSource(''); setRouteTarget(''); onNotify('Route saved as a draft. Activate it when ready.') }
  return <div className="page-content network-page">
    <section className="page-title-row"><div><p className="eyebrow">Edge</p><h1>Network</h1><p className="page-intro">Centralize domains, certificates, redirects, rewrites, and cache-ready route rules.</p></div><span className="edge-status"><i />Edge network operational</span></section>
    <section className="network-overview"><div><span className="network-orb"><Icon name="globe" size={23} /></span><div><p className="eyebrow">Global delivery</p><h2>HTTPS on every active domain</h2><span>Certificate issuance, DNS ownership, and edge routes become production APIs in the next backend phase.</span></div></div><div className="network-metrics"><span><strong>{allDomains.length}</strong><small>hostnames</small></span><span><strong>{allDomains.filter((domain) => domain.ssl).length}</strong><small>TLS active</small></span><span><strong>{cloud.routes.filter((route) => route.status === 'active').length}</strong><small>edge rules</small></span></div></section>
    <div className="ops-tabs resource-tabs"><button className={tab === 'domains' ? 'active' : ''} onClick={() => setTab('domains')}><Icon name="globe" size={15} />Domains</button><button className={tab === 'routes' ? 'active' : ''} onClick={() => setTab('routes')}><Icon name="layers" size={15} />Route rules <span>{cloud.routes.length}</span></button></div>
    {tab === 'domains' && <section className="network-card"><div className="network-card-heading"><div><p className="eyebrow">Domain manager</p><h2>Map a hostname</h2><span>A new custom hostname starts as pending until DNS points to the edge.</span></div></div><div className="network-form"><select value={domainProject} onChange={(event) => setDomainProject(event.target.value)} aria-label="Service for domain">{cloud.projects.map((project) => <option key={project.id} value={project.id}>{project.name}</option>)}</select><div className="input-with-icon"><Icon name="globe" size={16} /><input value={domain} onChange={(event) => setDomain(event.target.value)} placeholder="app.example.com" /></div><button className="primary-button small" onClick={addDomainFromNetwork}>Add domain</button></div><div className="network-domain-list">{allDomains.map(({ project, ...domainItem }) => <div className="network-domain-row" key={domainItem.id}><span className="domain-icon"><Icon name="globe" size={16} /></span><span><strong>{domainItem.hostname}</strong><small>{project.name} · {domainItem.type === 'platform' ? 'Platform domain' : domainItem.ssl ? 'TLS certificate active' : 'Awaiting DNS verification'}</small></span><span className={`domain-status ${domainItem.status}`}>{domainItem.status === 'active' ? <><Icon name="check" size={13} />TLS active</> : <><Icon name="clock" size={13} />Pending</>}</span><button className="text-button" onClick={() => onOpenProject(project.id)}>Service <Icon name="arrowUpRight" size={13} /></button></div>)}</div></section>}
    {tab === 'routes' && <section className="network-card"><div className="network-card-heading"><div><p className="eyebrow">Edge routing</p><h2>Redirect, rewrite, and header rules</h2><span>Use exact route patterns and deploy drafts explicitly in a production backend.</span></div></div><div className="route-builder"><select value={routeType} onChange={(event) => setRouteType(event.target.value as NetworkRoute['type'])}><option value="redirect">Redirect</option><option value="rewrite">Rewrite</option><option value="header">Header</option></select><input value={routeSource} onChange={(event) => setRouteSource(event.target.value)} placeholder="Source, e.g. /legacy/*" /><input value={routeTarget} onChange={(event) => setRouteTarget(event.target.value)} placeholder={routeType === 'header' ? 'Header value' : 'Target URL or path'} /><select value={routeProject ?? ''} onChange={(event) => setRouteProject(event.target.value || undefined)}><option value="">Workspace-level</option>{cloud.projects.map((project) => <option key={project.id} value={project.id}>{project.name}</option>)}</select><button className="soft-button small" onClick={addRoute}><Icon name="plus" size={14} />Create rule</button></div><div className="route-list">{cloud.routes.map((route) => { const project = cloud.projects.find((item) => item.id === route.projectId); return <div className="route-row" key={route.id}><span className={`route-type ${route.type}`}>{route.type}</span><code>{route.source}</code><Icon name="arrowUpRight" size={14} /><code>{route.target}</code><span className="route-project">{project?.name ?? 'Workspace'}</span><StatusPill status={route.status} /><button className="soft-button small" onClick={() => onToggleRoute(route.id)}>{route.status === 'active' ? 'Deactivate' : 'Activate'}</button><button className="icon-button subtle" onClick={() => onRemoveRoute(route.id)} aria-label={`Delete ${route.source}`}><Icon name="trash" size={15} /></button></div>})}</div></section>}
  </div>
}

const templateCards: Array<{ name: string; description: string; framework: string; runtime: string; category: string; features: string[]; plan: string }> = [
  { name: 'Next.js commerce', description: 'Edge-ready storefront with preview deployment defaults.', framework: 'Next.js', runtime: 'Node.js 22', category: 'Frontend', features: ['Preview URLs', 'Edge cache', 'Image optimization'], plan: 'Pro' },
  { name: 'FastAPI service', description: 'Typed Python API with health checks and a PostgreSQL-ready shape.', framework: 'FastAPI', runtime: 'Python 3.12', category: 'API', features: ['Health checks', 'OpenAPI', 'Worker-ready'], plan: 'Pro' },
  { name: 'Django app', description: 'Full-stack Python application with static asset and migration guidance.', framework: 'Django', runtime: 'Python 3.12', category: 'Full stack', features: ['Admin', 'Migrations', 'PostgreSQL-ready'], plan: 'Pro' },
  { name: 'Queue worker', description: 'Long-running worker pattern with retries, queues, and observability.', framework: 'Node API', runtime: 'Node.js 22', category: 'Workers', features: ['Retries', 'Cron jobs', 'Log stream'], plan: 'Starter' },
  { name: 'Docker service', description: 'Bring a portable container with an explicit runtime contract.', framework: 'Docker', runtime: 'Docker', category: 'Container', features: ['Dockerfile', 'Health probes', 'Volumes'], plan: 'Scale' },
]

function TemplatesPage({ onUseTemplate }: { onUseTemplate: (draft: Partial<CreateServiceInput>) => void }) {
  const [category, setCategory] = useState('All')
  const categories = ['All', ...new Set(templateCards.map((template) => template.category))]
  const shown = templateCards.filter((template) => category === 'All' || template.category === category)
  return <div className="page-content templates-page">
    <section className="page-title-row"><div><p className="eyebrow">Accelerate</p><h1>Service templates</h1><p className="page-intro">Start with production-shaped runtime defaults, then connect your own repository.</p></div><span className="template-note"><Icon name="sparkles" size={15} />Original starter blueprints</span></section>
    <div className="template-hero"><div><span className="template-hero-icon"><Icon name="layers" size={22} /></span><h2>Go from empty repo to deployment plan in minutes.</h2><p>Templates fill in safe runtime and plan defaults. You still review the repository, configuration, variables, and release strategy.</p><button className="soft-button" onClick={() => onUseTemplate({ name: '', repository: '', description: '', branch: 'main', framework: 'Next.js', runtime: 'Node.js 22', region: 'Mumbai, India', plan: 'Starter', env: [] })}>Start blank <Icon name="arrowUpRight" size={15} /></button></div><div className="template-steps"><span><i>1</i>Choose a foundation</span><span><i>2</i>Connect your source</span><span><i>3</i>Review and deploy</span></div></div>
    <div className="template-filters">{categories.map((item) => <button key={item} className={category === item ? 'selected' : ''} onClick={() => setCategory(item)}>{item}</button>)}</div>
    <section className="template-grid">{shown.map((template) => <article className="template-card" key={template.name}><div className="template-card-head"><span className="template-card-icon"><Icon name={template.framework === 'FastAPI' || template.framework === 'Django' ? 'terminal' : template.framework === 'Docker' ? 'box' : 'layers'} size={19} /></span><span>{template.category}</span></div><h2>{template.name}</h2><p>{template.description}</p><div className="template-tags">{template.features.map((feature) => <span key={feature}>{feature}</span>)}</div><footer><span>{template.runtime} · {template.plan}</span><button className="soft-button small" onClick={() => onUseTemplate({ name: '', repository: '', description: template.description, branch: 'main', framework: template.framework, runtime: template.runtime, region: 'Mumbai, India', plan: template.plan, env: [] })}>Use template <Icon name="arrowUpRight" size={14} /></button></footer></article>)}</section>
  </div>
}

function ObservabilityPage({ cloud, onOpenProject }: { cloud: CloudState; onOpenProject: (id: string) => void }) {
  const highTraffic = cloud.projects.slice().sort((a, b) => parseFloat(b.requests.replace(/[^0-9.]/g, '')) - parseFloat(a.requests.replace(/[^0-9.]/g, '')))
  return <div className="page-content">
    <section className="page-title-row"><div><p className="eyebrow">Operations</p><h1>Observability</h1><p className="page-intro">A high-signal snapshot across your services and regions.</p></div><button className="soft-button"><Icon name="download" size={16} />Export report</button></section>
    <section className="metric-grid observability-metrics"><MetricCard icon="activity" label="Requests" value="3.07M" detail="Last 30 days" trend="↑ 12.4%" tone="violet" /><MetricCard icon="clock" label="P95 latency" value="84 ms" detail="Across all edge regions" trend="↓ 8 ms" tone="cyan" /><MetricCard icon="warning" label="Error rate" value="0.04%" detail="Well inside your 1% SLO" trend="Healthy" /><MetricCard icon="database" label="Data transfer" value="72.7 GB" detail="52% of included usage" trend="On track" tone="orange" /></section>
    <section className="charts-grid"><article className="chart-card traffic-chart"><div className="chart-card-header"><div><p className="eyebrow">Traffic</p><h2>Requests over time</h2></div><div className="chart-legend"><span><i className="violet" />Requests</span><button>30 days <Icon name="chevronDown" size={14} /></button></div></div><div className="chart-total"><strong>3,072,815</strong><span>↑ 12.4% vs. previous period</span></div><TrafficChart /></article>
      <article className="chart-card uptime-card"><div className="chart-card-header"><div><p className="eyebrow">Reliability</p><h2>Service health</h2></div><span className="uptime-score">99.99%</span></div><div className="uptime-days" aria-label="30 days of successful uptime">{Array.from({ length: 30 }, (_, index) => <span key={index} className={index === 12 ? 'soft' : ''} />)}</div><div className="uptime-footer"><span><i />All systems operational</span><span>Last incident: 41 days ago</span></div></article></section>
    <section className="chart-card service-health-card"><div className="section-heading"><div><p className="eyebrow">Service health</p><h2>Resource snapshot</h2></div><button className="text-button">View metrics <Icon name="arrowUpRight" size={15} /></button></div><div className="resource-list">{highTraffic.map((project) => <button key={project.id} className="resource-row" onClick={() => onOpenProject(project.id)}><ServiceGlyph project={project} size="small" /><span className="resource-name"><strong>{project.name}</strong><small>{project.region} · {project.replicas} {project.replicas === 1 ? 'replica' : 'replicas'}</small></span><span className="resource-meter"><small>CPU</small><ProgressBar value={project.cpu} tone="violet" /><strong>{project.cpu}%</strong></span><span className="resource-meter"><small>Memory</small><ProgressBar value={project.memory} tone="cyan" /><strong>{project.memory}%</strong></span><StatusPill status={project.status} /></button>)}</div></section>
  </div>
}

function TrafficChart() {
  return <div className="traffic-svg-wrap"><svg viewBox="0 0 720 215" preserveAspectRatio="none" role="img" aria-label="Request volume trend increasing over 30 days"><defs><linearGradient id="areaGradient" x1="0" x2="0" y1="0" y2="1"><stop offset="0%" stopColor="#8b5cf6" stopOpacity=".34" /><stop offset="100%" stopColor="#8b5cf6" stopOpacity="0" /></linearGradient></defs><g className="grid-lines"><line x1="0" x2="720" y1="34" y2="34" /><line x1="0" x2="720" y1="88" y2="88" /><line x1="0" x2="720" y1="142" y2="142" /><line x1="0" x2="720" y1="196" y2="196" /></g><path d="M0 184 C24 174 32 179 49 161 S80 151 98 155 S123 135 144 145 S170 125 190 132 S216 112 235 126 S258 136 279 112 S315 118 333 101 S366 105 385 89 S416 106 436 85 S465 94 484 73 S515 80 538 65 S565 75 588 48 S622 55 644 35 S682 51 720 22 V215 H0Z" fill="url(#areaGradient)" /><path d="M0 184 C24 174 32 179 49 161 S80 151 98 155 S123 135 144 145 S170 125 190 132 S216 112 235 126 S258 136 279 112 S315 118 333 101 S366 105 385 89 S416 106 436 85 S465 94 484 73 S515 80 538 65 S565 75 588 48 S622 55 644 35 S682 51 720 22" fill="none" stroke="#9b7cff" strokeWidth="3" vectorEffect="non-scaling-stroke" /></svg><div className="chart-axis"><span>Aug 1</span><span>Aug 8</span><span>Aug 15</span><span>Aug 22</span><span>Aug 30</span></div></div>
}

function TeamPage({ cloud, onInvite, onCreateToken, onRevokeToken, onUpdatePolicy, onUpdateBilling, onNotify }: { cloud: CloudState; onInvite: () => void; onCreateToken: () => void; onRevokeToken: (id: string) => void; onUpdatePolicy: (patch: Partial<CloudState['deploymentPolicy']>) => void; onUpdateBilling: (patch: Partial<CloudState['billing']>) => void; onNotify: (message: string) => void }) {
  const [tab, setTab] = useState<'members' | 'security' | 'billing'>('members')
  const { team, apiTokens, deploymentPolicy, billing } = cloud
  return <div className="page-content team-access-page">
    <section className="page-title-row"><div><p className="eyebrow">Workspace</p><h1>Team & access</h1><p className="page-intro">Collaborate with explicit roles, deployment protection, scoped API tokens, and clear usage boundaries.</p></div>{tab === 'members' ? <button className="primary-button" onClick={onInvite}><Icon name="plus" size={17} />Invite member</button> : tab === 'security' ? <button className="primary-button" onClick={onCreateToken}><Icon name="key" size={16} />Create API token</button> : <button className="soft-button" onClick={() => onNotify('Billing portal would open here when Stripe or your billing provider is connected.')}><Icon name="arrowUpRight" size={16} />Billing portal</button>}</section>
    <section className="team-hero"><div className="team-hero-copy"><span className="hero-icon"><Icon name="users" size={20} /></span><div><p>Northstar Labs</p><h2>{team.length} collaborators · Pro workspace</h2><span>Production changes are protected by clear, reviewable controls.</span></div></div><div className="avatar-stack">{team.slice(0, 4).map((member) => <Avatar key={member.id} member={member} />)}{team.length > 4 && <span className="avatar more">+{team.length - 4}</span>}</div></section>
    <div className="ops-tabs access-tabs"><button className={tab === 'members' ? 'active' : ''} onClick={() => setTab('members')}><Icon name="users" size={15} />Members <span>{team.length}</span></button><button className={tab === 'security' ? 'active' : ''} onClick={() => setTab('security')}><Icon name="lock" size={15} />Security & delivery</button><button className={tab === 'billing' ? 'active' : ''} onClick={() => setTab('billing')}><Icon name="chart" size={15} />Billing & usage</button></div>
    {tab === 'members' && <><section className="team-table-card"><div className="team-table-heading"><div><h2>Members</h2><span>Manage workspace access and deployment roles.</span></div><button className="soft-button" onClick={() => onNotify('Role templates can be connected to your production identity provider.')}><Icon name="sliders" size={16} />Role templates</button></div><div className="team-table-head"><span>Member</span><span>Role</span><span>Last active</span><span /></div>{team.map((member) => <div className="team-table-row" key={member.id}><span className="member-cell"><Avatar member={member} /><span><strong>{member.name}</strong><small>{member.email}</small></span></span><span className={`role-badge ${member.role.toLowerCase()}`}>{member.role}</span><span className="last-active">{member.lastActive}</span><button className="icon-button subtle" onClick={() => onNotify(`${member.name}'s access is managed through this prototype.`)} aria-label={`Manage ${member.name}`}><Icon name="dots" size={18} /></button></div>)}</section><section className="access-grid"><article><span className="access-icon"><Icon name="lock" size={18} /></span><h3>Least-privilege roles</h3><p>Owner, Admin, Developer, and Viewer roles make permissions clear at a glance.</p></article><article><span className="access-icon"><Icon name="activity" size={18} /></span><h3>Deployment audit trail</h3><p>Every local control-plane change appears in the workspace activity feed.</p></article><article><span className="access-icon"><Icon name="key" size={18} /></span><h3>Secret-safe by default</h3><p>Secret values are masked in the UI and excluded from workspace exports.</p></article></section></>}
    {tab === 'security' && <div className="security-layout"><section className="security-card"><div className="security-card-heading"><span className="access-icon"><Icon name="rocket" size={18} /></span><div><p className="eyebrow">Production policy</p><h2>Protected delivery</h2><span>Set the default release strategy and require a human approval before promotion.</span></div></div><div className="policy-row"><span><strong>Require production approval</strong><small>Pause completed releases before they can receive traffic.</small></span><Toggle checked={deploymentPolicy.requireProductionApproval} onChange={(checked) => onUpdatePolicy({ requireProductionApproval: checked })} /></div><div className="policy-row"><span><strong>Create preview deployments</strong><small>Allow safe, temporary preview URLs for branch changes.</small></span><Toggle checked={deploymentPolicy.previewBranches} onChange={(checked) => onUpdatePolicy({ previewBranches: checked })} /></div><div className="strategy-row"><span><strong>Default production strategy</strong><small>Choose whether a release starts with limited traffic.</small></span><div className="strategy-picker">{(['canary', 'direct'] as DeploymentStrategy[]).map((strategy) => <button key={strategy} className={deploymentPolicy.defaultStrategy === strategy ? 'selected' : ''} onClick={() => onUpdatePolicy({ defaultStrategy: strategy })}>{strategy === 'canary' ? 'Canary · 10%' : 'Direct · 100%'}</button>)}</div></div><label className="policy-branch"><span>Protected branch</span><input value={deploymentPolicy.protectedBranch} onChange={(event) => onUpdatePolicy({ protectedBranch: event.target.value })} /></label></section><section className="api-token-card"><div className="security-card-heading"><span className="access-icon"><Icon name="key" size={18} /></span><div><p className="eyebrow">Developer access</p><h2>Scoped API tokens</h2><span>Create least-privilege tokens for CI/CD and monitoring integrations.</span></div></div><div className="token-list">{apiTokens.map((token) => <div className={`token-row ${token.revoked ? 'revoked' : ''}`} key={token.id}><span className="token-prefix"><Icon name="key" size={15} /><code>{token.prefix}••••</code></span><span><strong>{token.name}</strong><small>{token.scopes.join(' · ')} · Last used {token.lastUsed}</small></span>{token.revoked ? <span className="token-revoked">Revoked</span> : <button className="danger-button small" onClick={() => onRevokeToken(token.id)}>Revoke</button>}</div>)}</div><button className="soft-button" onClick={onCreateToken}><Icon name="plus" size={15} />Create scoped token</button></section></div>}
    {tab === 'billing' && <div className="billing-layout"><section className="billing-hero"><div><p className="eyebrow">Current estimate</p><strong>${billing.monthlyEstimate.toFixed(2)}</strong><span>this billing period</span><small>Includes usage through today; no real charge is made by this prototype.</small></div><div className="billing-plan"><span>Current plan</span><strong>{billing.plan}</strong><button onClick={() => onNotify('Plan changes should be validated by a production billing provider.')}>Manage plan <Icon name="arrowUpRight" size={13} /></button></div></section><section className="usage-card"><div className="usage-card-heading"><div><p className="eyebrow">Usage</p><h2>Included resources</h2></div><span>Period ends in 12 days</span></div><div className="usage-progress"><div><span><strong>Compute hours</strong><small>{billing.usedHours} of {billing.includedHours} included</small></span><ProgressBar value={(billing.usedHours / billing.includedHours) * 100} tone="violet" /><strong>{Math.round((billing.usedHours / billing.includedHours) * 100)}%</strong></div><div><span><strong>Data transfer</strong><small>{billing.usedTransferGb.toFixed(1)} GB of {billing.includedTransferGb} GB included</small></span><ProgressBar value={(billing.usedTransferGb / billing.includedTransferGb) * 100} tone="cyan" /><strong>{Math.round((billing.usedTransferGb / billing.includedTransferGb) * 100)}%</strong></div></div></section><section className="billing-controls-card"><div><p className="eyebrow">Cost protection</p><h2>Monthly budget alert</h2><span>Send a notification when the estimated charge crosses this amount.</span></div><label><span>Alert threshold</span><div className="currency-field"><i>$</i><input type="number" min="1" value={billing.budgetAlert} onChange={(event) => onUpdateBilling({ budgetAlert: Math.max(1, Number(event.target.value) || 1) })} /></div></label></section><section className="plan-options">{(['Starter', 'Pro', 'Scale'] as const).map((plan) => <button key={plan} className={billing.plan === plan ? 'selected' : ''} onClick={() => onUpdateBilling({ plan, monthlyEstimate: plan === 'Starter' ? 0 : plan === 'Pro' ? 84.6 : 249 })}><strong>{plan}</strong><small>{plan === 'Starter' ? 'Experiment safely' : plan === 'Pro' ? 'For production teams' : 'For high-volume apps'}</small>{billing.plan === plan && <span><Icon name="check" size={13} />Current</span>}</button>)}</section></div>}
  </div>
}

function SettingsPage({ cloud, onChange, onExport, onReset }: { cloud: CloudState; onChange: (patch: Partial<CloudState['preferences']>) => void; onExport: () => void; onReset: () => void }) {
  return <div className="page-content settings-page">
    <section className="page-title-row"><div><p className="eyebrow">Workspace</p><h1>Settings</h1><p className="page-intro">These controls only change this browser’s local Northstar prototype.</p></div></section>
    <div className="settings-layout"><aside className="settings-nav"><strong>Workspace</strong><button className="active">General</button><button>Notifications</button><button>Security</button><button>Billing</button><strong>Developer</strong><button>API tokens</button><button>Integrations</button></aside><div className="settings-content"><section className="settings-card"><div><h2>Workspace appearance</h2><p>Choose how dense the dashboard feels on this device.</p></div><div className="setting-row"><span><strong>Compact density</strong><small>Show more services and activity in less vertical space.</small></span><Toggle checked={cloud.preferences.compactMode} onChange={(checked) => onChange({ compactMode: checked })} /></div></section><section className="settings-card"><div><h2>Notifications</h2><p>Control local in-app release notices.</p></div><div className="setting-row"><span><strong>Deployment notifications</strong><small>Show a confirmation when a local demo action completes.</small></span><Toggle checked={cloud.preferences.notifications} onChange={(checked) => onChange({ notifications: checked })} /></div></section><section className="settings-card"><div><h2>Export workspace</h2><p>Download your project configuration, activity, and team structure. Secret values are redacted.</p></div><button className="soft-button" onClick={onExport}><Icon name="download" size={16} />Download redacted export</button></section><section className="settings-card danger"><div><h2>Reset local demo</h2><p>Restore the sample services and remove all browser-only changes to this prototype.</p></div><button className="danger-button" onClick={onReset}><Icon name="trash" size={16} />Reset demo data</button></section></div></div>
  </div>
}

function Toggle({ checked, onChange }: { checked: boolean; onChange: (checked: boolean) => void }) {
  return <button className={`toggle ${checked ? 'on' : ''}`} onClick={() => onChange(!checked)} role="switch" aria-checked={checked}><span /></button>
}

function DeployWizard({ initialValues, onClose, onCreate }: { initialValues?: Partial<CreateServiceInput>; onClose: () => void; onCreate: (input: CreateServiceInput) => void }) {
  const [step, setStep] = useState(1)
  const [error, setError] = useState('')
  const [input, setInput] = useState<CreateServiceInput>(() => ({ name: '', description: '', repository: '', branch: 'main', framework: 'Next.js', runtime: 'Node.js 22', region: 'Mumbai, India', plan: 'Starter', ...initialValues, env: initialValues?.env ?? [] }))
  const [envName, setEnvName] = useState('')
  const [envValue, setEnvValue] = useState('')
  const [envSecret, setEnvSecret] = useState(true)

  const update = <K extends keyof CreateServiceInput>(key: K, value: CreateServiceInput[K]) => setInput((current) => ({ ...current, [key]: value }))
  const next = () => {
    if (step === 1 && !input.repository.trim()) { setError('Add a GitHub repository to continue.'); return }
    if (step === 2 && !input.name.trim()) { setError('Give this service a name to continue.'); return }
    setError('')
    setStep((current) => Math.min(4, current + 1))
  }
  const addEnv = () => {
    if (!envName.trim()) return
    update('env', [...input.env, { id: makeId('draft'), name: envName.trim().toUpperCase(), value: envValue, secret: envSecret, scope: 'production' }])
    setEnvName(''); setEnvValue(''); setEnvSecret(true)
  }
  const frameworkRuntime: Record<string, string> = { 'Next.js': 'Node.js 22', React: 'Node.js 22', FastAPI: 'Python 3.12', Django: 'Python 3.12', 'Node API': 'Node.js 22', Docker: 'Docker' }

  return <Modal title="Create a new service" subtitle="Connect a repository, choose a runtime, and deploy with confidence." onClose={onClose} className="wizard-modal">
    <div className="wizard-steps">{['Source', 'Configure', 'Variables', 'Review'].map((label, index) => <div key={label} className={step === index + 1 ? 'active' : step > index + 1 ? 'done' : ''}><span>{step > index + 1 ? <Icon name="check" size={13} /> : index + 1}</span><strong>{label}</strong></div>)}</div>
    <div className="wizard-body">
      {step === 1 && <section className="wizard-panel"><div className="wizard-heading"><span className="setup-icon"><Icon name="github" size={20} /></span><div><h2>Choose your source</h2><p>Start from a Git repository. Northstar will create an isolated build plan.</p></div></div><div className="source-options"><button className="source-option active"><span><Icon name="github" size={19} /></span><div><strong>GitHub repository</strong><small>Deploy from a GitHub repository</small></div><i><Icon name="check" size={15} /></i></button><button className="source-option" onClick={() => setError('GitLab and Docker image sources are planned for the production control plane.')}><span><Icon name="box" size={19} /></span><div><strong>Container image</strong><small>Bring an OCI-compatible image</small></div><i>Coming soon</i></button></div><label className="field-label">Repository <span>Required</span><div className="input-with-icon"><Icon name="github" size={16} /><input autoFocus value={input.repository} onChange={(event) => update('repository', event.target.value)} placeholder="acme/your-repository" /></div><small>Enter owner/repository. This prototype never contacts GitHub.</small></label></section>}
      {step === 2 && <section className="wizard-panel"><div className="wizard-heading"><span className="setup-icon"><Icon name="sliders" size={20} /></span><div><h2>Configure the service</h2><p>These are a safe deployment plan preview — no shell commands are executed.</p></div></div><div className="form-two-col"><label className="field-label">Service name <span>Required</span><input autoFocus value={input.name} onChange={(event) => update('name', event.target.value)} placeholder="e.g. customer-api" /></label><label className="field-label">Production branch<select value={input.branch} onChange={(event) => update('branch', event.target.value)}><option>main</option><option>production</option><option>develop</option></select></label><label className="field-label">Framework<select value={input.framework} onChange={(event) => { const framework = event.target.value; setInput((current) => ({ ...current, framework, runtime: frameworkRuntime[framework] })) }}><option>Next.js</option><option>React</option><option>FastAPI</option><option>Django</option><option>Node API</option><option>Docker</option></select></label><label className="field-label">Runtime<select value={input.runtime} onChange={(event) => update('runtime', event.target.value)}><option>Node.js 22</option><option>Python 3.12</option><option>Docker</option></select></label><label className="field-label full">Description <textarea value={input.description} onChange={(event) => update('description', event.target.value)} placeholder="What does this service do?" rows={3} /></label><label className="field-label full">Region<select value={input.region} onChange={(event) => update('region', event.target.value)}><option>Mumbai, India</option><option>Singapore</option><option>Frankfurt, Germany</option><option>Virginia, USA</option></select></label></div><div className="plan-picker"><span>Plan</span>{['Starter', 'Pro', 'Scale'].map((plan) => <button key={plan} className={input.plan === plan ? 'selected' : ''} onClick={() => update('plan', plan)}><strong>{plan}</strong><small>{plan === 'Starter' ? 'For prototypes' : plan === 'Pro' ? 'For production' : 'For high traffic'}</small></button>)}</div></section>}
      {step === 3 && <section className="wizard-panel"><div className="wizard-heading"><span className="setup-icon"><Icon name="key" size={20} /></span><div><h2>Environment variables</h2><p>They stay in this browser for the prototype. Production needs encrypted server-side storage.</p></div></div><div className="inline-env-form"><input value={envName} onChange={(event) => setEnvName(event.target.value)} placeholder="VARIABLE_NAME" aria-label="Variable name" /><input value={envValue} onChange={(event) => setEnvValue(event.target.value)} placeholder="Value" aria-label="Variable value" /><button className={`secret-toggle ${envSecret ? 'active' : ''}`} onClick={() => setEnvSecret((current) => !current)} title="Toggle secret"><Icon name={envSecret ? 'lock' : 'eye'} size={15} /></button><button className="soft-button small" onClick={addEnv}>Add</button></div>{input.env.length ? <div className="draft-env-list">{input.env.map((variable) => <div key={variable.id}><span><Icon name={variable.secret ? 'lock' : 'key'} size={15} />{variable.name}</span><code>{variable.secret ? maskValue(variable.value) : variable.value || 'Empty'}</code><button onClick={() => update('env', input.env.filter((item) => item.id !== variable.id))} aria-label={`Remove ${variable.name}`}><Icon name="x" size={15} /></button></div>)}</div> : <div className="compact-empty"><Icon name="key" size={18} /><span>No variables added. You can also add them after deployment.</span></div>}</section>}
      {step === 4 && <section className="wizard-panel review-panel"><div className="wizard-heading"><span className="setup-icon"><Icon name="rocket" size={20} /></span><div><h2>Ready to deploy</h2><p>Review the plan. Starting a demo deployment creates no cloud resources.</p></div></div><div className="review-service"><ServiceGlyph project={{ ...fallbackProject, name: input.name || 'Untitled service' }} /><div><strong>{input.name || 'Untitled service'}</strong><span>{input.repository} · {input.branch}</span></div><span className="review-ready"><Icon name="check" size={15} />Ready</span></div><div className="review-grid"><span><small>Framework</small><strong>{input.framework}</strong></span><span><small>Runtime</small><strong>{input.runtime}</strong></span><span><small>Region</small><strong>{input.region}</strong></span><span><small>Plan</small><strong>{input.plan}</strong></span><span><small>Variables</small><strong>{input.env.length} configured</strong></span><span><small>Build mode</small><strong>Isolated preview</strong></span></div><div className="safe-note"><Icon name="lock" size={16} /><span><strong>Safe by design.</strong> This standalone prototype models a deployment control plane but does not clone repositories, run builds, or expose secrets.</span></div></section>}
    </div>
    {error && <p className="form-error"><Icon name="warning" size={15} />{error}</p>}
    <footer className="wizard-footer"><button className="soft-button" onClick={step === 1 ? onClose : () => setStep((current) => current - 1)}>{step === 1 ? 'Cancel' : <><Icon name="arrowLeft" size={15} />Back</>}</button>{step < 4 ? <button className="primary-button" onClick={next}>Continue <Icon name="arrowUpRight" size={15} /></button> : <button className="primary-button" onClick={() => onCreate(input)}><Icon name="rocket" size={16} />Create & deploy</button>}</footer>
  </Modal>
}

function ProjectDrawer({ project, deployments, onClose, onDeploy, onSetStatus, onRollback, onAddEnvironment, onRemoveEnvironment, onAddDomain, onRemoveDomain, onViewDeployment, onNotify }: { project: Project; deployments: Deployment[]; onClose: () => void; onDeploy: () => void; onSetStatus: (status: ServiceStatus) => void; onRollback: () => void; onAddEnvironment: (variable: Omit<EnvironmentVariable, 'id'>) => void; onRemoveEnvironment: (id: string) => void; onAddDomain: (hostname: string) => void; onRemoveDomain: (id: string) => void; onViewDeployment: (id: string) => void; onNotify: (message: string) => void }) {
  const [tab, setTab] = useState<'overview' | 'deployments' | 'variables' | 'domains' | 'settings'>('overview')
  const [envName, setEnvName] = useState('')
  const [envValue, setEnvValue] = useState('')
  const [envSecret, setEnvSecret] = useState(true)
  const [envScope, setEnvScope] = useState<EnvironmentVariable['scope']>('production')
  const [domain, setDomain] = useState('')
  const [showSecrets, setShowSecrets] = useState(false)
  const currentDeployment = deployments.find((deployment) => deployment.id === project.lastDeploymentId) ?? deployments[0]

  const addEnv = () => {
    if (!envName.trim()) return
    onAddEnvironment({ name: envName, value: envValue, secret: envSecret, scope: envScope })
    setEnvName(''); setEnvValue(''); setEnvSecret(true)
  }
  const copyUrl = () => {
    navigator.clipboard?.writeText(project.url).catch(() => undefined)
    onNotify('Service URL copied to clipboard.')
  }
  return <div className="drawer-layer" role="presentation"><button className="drawer-scrim" aria-label="Close service panel" onClick={onClose} /><aside className="project-drawer" role="dialog" aria-modal="true" aria-label={`${project.name} settings`}>
    <header className="drawer-header"><div className="drawer-title"><ServiceGlyph project={project} /><div><div className="drawer-title-line"><h2>{project.name}</h2><StatusPill status={project.status} /></div><span>{project.repository} · {project.branch}</span></div></div><button className="icon-button subtle" onClick={onClose} aria-label="Close service panel"><Icon name="x" /></button></header>
    <div className="drawer-actions"><button className="primary-button" onClick={onDeploy}><Icon name="rocket" size={16} />Deploy</button><button className="soft-button" onClick={copyUrl}><Icon name="copy" size={15} />Copy URL</button><button className="icon-button subtle" onClick={() => onNotify('Service menu opened.')} aria-label="Service actions"><Icon name="dots" size={18} /></button></div>
    <nav className="drawer-tabs" aria-label="Service sections">{(['overview', 'deployments', 'variables', 'domains', 'settings'] as const).map((item) => <button key={item} className={tab === item ? 'active' : ''} onClick={() => setTab(item)}>{item === 'variables' ? 'Environment' : item[0].toUpperCase() + item.slice(1)}</button>)}</nav>
    <div className="drawer-content">
      {tab === 'overview' && <><section className="drawer-url-card"><span><Icon name="globe" size={16} />Production URL</span><button onClick={copyUrl}>{project.url}<Icon name="copy" size={14} /></button></section><section className="drawer-stat-grid"><span><small>Health</small><strong>{project.health}%</strong><i className="positive">Operational</i></span><span><small>Requests</small><strong>{project.requests}</strong><i>Last 30 days</i></span><span><small>Latency</small><strong>{project.latency}</strong><i>P95 global</i></span><span><small>Data transfer</small><strong>{project.bandwidth}</strong><i>Last 30 days</i></span></section><section className="drawer-section"><div className="drawer-section-heading"><div><p className="eyebrow">Latest release</p><h3>Production deployment</h3></div>{currentDeployment && <StatusPill status={currentDeployment.status} />}</div>{currentDeployment ? <button className="mini-deployment-card" onClick={() => onViewDeployment(currentDeployment.id)}><span className="commit-dot"><Icon name="rocket" size={15} /></span><span><strong><code>{shortCommit(currentDeployment.commit)}</code> {currentDeployment.message}</strong><small>{currentDeployment.author} · {relativeTime(currentDeployment.createdAt)} · {currentDeployment.duration}</small></span><Icon name="arrowUpRight" size={16} /></button> : <EmptyState icon="rocket" title="No deployment yet" description="Deploy this service when you are ready." />}</section><section className="drawer-section"><div className="drawer-section-heading"><div><p className="eyebrow">Runtime</p><h3>Service configuration</h3></div></div><div className="runtime-list"><span><Icon name="terminal" size={16} /><div><small>Runtime</small><strong>{project.runtime}</strong></div></span><span><Icon name="globe" size={16} /><div><small>Region</small><strong>{project.region}</strong></div></span><span><Icon name="layers" size={16} /><div><small>Scaling</small><strong>{project.replicas} {project.replicas === 1 ? 'replica' : 'replicas'} · {project.plan}</strong></div></span></div></section></>}
      {tab === 'deployments' && <section className="drawer-section drawer-deployments"><div className="drawer-section-heading"><div><p className="eyebrow">Release history</p><h3>{deployments.length} deployments</h3></div><button className="soft-button small" onClick={onDeploy}><Icon name="rocket" size={14} />Deploy</button></div>{deployments.length ? deployments.map((deployment) => <button key={deployment.id} className="drawer-deployment-row" onClick={() => onViewDeployment(deployment.id)}><span className="commit-dot"><Icon name={deployment.status === 'live' ? 'check' : 'rocket'} size={14} /></span><span><strong><code>{shortCommit(deployment.commit)}</code> {deployment.message}</strong><small>{deployment.branch} · {deployment.author} · {relativeTime(deployment.createdAt)}</small><ProgressBar value={deployment.progress} tone={deployment.status === 'live' ? 'green' : 'violet'} /></span><span><StatusPill status={deployment.status} /><small>{deployment.duration}</small></span></button>) : <EmptyState icon="rocket" title="No releases yet" description="Your release history will appear here." />}</section>}
      {tab === 'variables' && <section className="drawer-section"><div className="drawer-section-heading"><div><p className="eyebrow">Environment</p><h3>Variables</h3><span>Secret values are masked in this prototype.</span></div><button className="icon-button subtle" onClick={() => setShowSecrets((current) => !current)} aria-label="Toggle secret visibility"><Icon name={showSecrets ? 'eyeOff' : 'eye'} size={17} /></button></div><div className="drawer-env-form"><input value={envName} onChange={(event) => setEnvName(event.target.value)} placeholder="VARIABLE_NAME" /><input value={envValue} onChange={(event) => setEnvValue(event.target.value)} placeholder="Value" /><select value={envScope} onChange={(event) => setEnvScope(event.target.value as EnvironmentVariable['scope'])}><option value="production">Production</option><option value="preview">Preview</option><option value="development">Development</option></select><button className={`secret-toggle ${envSecret ? 'active' : ''}`} onClick={() => setEnvSecret((current) => !current)} title="Toggle secret"><Icon name={envSecret ? 'lock' : 'eye'} size={15} /></button><button className="primary-button small" onClick={addEnv}>Add</button></div><div className="variable-list">{project.environment.length ? project.environment.map((variable) => <div className="variable-row" key={variable.id}><span className="variable-name"><Icon name={variable.secret ? 'lock' : 'key'} size={15} /><strong>{variable.name}</strong></span><code>{variable.secret && !showSecrets ? maskValue(variable.value) : variable.value || 'Empty'}</code><span className="scope-badge">{variable.scope}</span><button onClick={() => onRemoveEnvironment(variable.id)} aria-label={`Remove ${variable.name}`}><Icon name="trash" size={15} /></button></div>) : <EmptyState icon="key" title="No variables configured" description="Add a variable above to create a safe local configuration." />}</div></section>}
      {tab === 'domains' && <section className="drawer-section"><div className="drawer-section-heading"><div><p className="eyebrow">Networking</p><h3>Domains</h3><span>Add a custom hostname and verify DNS before it becomes live.</span></div></div><div className="domain-form"><div className="input-with-icon"><Icon name="globe" size={16} /><input value={domain} onChange={(event) => setDomain(event.target.value)} placeholder="app.example.com" /></div><button className="primary-button small" onClick={() => { onAddDomain(domain); setDomain('') }}>Add domain</button></div><div className="domain-list">{project.domains.map((item) => <DomainRow key={item.id} domain={item} removable={item.type === 'custom'} onRemove={() => onRemoveDomain(item.id)} />)}</div><div className="dns-note"><Icon name="info" size={0} /><span><strong>DNS verification</strong> — Custom domains appear as pending until you point a CNAME record to <code>edge.northstar.app</code>.</span></div></section>}
      {tab === 'settings' && <section className="drawer-section"><div className="drawer-section-heading"><div><p className="eyebrow">Service controls</p><h3>Runtime settings</h3><span>These actions update local prototype state only.</span></div></div><div className="settings-action-row"><span><span className="setting-action-icon"><Icon name="server" size={17} /></span><div><strong>Service state</strong><small>{project.status === 'stopped' ? 'This service is not accepting traffic.' : 'Manage traffic availability for this service.'}</small></div></span><div>{project.status === 'stopped' ? <button className="soft-button small" onClick={() => onSetStatus('live')}><Icon name="rocket" size={14} />Start service</button> : <button className="soft-button small" onClick={() => onSetStatus('stopped')}><Icon name="stop" size={14} />Stop service</button>}</div></div><div className="settings-action-row"><span><span className="setting-action-icon"><Icon name="layers" size={17} /></span><div><strong>Instance count</strong><small>{project.replicas} active {project.replicas === 1 ? 'replica' : 'replicas'} on the {project.plan} plan.</small></div></span><button className="soft-button small" onClick={() => onNotify('Autoscaling would be configured through your production scheduler.')}>Configure</button></div><div className="danger-zone"><div><strong>Rollback release</strong><span>Promote the previous known-good production deployment.</span></div><button className="danger-button small" onClick={onRollback}><Icon name="refresh" size={14} />Roll back</button></div></section>}
    </div>
  </aside></div>
}

function DomainRow({ domain, removable, onRemove }: { domain: Domain; removable: boolean; onRemove: () => void }) {
  return <div className="domain-row"><span className="domain-icon"><Icon name="globe" size={16} /></span><span><strong>{domain.hostname}</strong><small>{domain.type === 'platform' ? 'Platform domain' : domain.ssl ? 'SSL certificate active' : 'Waiting for DNS verification'}</small></span><span className={`domain-status ${domain.status}`}>{domain.status === 'active' ? <><Icon name="check" size={13} />Active</> : <><Icon name="clock" size={13} />Pending</>}</span>{removable ? <button onClick={onRemove} aria-label={`Remove ${domain.hostname}`}><Icon name="trash" size={15} /></button> : <span className="domain-lock"><Icon name="lock" size={14} /></span>}</div>
}

function DeploymentModal({ deployment, project, onClose, onOpenProject, onApprove, onSetCanary }: { deployment: Deployment; project?: Project; onClose: () => void; onOpenProject: () => void; onApprove: () => void; onSetCanary: (percent: number) => void }) {
  const isPreview = deployment.environment === 'preview'
  const needsApproval = deployment.approvalState === 'pending' && deployment.status === 'deploying'
  const isCanary = deployment.strategy === 'canary' && !isPreview
  const canary = deployment.canaryPercent ?? (isCanary ? 10 : 100)
  return <Modal title="Deployment details" subtitle={`${project?.name ?? 'Service'} · ${deployment.branch}`} onClose={onClose} className="deployment-modal"><div className="deployment-modal-header"><div className="deploy-modal-ident"><ServiceGlyph project={project ?? fallbackProject} /><div><div><code>{shortCommit(deployment.commit)}</code><span className={`environment-badge ${isPreview ? 'preview' : 'production'}`}>{isPreview ? 'Preview' : 'Production'}</span><StatusPill status={deployment.status} /></div><h2>{deployment.message}</h2><span>{deployment.author} started this deployment {relativeTime(deployment.createdAt)}</span></div></div><button className="text-button" onClick={onOpenProject}>Open service <Icon name="arrowUpRight" size={15} /></button></div>{isPreview && deployment.previewUrl && <div className="preview-url-card"><span><Icon name="layers" size={15} />Preview URL</span><button onClick={() => navigator.clipboard?.writeText(deployment.previewUrl!).catch(() => undefined)}>{deployment.previewUrl}<Icon name="copy" size={14} /></button></div>}{needsApproval && <div className="approval-gate"><span><Icon name="lock" size={17} /></span><div><strong>Production approval required</strong><p>Build and health checks passed. Approve this release before it can receive production traffic.</p></div><button className="primary-button small" onClick={onApprove}><Icon name="check" size={14} />Approve promotion</button></div>}<div className="modal-progress"><div><span>{needsApproval ? 'Awaiting approval' : statusLabel(deployment.status)}</span><strong>{deployment.progress}%</strong></div><ProgressBar value={deployment.progress} tone={deployment.status === 'live' ? 'green' : deployment.status === 'failed' ? 'orange' : 'violet'} /></div>{isCanary && <section className="canary-control"><div><p className="eyebrow">Canary rollout</p><h3>{canary}% of production traffic</h3><span>Increase only after the release is healthy. A real backend would use weighted routing and error-budget checks.</span></div><div className="canary-actions"><input type="range" min="0" max="100" step="5" value={canary} onChange={(event) => onSetCanary(Number(event.target.value))} aria-label="Canary traffic percentage" /><div>{[10, 25, 50, 100].map((percent) => <button key={percent} className={canary === percent ? 'selected' : ''} onClick={() => onSetCanary(percent)}>{percent}%</button>)}</div></div></section>}<section className="build-log"><div className="build-log-top"><span><i />Build output</span><button onClick={() => navigator.clipboard?.writeText(deployment.logs.join('\n')).catch(() => undefined)}><Icon name="copy" size={14} />Copy</button></div><pre>{deployment.logs.map((log, index) => <code key={`${log}-${index}`}><span>{String(index + 1).padStart(2, '0')}</span>{log}</code>)}</pre></section><div className="deploy-milestones"><span className="done"><i><Icon name="check" size={12} /></i>Queued</span><span className={deployment.progress >= 34 ? 'done' : ''}><i>{deployment.progress >= 34 && <Icon name="check" size={12} />}</i>Build</span><span className={deployment.progress >= 74 ? 'done' : ''}><i>{deployment.progress >= 74 && <Icon name="check" size={12} />}</i>{isPreview ? 'Preview' : 'Release'}</span><span className={deployment.status === 'live' ? 'done' : ''}><i>{deployment.status === 'live' && <Icon name="check" size={12} />}</i>Live</span></div></Modal>
}

function CommandPalette({ projects, onClose, onNavigate, onNewService, onOpenProject }: { projects: Project[]; onClose: () => void; onNavigate: (page: Page) => void; onNewService: () => void; onOpenProject: (id: string) => void }) {
  const [query, setQuery] = useState('')
  const normalized = query.toLowerCase()
  const actions: { label: string; description: string; icon: IconName; shortcut?: string; run: () => void }[] = [
    { label: 'Create a new service', description: 'Start a deploy from a Git repository', icon: 'plus', shortcut: 'N', run: onNewService },
    { label: 'Go to projects', description: 'Browse all services', icon: 'box', run: () => { onNavigate('projects'); onClose() } },
    { label: 'Go to deployments', description: 'View build and release history', icon: 'rocket', run: () => { onNavigate('deployments'); onClose() } },
    { label: 'Open observability', description: 'Check requests and health', icon: 'chart', run: () => { onNavigate('observability'); onClose() } },
  ]
  const matches = actions.filter((action) => `${action.label} ${action.description}`.toLowerCase().includes(normalized))
  const projectsMatch = projects.filter((project) => `${project.name} ${project.repository}`.toLowerCase().includes(normalized)).slice(0, 5)
  return <div className="modal-layer command-layer" role="presentation"><button className="modal-scrim" aria-label="Close command palette" onClick={onClose} /><section className="command-palette" role="dialog" aria-modal="true" aria-label="Search and command palette"><div className="command-input"><Icon name="search" size={19} /><input autoFocus value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search services or run a command…" /><kbd>ESC</kbd></div><div className="command-results">{matches.length > 0 && <><p>Quick actions</p>{matches.map((action) => <button key={action.label} onClick={action.run}><span className="command-result-icon"><Icon name={action.icon} size={17} /></span><span><strong>{action.label}</strong><small>{action.description}</small></span>{action.shortcut && <kbd>{action.shortcut}</kbd>}</button>)}</>}{projectsMatch.length > 0 && <><p>Projects</p>{projectsMatch.map((project) => <button key={project.id} onClick={() => onOpenProject(project.id)}><ServiceGlyph project={project} size="small" /><span><strong>{project.name}</strong><small>{project.repository}</small></span><StatusPill status={project.status} /></button>)}</>}{!matches.length && !projectsMatch.length && <EmptyState icon="search" title="No matching results" description="Try a project name or an action such as “deployments”." />}</div><footer className="command-footer"><span><kbd>↵</kbd> to select</span><span><kbd>↑</kbd><kbd>↓</kbd> to navigate</span></footer></section></div>
}

function ResourceModal({ projects, onClose, onCreate }: { projects: Project[]; onClose: () => void; onCreate: (input: CreateResourceInput) => void }) {
  const [name, setName] = useState('')
  const [kind, setKind] = useState<ResourceKind>('PostgreSQL')
  const [region, setRegion] = useState('Mumbai, India')
  const [plan, setPlan] = useState('Starter')
  const [projectId, setProjectId] = useState(projects[0]?.id ?? '')
  const [error, setError] = useState('')
  const submit = (event: FormEvent) => {
    event.preventDefault()
    if (!name.trim()) { setError('Name this resource before provisioning it.'); return }
    onCreate({ name: name.trim(), kind, region, plan, projectId: projectId || undefined })
  }
  return <Modal title="Provision a resource" subtitle="Create a safe local resource plan; no databases or volumes are actually provisioned." onClose={onClose} className="resource-modal"><form className="resource-form" onSubmit={submit}><div className="resource-kind-picker">{(['PostgreSQL', 'Redis', 'Volume', 'Object storage'] as ResourceKind[]).map((item) => <button type="button" key={item} className={kind === item ? 'selected' : ''} onClick={() => setKind(item)}><Icon name={item === 'PostgreSQL' ? 'database' : item === 'Redis' ? 'layers' : 'server'} size={18} /><span><strong>{item}</strong><small>{item === 'PostgreSQL' ? 'Relational data' : item === 'Redis' ? 'Cache and queues' : item === 'Volume' ? 'Persistent files' : 'Blob assets'}</small></span></button>)}</div><div className="form-two-col"><label className="field-label">Resource name <span>Required</span><input autoFocus value={name} onChange={(event) => setName(event.target.value)} placeholder={kind === 'PostgreSQL' ? 'e.g. app-production-db' : 'e.g. uploads-volume'} /></label><label className="field-label">Attach to service<select value={projectId} onChange={(event) => setProjectId(event.target.value)}><option value="">No service yet</option>{projects.map((project) => <option value={project.id} key={project.id}>{project.name}</option>)}</select></label><label className="field-label">Region<select value={region} onChange={(event) => setRegion(event.target.value)}><option>Mumbai, India</option><option>Singapore</option><option>Frankfurt, Germany</option><option>Virginia, USA</option></select></label><label className="field-label">Plan<select value={plan} onChange={(event) => setPlan(event.target.value)}><option>Starter</option><option>Standard</option><option>Pro · HA</option></select></label></div>{error && <p className="form-error"><Icon name="warning" size={15} />{error}</p>}<div className="safe-note"><Icon name="lock" size={16} /><span><strong>Resource protection.</strong> The production implementation should generate credentials only in a server-side secrets vault and enforce backups, quotas, and access controls.</span></div><div className="modal-form-footer"><button type="button" className="soft-button" onClick={onClose}>Cancel</button><button className="primary-button" type="submit"><Icon name="database" size={16} />Provision resource</button></div></form></Modal>
}

function TokenModal({ onClose, onCreate }: { onClose: () => void; onCreate: (name: string, scopes: string[]) => void }) {
  const [name, setName] = useState('')
  const [scopes, setScopes] = useState<string[]>(['projects:read'])
  const [error, setError] = useState('')
  const options = ['projects:read', 'deploy:write', 'metrics:read', 'domains:write']
  const toggle = (scope: string) => setScopes((current) => current.includes(scope) ? current.filter((item) => item !== scope) : [...current, scope])
  const submit = (event: FormEvent) => { event.preventDefault(); if (!name.trim() || !scopes.length) { setError('Provide a name and select at least one scoped permission.'); return }; onCreate(name.trim(), scopes) }
  return <Modal title="Create API token" subtitle="Tokens are scoped. In production, the full value should be displayed exactly once and stored only as a hash." onClose={onClose} className="token-modal"><form className="token-form" onSubmit={submit}><label className="field-label">Token name <span>Required</span><input autoFocus value={name} onChange={(event) => setName(event.target.value)} placeholder="e.g. GitHub Actions production deploy" /></label><fieldset className="scope-fieldset"><legend>Permissions</legend><p>Grant only the permissions this integration actually needs.</p>{options.map((scope) => <label key={scope} className="scope-option"><input type="checkbox" checked={scopes.includes(scope)} onChange={() => toggle(scope)} /><span><strong>{scope}</strong><small>{scope === 'projects:read' ? 'Read project configuration' : scope === 'deploy:write' ? 'Request approved deployments' : scope === 'metrics:read' ? 'Read service health and metrics' : 'Manage custom domains'}</small></span><i>{scopes.includes(scope) && <Icon name="check" size={14} />}</i></label>)}</fieldset>{error && <p className="form-error"><Icon name="warning" size={15} />{error}</p>}<div className="modal-form-footer"><button type="button" className="soft-button" onClick={onClose}>Cancel</button><button className="primary-button" type="submit"><Icon name="key" size={16} />Create token</button></div></form></Modal>
}

function TokenRevealModal({ token, onClose }: { token: string; onClose: () => void }) {
  const [copied, setCopied] = useState(false)
  const copy = () => { navigator.clipboard?.writeText(token).catch(() => undefined); setCopied(true) }
  return <Modal title="Copy your API token" subtitle="This is the only time the full demo token is shown." onClose={onClose} className="token-reveal-modal"><div className="token-reveal"><span className="token-reveal-icon"><Icon name="key" size={20} /></span><h2>Save this token now</h2><p>It will be hidden after you close this dialog. Never put real tokens in client-side code or version control.</p><div className="full-token"><code>{token}</code><button onClick={copy}>{copied ? <><Icon name="check" size={15} />Copied</> : <><Icon name="copy" size={15} />Copy</>}</button></div></div><div className="modal-form-footer"><span className="token-warning"><Icon name="warning" size={14} />Treat tokens like passwords.</span><button className="primary-button" onClick={onClose}>I saved it</button></div></Modal>
}

function InviteModal({ onClose, onInvite }: { onClose: () => void; onInvite: (name: string, email: string, role: TeamMember['role']) => void }) {
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [role, setRole] = useState<TeamMember['role']>('Developer')
  const [error, setError] = useState('')
  const submit = (event: FormEvent) => { event.preventDefault(); if (!name.trim() || !email.includes('@')) { setError('Enter a name and valid email address.'); return } onInvite(name.trim(), email.trim(), role) }
  return <Modal title="Invite a team member" subtitle="Give a collaborator scoped workspace access." onClose={onClose} className="invite-modal"><form className="invite-form" onSubmit={submit}><label className="field-label">Full name<input autoFocus value={name} onChange={(event) => setName(event.target.value)} placeholder="e.g. Taylor Morgan" /></label><label className="field-label">Email address<input type="email" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="taylor@example.com" /></label><label className="field-label">Role<select value={role} onChange={(event) => setRole(event.target.value as TeamMember['role'])}><option>Developer</option><option>Viewer</option><option>Admin</option></select><small>Developers can deploy services. Viewers can inspect their health and history.</small></label>{error && <p className="form-error"><Icon name="warning" size={15} />{error}</p>}<div className="modal-form-footer"><button type="button" className="soft-button" onClick={onClose}>Cancel</button><button className="primary-button" type="submit"><Icon name="users" size={16} />Create invitation</button></div></form></Modal>
}

function Modal({ title, subtitle, onClose, className = '', children }: { title: string; subtitle?: string; onClose: () => void; className?: string; children: ReactNode }) {
  return <div className="modal-layer" role="presentation"><button className="modal-scrim" aria-label={`Close ${title}`} onClick={onClose} /><section className={`modal ${className}`} role="dialog" aria-modal="true" aria-label={title}><header className="modal-header"><div><h1>{title}</h1>{subtitle && <p>{subtitle}</p>}</div><button className="icon-button subtle" onClick={onClose} aria-label={`Close ${title}`}><Icon name="x" /></button></header>{children}</section></div>
}

export default App
