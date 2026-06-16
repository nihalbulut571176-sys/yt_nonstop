import {useNavigate} from 'react-router-dom';
import {Badge} from '../../shared/ui/Badge.jsx';
import {EmptyState} from '../../shared/ui/EmptyState.jsx';
import {MetricCard} from '../../shared/ui/MetricCard.jsx';
import {SectionTitle} from '../../shared/ui/SectionTitle.jsx';
import {useWorkspaceStore} from '../../state/StudioProvider.jsx';
import {formatTime} from '../../shared/types/contracts.js';

export function ProjectsPage() {
  const navigate = useNavigate();
  const {workspace, projects, setSelectedProjectId, refreshWorkspace} = useWorkspaceStore();

  if (!projects.length) {
    return <EmptyState title="No projects discovered yet" body="Create a new project or place an existing project folder under the configured workspace root." />;
  }

  return (
    <section className="stack wide-gap">
      <div className="panel">
        <SectionTitle title="Workspace Summary" meta={<button className="ghost-button" onClick={refreshWorkspace}>Refresh</button>} />
        <div className="metric-grid">
          <MetricCard label="Total projects" value={workspace?.total_projects ?? 0} />
          <MetricCard label="Full support" value={workspace?.full_support_projects ?? 0} tone="success" />
          <MetricCard label="Limited support" value={workspace?.limited_support_projects ?? 0} tone="warn" />
          <MetricCard label="Blocked" value={workspace?.blocked_projects ?? 0} tone="warn" />
        </div>
      </div>
      <div className="panel">
        <SectionTitle title="Projects" meta={`${projects.length} items`} />
        <div className="card-grid">
          {projects.map((item) => (
            <article key={item.id} className="project-card saas-card">
              <div className="stack compact">
                <h3>{item.name}</h3>
                <p>{item.path}</p>
                <div className="meta-row">
                  <Badge tone={item.support === 'full' ? 'success' : 'warn'}>{item.support}</Badge>
                  <Badge tone="neutral">{item.current_stage || item.status}</Badge>
                  <Badge tone="accent">{item.lifecycle_status || item.next_stage || 'pending'}</Badge>
                </div>
                <div className="meta-row">
                  <span className="stat-pill">blocked {item.blocked_count ?? 0}</span>
                  <span className="stat-pill">warnings {item.warning_count ?? 0}</span>
                  <span className="stat-pill">updated {formatTime(item.last_updated)}</span>
                </div>
              </div>
              <div className="action-row">
                <button onClick={() => { setSelectedProjectId(item.id); navigate(`/projects/${item.id}/overview`); }}>Open overview</button>
                <button className="ghost-button" onClick={() => { setSelectedProjectId(item.id); navigate(`/projects/${item.id}/pipeline`); }}>Open pipeline</button>
              </div>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}
