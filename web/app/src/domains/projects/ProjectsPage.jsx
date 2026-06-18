import {useNavigate} from 'react-router-dom';
import {EmptyState} from '../../shared/ui/EmptyState.jsx';
import {MetricCard} from '../../shared/ui/MetricCard.jsx';
import {SectionTitle} from '../../shared/ui/SectionTitle.jsx';
import {PageHeader} from '../../shared/ui/PageHeader.jsx';
import {useWorkspaceStore} from '../../state/StudioProvider.jsx';
import {ProjectTable} from '../../shared/ui/ProjectTable.jsx';

export function ProjectsPage() {
  const navigate = useNavigate();
  const {workspace, projects, setSelectedProjectId, refreshWorkspace} = useWorkspaceStore();

  if (!projects.length) {
    return <EmptyState title="No projects discovered yet" body="Create a new project or place an existing project folder under the configured workspace root." />;
  }

  return (
    <section className="stack wide-gap">
      <PageHeader
        eyebrow="Workspace"
        title="Projects"
        description="Manage local video projects, see the current production step, and jump into the next action."
        actions={<button className="primary-button" onClick={() => navigate('/projects/new')}>+ New Project</button>}
        meta={`${projects.length} projects`}
      />
      <div className="panel">
        <SectionTitle title="Production status" meta={<button className="ghost-button" onClick={refreshWorkspace}>Refresh</button>} />
        <div className="metric-grid">
          <MetricCard label="Total projects" value={workspace?.total_projects ?? 0} />
          <MetricCard label="Full support" value={workspace?.full_support_projects ?? 0} tone="success" />
          <MetricCard label="Limited support" value={workspace?.limited_support_projects ?? 0} tone="warn" />
          <MetricCard label="Blocked" value={workspace?.blocked_projects ?? 0} tone="warn" />
        </div>
      </div>
      <div className="panel">
        <SectionTitle title="Project queue" meta={`${projects.length} items`} />
        <ProjectTable
          projects={projects}
          onOpen={(id) => { setSelectedProjectId(id); navigate(`/projects/${id}/overview`); }}
          onPipeline={(id) => { setSelectedProjectId(id); navigate(`/projects/${id}/pipeline`); }}
        />
      </div>
    </section>
  );
}
