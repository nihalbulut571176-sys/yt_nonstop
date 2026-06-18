import {NavLink, Outlet, useLocation, useNavigate, useParams} from 'react-router-dom';
import {useEffect} from 'react';
import {Badge} from '../shared/ui/Badge.jsx';
import {PipelineStageRail} from '../shared/ui/PipelineStageRail.jsx';
import {useProjectStore, useRunsStore, useStudioShell, useWorkspaceStore} from '../state/StudioProvider.jsx';

function navForProject(projectId) {
  const baseItems = [
    {to: '/projects', label: 'Projects'},
    {to: '/projects/new', label: 'New Project'},
    {to: projectId ? `/projects/${projectId}/runs` : '/runs', label: 'Runs / History'},
    {to: '/settings', label: 'Settings'}
  ];
  if (!projectId) return baseItems;
  return [
    baseItems[0],
    baseItems[1],
    baseItems[2],
    {to: `/projects/${projectId}/assets`, label: 'Assets'},
    baseItems[3]
  ];
}

function projectTabs(projectId) {
  if (!projectId) return [];
  return [
    {to: `/projects/${projectId}/overview`, label: 'Overview'},
    {to: `/projects/${projectId}/pipeline`, label: 'Pipeline'},
    {to: `/projects/${projectId}/review`, label: 'Review'},
    {to: `/projects/${projectId}/assets`, label: 'Assets'},
    {to: `/projects/${projectId}/runs`, label: 'Runs'}
  ];
}

export function AppLayout() {
  const navigate = useNavigate();
  const location = useLocation();
  const params = useParams();
  const {projects, workspace, selectedProjectId, setSelectedProjectId} = useWorkspaceStore();
  const {project, overview, pipelineState} = useProjectStore();
  const {activeRunDetails} = useRunsStore();
  const {signOut, error} = useStudioShell();

  const routeProjectId = params.projectId || '';
  const isNewProjectRoute = location.pathname === '/projects/new';
  const isProjectsRoute = location.pathname === '/projects';
  const shellProject = routeProjectId ? project : null;
  const shellTitle = isNewProjectRoute ? 'New Project' : shellProject?.name || 'Projects';
  const shellDescription = isNewProjectRoute
    ? 'Upload audio and script, choose a range, then watch the pipeline launch.'
    : shellProject?.path || 'Manage local video production projects and runs.';

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
    <div className="studio-shell">
      <aside className="studio-sidebar">
        <div className="sidebar-brand">
          <div className="brand-mark">yt</div>
          <div>
            <strong>yt_nonstop</strong>
            <span>Studio</span>
          </div>
        </div>
        <p className="sidebar-copy">AI-powered video production pipeline</p>
        <nav className="sidebar-nav">
          {navForProject(routeProjectId || selectedProjectId).map((item) => (
            <NavLink end={item.to === '/projects'} key={item.to} to={item.to} className={({isActive}) => `sidebar-link ${isActive ? 'active' : ''}`}>
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-section">
          <span>Recent Projects</span>
          <div className="sidebar-projects">
            {projects.slice(0, 5).map((item) => (
              <button key={item.id} className={(routeProjectId || selectedProjectId) === item.id ? 'active' : ''} onClick={() => openProject(item.id)}>
                <strong>{item.name}</strong>
                <Badge tone={item.lifecycle_status === 'failed' ? 'warn' : item.lifecycle_status === 'running' ? 'success' : 'neutral'}>{item.lifecycle_status || item.status}</Badge>
              </button>
            ))}
          </div>
        </div>
        <div className="sidebar-footer">
          <div className="engine-card">
            <span className="engine-dot" />
            <div>
              <strong>Local engine</strong>
              <span>{workspace?.active_runs ? `${workspace.active_runs} active run(s)` : 'Online'}</span>
            </div>
          </div>
          <div className="workspace-path">{workspace?.workspace_root || 'Workspace not loaded'}</div>
          <button type="button" className="sidebar-signout" onClick={signOut}>Sign out</button>
        </div>
      </aside>

      <main className="studio-main">
        <header className="project-header">
          <div className="project-header-main">
            <div>
              <p className="breadcrumb">{isNewProjectRoute ? 'Projects / New Project' : shellProject ? `Projects / ${shellProject.name}` : 'Workspace / Projects'}</p>
              <h1>{shellTitle}</h1>
              <p className="muted">{shellDescription}</p>
            </div>
            <div className="masthead-stats">
              {shellProject ? <Badge tone={shellProject.support === 'full' ? 'success' : 'warn'}>{shellProject.support || 'idle'}</Badge> : null}
              {shellProject ? <Badge tone={overview?.lifecycle_status === 'failed' || overview?.lifecycle_status === 'blocked' ? 'warn' : overview?.lifecycle_status === 'running' ? 'success' : 'neutral'}>{overview?.lifecycle_status || 'unselected'}</Badge> : <Badge tone="neutral">{isProjectsRoute ? 'workspace' : 'intake'}</Badge>}
              <button type="button" className="ghost-button" onClick={() => navigate('/projects/new')}>New Project</button>
            </div>
          </div>
          {routeProjectId ? <PipelineStageRail pipelineState={pipelineState} compact /> : null}
          <nav className="subnav">
            {projectTabs(routeProjectId).map((item) => (
              <NavLink key={item.to} to={item.to} className={({isActive}) => `subnav-link ${isActive ? 'active' : ''}`}>
                {item.label}
              </NavLink>
            ))}
          </nav>
          {routeProjectId ? <div className="action-tray">
            <div className="action-tray-copy">
              <strong>{pipelineState?.progress?.current_stage_label || pipelineState?.next_command || 'No active project selected'}</strong>
              <span>{pipelineState?.blocked_count ? `${pipelineState.blocked_count} blockers` : activeRunDetails?.status ? `Run ${activeRunDetails.status}` : 'No blockers detected'}</span>
            </div>
            <div className="action-tray-meta">
              <span>{pipelineState?.progress?.percent ?? 0}%</span>
            </div>
          </div> : null}
        </header>

        {error ? <div className="error-banner">{error}</div> : null}
        <Outlet />
      </main>
    </div>
  );
}
