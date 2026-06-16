import {useEffect, useState} from 'react';
import {NavLink, Route, Routes, useNavigate} from 'react-router-dom';
import {api} from './api.js';

const navItems = [
  {to: '/', label: 'Projects', end: true},
  {to: '/pipeline', label: 'Pipeline'},
  {to: '/review', label: 'Review'},
  {to: '/assets', label: 'Assets'}
];

function formatTime(value) {
  if (!value) return 'n/a';
  return new Date(value).toLocaleString();
}

function Badge({tone = 'neutral', children}) {
  return <span className={`badge badge-${tone}`}>{children}</span>;
}

function useStudioData() {
  const [projects, setProjects] = useState([]);
  const [selectedId, setSelectedId] = useState('');
  const [project, setProject] = useState(null);
  const [jobs, setJobs] = useState([]);
  const [status, setStatus] = useState(null);
  const [timeline, setTimeline] = useState({rows: []});
  const [review, setReview] = useState({rows: []});
  const [artifacts, setArtifacts] = useState([]);
  const [preview, setPreview] = useState(null);
  const [error, setError] = useState('');

  const refreshProjects = async () => {
    try {
      const list = await api.listProjects();
      setProjects(list);
      if (!selectedId && list[0]) {
        setSelectedId(list[0].id);
      }
      if (selectedId && !list.find((item) => item.id === selectedId) && list[0]) {
        setSelectedId(list[0].id);
      }
      setError('');
    } catch (err) {
      setError(err.message);
    }
  };

  const refreshJobs = async () => {
    try {
      setJobs(await api.listJobs());
    } catch (err) {
      setError(err.message);
    }
  };

  const refreshProjectBundle = async (projectId) => {
    if (!projectId) return;
    try {
      const [projectData, statusData, timelineData, reviewData, artifactData] = await Promise.all([
        api.getProject(projectId),
        api.getStatus(projectId),
        api.getTimeline(projectId),
        api.getReview(projectId),
        api.getArtifacts(projectId)
      ]);
      setProject(projectData);
      setStatus(statusData);
      setTimeline(timelineData);
      setReview(reviewData);
      setArtifacts(artifactData);
      setPreview(null);
      setError('');
    } catch (err) {
      setError(err.message);
    }
  };

  useEffect(() => {
    refreshProjects();
    refreshJobs();
  }, []);

  useEffect(() => {
    refreshProjectBundle(selectedId);
  }, [selectedId]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      refreshJobs();
      if (selectedId) {
        refreshProjectBundle(selectedId);
      }
    }, 4000);
    return () => window.clearInterval(timer);
  }, [selectedId]);

  return {
    projects,
    selectedId,
    setSelectedId,
    project,
    jobs,
    status,
    timeline,
    review,
    artifacts,
    preview,
    setPreview,
    error,
    setError,
    refreshProjects,
    refreshJobs,
    refreshProjectBundle
  };
}

