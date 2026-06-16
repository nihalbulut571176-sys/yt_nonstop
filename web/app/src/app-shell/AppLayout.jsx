import {NavLink, Outlet, useNavigate, useParams} from 'react-router-dom';
import {useEffect} from 'react';
import {Badge} from '../shared/ui/Badge.jsx';
import {MetricCard} from '../shared/ui/MetricCard.jsx';
import {useProjectStore, useRunsStore, useStudioShell, useWorkspaceStore} from '../state/StudioProvider.jsx';

function navForProject(projectId) {
  if (!projectId) {
    return [{to: '/projects', label: 'Projects'}, {to: '/settings', label: 'Settings'}];
  }
  return [
    {to: `/projects/${projectId}/overview`, label: 'Overview'},
    {to: `/projects/${projectId}/pipeline`, label: 'Pipeline'},
    {to: `/projects/${projectId}/review`, label: 'Review'},
    {to: `/projects/${projectId}/assets`, label: 'Assets'},
    {to: `/projects/${projectId}/runs`, label: 'Runs'},
    {to: '/projects/new', label: 'New Project'},
    {to: '/settings', label: 'Settings'}
  ];
}

export function AppLayout() {
  const navigate = useNavigate();
  const params = useParams();
  const {projects, workspace, selectedProjectId, setSelectedProjectId} = useWorkspaceStore();
  const {project, overview, pipelineState} = useProjectStore();
  const {activeRunDetails} = useRunsStore();
  const {signOut, error} = useStudioShell();

  const routeProjectId = params.projectId || selectedProjectId;

  useEffect(() => {
    if (params.projectId && params.projectId !== selectedProjectId) {
      setSelectedProjectId(params.projectId);
    }
  }, [params.projectId, selectedProjectId, setSelectedProjectId]);

  const openProject = (projectId, screen = 'overview') => {
    setSelectedProjectId(projectId);
    navigate(`/projects/${projectId}/${screen}`);
  };

  return (
    <div className="workspace-shell">
      <header className="topbar">
        <div className="brand-block">
          <p className="eyebrow">Local-First SaaS Studio</p>
          <h1>yt_nonstop</h1>
        </div>
        <div className="topbar-actions">
          <button className="ghost-button" onClick={() => navigate('/projects')}>Projects</button>
          <button className="ghost-button" onClick={() => navigate('/projects/new')}>New Project</button>
          <button className="ghost-button" onClick={() => navigate('/settings')}>Settings</button>
          <button className="ghost-button" onClick={signOut}>Sign out</button>
        </div>
      </header>

      <section className="workspace-overview">
        <MetricCard label="Projects" value={workspace?.total_projects ?? 0} />
        <MetricCard label="Active runs" value={workspace?.active_runs ?? 0} tone="accent" />
        <MetricCard label="Awaiting review" value={workspace?.awaiting_review_projects ?? 0} tone="warn" />
        <MetricCard label="Ready for render" value={workspace?.ready_for_render_projects ?? 0} tone="success" />
      </section>

      <div className="workspace-main">
        <aside className="project-rail">
          <div className="rail-panel">
            <div className="panel-head">
              <span>Projects</span>
              <span>{projects.length}</span>
            </div>
            <div className="project-list">
              {projects.map((item) => (
                <button key={item.id} className={`project-chip ${routeProjectId === item.id ? 'active' : ''}`} onClick={() => openProject(item.id)}>
                  <strong>{item.name}</strong>
                  <span>{`${item.current_stage || item.status} -> ${item.next_stage || 'n/a'}`}</span>
                </button>
              ))}
            </div>
          </div>
          <div className="rail-panel">
            <div className="panel-head">
              <span>Workspace</span>
            </div>
            <p className="muted mono-inline">{workspace?.workspace_root || 'No workspace loaded'}</p>
          </div>
        </aside>

        <div className="content-shell">
          <section className="project-header">
            <div className="project-header-main">
              <div>
                <p className="eyebrow">Current Project</p>
                <h2>{project?.name || 'Choose a project'}</h2>
                <p className="muted">{project?.path || 'Use Projects or New Project to get started.'}</p>
              </div>
              <div className="masthead-stats">
                <Badge tone={project?.support === 'full' ? 'success' : 'warn'}>{project?.support || 'idle'}</Badge>
                <Badge tone="neutral">{project?.kind || 'workspace'}</Badge>
                <Badge tone={overview?.lifecycle_status === 'blocked' ? 'warn' : 'accent'}>{overview?.lifecycle_status || 'unselected'}</Badge>
              </div>
            </div>
            <nav className="subnav">
              {navForProject(routeProjectId).map((item) => (
                <NavLink key={item.to} to={item.to} className={({isActive}) => `subnav-link ${isActive ? 'active' : ''}`}>
                  {item.label}
                </NavLink>
              ))}
            </nav>
            <div className="action-tray">
              <div className="action-tray-copy">
                <strong>{pipelineState?.next_command || 'No next command available yet'}</strong>
                <span>{pipelineState?.blocked_count ? `${pipelineState.blocked_count} blockers` : 'No blockers detected'}</span>
              </div>
              <div className="action-tray-meta">
                <span>{activeRunDetails?.status ? `Active run: ${activeRunDetails.status}` : 'No active run'}</span>
              </div>
            </div>
          </section>

          {error ? <div className="error-banner">{error}</div> : null}
          <Outlet />
        </div>
      </div>
    </div>
  );
}
