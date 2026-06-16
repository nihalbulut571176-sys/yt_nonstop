import {Badge} from '../../shared/ui/Badge.jsx';
import {ListBlock} from '../../shared/ui/ListBlock.jsx';
import {SectionTitle} from '../../shared/ui/SectionTitle.jsx';
import {useProjectStore, useRunsStore, useStudioShell} from '../../state/StudioProvider.jsx';
import {formatCommand, formatTime} from '../../shared/types/contracts.js';
import {useState} from 'react';
import {RunsTable} from '../../shared/ui/RunsTable.jsx';

function QuickActionButton({label, actionKey, pipelineState, busyAction, onRun}) {
  const descriptor = (pipelineState?.available_actions || []).find((item) => item.key === actionKey);
  const disabled = !descriptor?.enabled || busyAction === actionKey;
  return (
    <button className="quick-button" disabled={disabled} onClick={() => onRun(actionKey)}>
      <strong>{label}</strong>
      <span>{descriptor?.reason || (descriptor?.recommended ? 'Recommended now' : 'Available action')}</span>
    </button>
  );
}

export function PipelinePage() {
  const {pipelineState, refreshProject, selectedProjectId} = useProjectStore();
  const {projectRuns, activeRunDetails} = useRunsStore();
  const {busyAction, runPipelineAction, applyReview} = useStudioShell();
  const [form, setForm] = useState({
    from_stage: '',
    to_stage: 'render',
    profile: '',
    limit_frames: 0,
    real_generation: false,
    concurrency: 10,
    dry_run: false
  });

  if (!pipelineState) {
    return <section className="panel"><p className="muted">Select a project to inspect pipeline state.</p></section>;
  }

  const writeDisabled = pipelineState.support !== 'full' || Boolean(pipelineState.active_run);

  const runQuickAction = async (action) => {
    await runPipelineAction({
      action,
      to_stage: form.to_stage || 'render',
      profile: form.profile || null,
      limit_frames: Number(form.limit_frames || 0),
      real_generation: form.real_generation,
      concurrency: Number(form.concurrency || 10),
      from_stage: form.from_stage || null,
      dry_run: form.dry_run
    });
  };

  return (
    <section className="stack wide-gap">
      <div className="grid-two">
        <div className="panel">
          <SectionTitle title="Primary Action Rail" meta={pipelineState.next_stage || 'n/a'} />
          <div className="hero-action">
            <h3>{pipelineState.next_command || 'No next command detected'}</h3>
            <p className="muted">Current stage: {pipelineState.current_stage || 'n/a'}. Lifecycle: {pipelineState.lifecycle_status}.</p>
          </div>
          <div className="meta-row">
            <Badge tone={pipelineState.ready_for_generation ? 'success' : 'neutral'}>generation {String(pipelineState.ready_for_generation)}</Badge>
            <Badge tone={pipelineState.ready_for_qc ? 'success' : 'neutral'}>qc {String(pipelineState.ready_for_qc)}</Badge>
            <Badge tone={pipelineState.ready_for_render ? 'success' : 'neutral'}>render {String(pipelineState.ready_for_render)}</Badge>
            <Badge tone={pipelineState.ready_for_human_review ? 'warn' : 'neutral'}>review {String(pipelineState.ready_for_human_review)}</Badge>
          </div>
          <div className="quick-grid">
            <QuickActionButton label="Validate" actionKey="validate" pipelineState={pipelineState} busyAction={busyAction} onRun={runQuickAction} />
            <QuickActionButton label="Resume" actionKey="resume" pipelineState={pipelineState} busyAction={busyAction} onRun={runQuickAction} />
            <QuickActionButton label="Retry Failed" actionKey="retry_failed_only" pipelineState={pipelineState} busyAction={busyAction} onRun={runQuickAction} />
            <QuickActionButton label="Render Dry Run" actionKey="render_dry_run" pipelineState={pipelineState} busyAction={busyAction} onRun={runQuickAction} />
          </div>
        </div>
        <div className="panel">
          <SectionTitle title="Pipeline State" meta={pipelineState.lifecycle_status} />
          <div className="info-cluster">
            {pipelineState.blocked_by_active_run ? <ListBlock title="Active run lock" rows={[pipelineState.active_run?.run_id || 'A write-heavy run is active.']} tone="warn" /> : null}
            <ListBlock title="Blocked reasons" rows={pipelineState.blocked} empty="No blockers detected." tone="warn" />
            <ListBlock title="Warnings" rows={pipelineState.warnings} empty="No warnings detected." />
            <ListBlock title="Info" rows={pipelineState.info} empty="No extra notes." tone="accent" />
          </div>
        </div>
      </div>

      <div className="grid-two">
        <div className="panel">
          <SectionTitle title="Advanced Controls" />
          <div className="form-grid">
            <label><span>From stage</span><input value={form.from_stage} onChange={(event) => setForm({...form, from_stage: event.target.value})} /></label>
            <label><span>To stage</span><input value={form.to_stage} onChange={(event) => setForm({...form, to_stage: event.target.value})} /></label>
            <label><span>Profile</span><input value={form.profile} onChange={(event) => setForm({...form, profile: event.target.value})} /></label>
            <label><span>Limit frames</span><input type="number" value={form.limit_frames} onChange={(event) => setForm({...form, limit_frames: Number(event.target.value)})} /></label>
            <label><span>Concurrency</span><input type="number" value={form.concurrency} onChange={(event) => setForm({...form, concurrency: Number(event.target.value)})} /></label>
          </div>
          <div className="toggle-row">
            <button className={`toggle ${form.real_generation ? 'active' : ''}`} onClick={() => setForm({...form, real_generation: !form.real_generation})}>Real generation</button>
            <button className={`toggle ${form.dry_run ? 'active' : ''}`} onClick={() => setForm({...form, dry_run: !form.dry_run})}>Dry run</button>
          </div>
          <div className="action-row">
            <button disabled={writeDisabled || busyAction === 'run_range'} onClick={() => runQuickAction('run_range')}>Run stage range</button>
            <button disabled={writeDisabled || busyAction === 'review'} onClick={() => applyReview({dry_run: form.dry_run})}>Apply review</button>
            <button className="ghost-button" onClick={() => refreshProject(selectedProjectId)}>Refresh state</button>
          </div>
        </div>
        <div className="panel">
          <SectionTitle title="Active Run" meta={pipelineState.active_run?.run_id || 'No active run'} />
          {activeRunDetails ? (
            <div className="stack compact">
              <dl className="details">
                <div><dt>Status</dt><dd>{activeRunDetails.status}</dd></div>
                <div><dt>Started</dt><dd>{formatTime(activeRunDetails.started_at)}</dd></div>
                <div><dt>Finished</dt><dd>{formatTime(activeRunDetails.finished_at)}</dd></div>
                <div><dt>Command</dt><dd><code>{formatCommand(activeRunDetails.command)}</code></dd></div>
              </dl>
              <pre className="mono-box tall">{(activeRunDetails.log_tail || []).join('\n') || 'Waiting for log output…'}</pre>
            </div>
          ) : (
            <p className="muted">No write-heavy run is currently active for this project.</p>
          )}
        </div>
      </div>

      <div className="panel">
        <SectionTitle title="Run History" meta={`${projectRuns.length} runs`} />
        <RunsTable rows={projectRuns} />
      </div>
    </section>
  );
}