function Shell({studio}) {
  const navigate = useNavigate();

  useEffect(() => {
    if (!studio.selectedId && studio.projects[0]) {
      studio.setSelectedId(studio.projects[0].id);
      navigate('/');
    }
  }, [studio.projects, studio.selectedId, navigate]);

  return (
    <div className="studio">
      <aside className="sidebar">
        <div className="sidebar-brand">
          <p className="eyebrow">Local Operator Studio</p>
          <h1>yt_nonstop</h1>
          <p className="sidebar-copy">CLI-first production control over the live `YT_visual` workspace.</p>
        </div>
        <div className="project-picker">
          <div className="panel-head">
            <span>Projects</span>
            <button className="ghost-button" onClick={studio.refreshProjects}>Refresh</button>
          </div>
          <div className="project-list">
            {studio.projects.map((item) => (
              <button
                key={item.id}
                className={`project-chip ${studio.selectedId === item.id ? 'active' : ''}`}
                onClick={() => studio.setSelectedId(item.id)}
              >
                <strong>{item.name}</strong>
                <span>{item.kind}</span>
              </button>
            ))}
          </div>
        </div>
        <nav className="nav">
          {navItems.map((item) => (
            <NavLink key={item.to} to={item.to} end={item.end} className={({isActive}) => `nav-link ${isActive ? 'active' : ''}`}>
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-footer">
          <p>Workspace root</p>
          <code>C:\Users\MIKE\Documents\Codex\YT_visual</code>
        </div>
      </aside>
      <main className="main">
        <header className="masthead">
          <div>
            <p className="eyebrow">Selected Project</p>
            <h2>{studio.project?.name || 'No project selected'}</h2>
            <p className="muted">{studio.project?.path || 'Pick a project from the sidebar.'}</p>
          </div>
          <div className="masthead-stats">
            <Badge tone={studio.project?.support === 'full' ? 'success' : 'warn'}>{studio.project?.support || 'idle'}</Badge>
            <Badge tone="neutral">{studio.project?.kind || 'workspace'}</Badge>
            <Badge tone="accent">{studio.status?.next_stage || studio.project?.status || 'pending'}</Badge>
          </div>
        </header>
        {studio.error ? <div className="error-banner">{studio.error}</div> : null}
        <Routes>
          <Route path="/" element={<ProjectsScreen studio={studio} />} />
          <Route path="/pipeline" element={<PipelineScreen studio={studio} />} />
          <Route path="/review" element={<ReviewScreen studio={studio} />} />
          <Route path="/assets" element={<AssetsScreen studio={studio} />} />
        </Routes>
      </main>
    </div>
  );
}

function ProjectsScreen({studio}) {
  return (
    <section className="grid-two">
      <div className="panel">
        <div className="panel-head">
          <span>Discovered Projects</span>
          <span>{studio.projects.length} total</span>
        </div>
        <div className="stack">
          {studio.projects.map((item) => (
            <article key={item.id} className={`project-card ${studio.selectedId === item.id ? 'active' : ''}`}>
              <div>
                <h3>{item.name}</h3>
                <p>{item.path}</p>
              </div>
              <div className="meta-row">
                <Badge tone={item.support === 'full' ? 'success' : 'warn'}>{item.support}</Badge>
                <Badge tone="neutral">{item.status}</Badge>
              </div>
              <p className="muted">Updated {formatTime(item.last_updated)}</p>
              <div className="tag-row">
                {item.available_outputs.map((output) => <span key={output} className="tag">{output}</span>)}
              </div>
            </article>
          ))}
        </div>
      </div>
      <div className="panel">
        <div className="panel-head">
          <span>Current Snapshot</span>
        </div>
        {studio.project ? (
          <div className="stack">
            <dl className="details">
              <div><dt>ID</dt><dd>{studio.project.id}</dd></div>
              <div><dt>Current stage</dt><dd>{studio.project.current_stage || 'n/a'}</dd></div>
              <div><dt>Next stage</dt><dd>{studio.project.next_stage || 'n/a'}</dd></div>
              <div><dt>Next command</dt><dd><code>{studio.project.next_command || 'n/a'}</code></dd></div>
            </dl>
            <div className="tag-row">
              {(studio.project.markers || []).map((marker) => <span key={marker} className="tag">{marker}</span>)}
            </div>
            <pre className="mono-box">{JSON.stringify(studio.status || {}, null, 2)}</pre>
          </div>
        ) : (
          <p className="muted">No project selected yet.</p>
        )}
      </div>
    </section>
  );
}

function PipelineScreen({studio}) {
  const [form, setForm] = useState({
    from_stage: '',
    to_stage: 'render',
    profile: '',
    limit_frames: 0,
    real_generation: false,
    concurrency: 10,
    resume: false,
    retry_failed_only: false,
    render_dry_run: false,
    dry_run: false
  });
  const currentJob = studio.jobs.find((item) => item.project_id === studio.selectedId);
  const [logs, setLogs] = useState([]);

  useEffect(() => {
    if (!currentJob) {
      setLogs([]);
      return;
    }
    api.getJobLogs(currentJob.job_id).then((payload) => setLogs(payload.lines)).catch(() => {});
  }, [currentJob]);

  const runAction = async (type) => {
    if (!studio.selectedId) return;
    try {
      if (type === 'validate') {
        await api.validate(studio.selectedId, {stage: 'all'});
      } else if (type === 'review') {
        await api.applyReview(studio.selectedId, {dry_run: form.dry_run});
      } else {
        await api.run(studio.selectedId, form);
      }
      await studio.refreshJobs();
      await studio.refreshProjectBundle(studio.selectedId);
      studio.setError('');
    } catch (err) {
      studio.setError(err.message);
    }
  };

  const toggle = (name) => setForm((prev) => ({...prev, [name]: !prev[name]}));

  return (
    <section className="grid-two">
      <div className="panel">
        <div className="panel-head">
          <span>Pipeline Control</span>
          <Badge tone={currentJob?.status === 'running' ? 'accent' : 'neutral'}>{currentJob?.status || 'idle'}</Badge>
        </div>
        <div className="form-grid">
          <label>
            <span>From stage</span>
            <input value={form.from_stage} onChange={(e) => setForm({...form, from_stage: e.target.value})} placeholder="generate_images" />
          </label>
          <label>
            <span>To stage</span>
            <input value={form.to_stage} onChange={(e) => setForm({...form, to_stage: e.target.value})} placeholder="render" />
          </label>
          <label>
            <span>Profile</span>
            <input value={form.profile} onChange={(e) => setForm({...form, profile: e.target.value})} placeholder="fastgen_pilot" />
          </label>
          <label>
            <span>Limit frames</span>
            <input type="number" value={form.limit_frames} onChange={(e) => setForm({...form, limit_frames: Number(e.target.value)})} />
          </label>
          <label>
            <span>Concurrency</span>
            <input type="number" value={form.concurrency} onChange={(e) => setForm({...form, concurrency: Number(e.target.value)})} />
          </label>
        </div>
        <div className="toggle-row">
          {[
            ['real_generation', 'Real generation'],
            ['resume', 'Resume'],
            ['retry_failed_only', 'Retry failed only'],
            ['render_dry_run', 'Render dry run'],
            ['dry_run', 'Dry run']
          ].map(([name, label]) => (
            <button key={name} className={`toggle ${form[name] ? 'active' : ''}`} onClick={() => toggle(name)}>{label}</button>
          ))}
        </div>
        <div className="action-row">
          <button onClick={() => runAction('validate')}>Validate</button>
          <button onClick={() => runAction('run')}>Run from stage</button>
          <button onClick={() => runAction('review')}>Apply review</button>
        </div>
        <div className="stack compact">
          <h3>Stage Summary</h3>
          <dl className="details">
            <div><dt>Current</dt><dd>{studio.status?.current_stage || 'n/a'}</dd></div>
            <div><dt>Next</dt><dd>{studio.status?.next_stage || 'n/a'}</dd></div>
            <div><dt>Render ready</dt><dd>{String(studio.status?.ready_for_render ?? false)}</dd></div>
            <div><dt>Human review</dt><dd>{String(studio.status?.ready_for_human_review ?? false)}</dd></div>
          </dl>
        </div>
      </div>
      <div className="panel">
        <div className="panel-head">
          <span>Live Job Log</span>
          <span>{currentJob?.job_id || 'No active job'}</span>
        </div>
        <div className="stack compact">
          <dl className="details">
            <div><dt>Status</dt><dd>{currentJob?.status || 'idle'}</dd></div>
            <div><dt>Started</dt><dd>{formatTime(currentJob?.started_at)}</dd></div>
            <div><dt>Finished</dt><dd>{formatTime(currentJob?.finished_at)}</dd></div>
            <div><dt>Exit code</dt><dd>{currentJob?.exit_code ?? 'n/a'}</dd></div>
          </dl>
          <pre className="mono-box tall">{logs.join('\n') || 'No logs yet.'}</pre>
        </div>
      </div>
    </section>
  );
}

function ReviewScreen({studio}) {
  const rows = studio.review.rows.length ? studio.review.rows : studio.timeline.rows;
  return (
    <section className="panel">
      <div className="panel-head">
        <span>Review Surface</span>
        <span>{rows.length} rows</span>
      </div>
      <p className="muted">Read-only v1 surface over existing timeline, review sheet, and selected-image artifacts.</p>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              {Object.keys(rows[0] || {empty: ''}).map((key) => <th key={key}>{key}</th>)}
            </tr>
          </thead>
          <tbody>
            {rows.slice(0, 200).map((row, index) => (
              <tr key={index}>
                {Object.keys(rows[0] || {empty: ''}).map((key) => <td key={key}>{String(row[key] ?? '')}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function AssetsScreen({studio}) {
  const grouped = studio.artifacts.reduce((acc, item) => {
    acc[item.type] = acc[item.type] || [];
    acc[item.type].push(item);
    return acc;
  }, {});

  const openPreview = async (path) => {
    try {
      const payload = await api.preview(studio.selectedId, path);
      studio.setPreview(payload);
      studio.setError('');
    } catch (err) {
      studio.setError(err.message);
    }
  };

  return (
    <section className="grid-two">
      <div className="panel">
        <div className="panel-head">
          <span>Artifact Browser</span>
          <span>{studio.artifacts.length} files</span>
        </div>
        <div className="stack">
          {Object.entries(grouped).map(([group, items]) => (
            <div key={group} className="asset-group">
              <h3>{group}</h3>
              {items.slice(0, 120).map((item) => (
                <button key={item.path} className="asset-row" onClick={() => openPreview(item.path)}>
                  <div>
                    <strong>{item.label}</strong>
                    <p>{item.path}</p>
                  </div>
                  <div className="meta-row">
                    <Badge tone="neutral">{item.preview_kind}</Badge>
                    <span>{Math.round(item.size / 1024)} KB</span>
                  </div>
                </button>
              ))}
            </div>
          ))}
        </div>
      </div>
      <div className="panel">
        <div className="panel-head">
          <span>Preview</span>
          <span>{studio.preview?.preview_kind || 'none'}</span>
        </div>
        {!studio.preview ? <p className="muted">Choose any artifact to inspect it.</p> : null}
        {studio.preview?.preview_kind === 'image' ? <img className="asset-preview-image" src={`/api/projects/${studio.selectedId}/media?path=${encodeURIComponent(studio.preview.path)}`} alt={studio.preview.path} /> : null}
        {studio.preview?.preview_kind === 'video' ? <video className="asset-preview-video" controls src={`/api/projects/${studio.selectedId}/media?path=${encodeURIComponent(studio.preview.path)}`} /> : null}
        {studio.preview?.preview_kind === 'text' ? <pre className="mono-box tall">{studio.preview.content}</pre> : null}
        {studio.preview?.preview_kind === 'binary' ? <p className="muted">{studio.preview.path}</p> : null}
      </div>
    </section>
  );
}

export default function App() {
  const studio = useStudioData();
  return <Shell studio={studio} />;
}
