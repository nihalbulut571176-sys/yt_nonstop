import {ListBlock} from '../../shared/ui/ListBlock.jsx';
import {MetricCard} from '../../shared/ui/MetricCard.jsx';
import {SectionTitle} from '../../shared/ui/SectionTitle.jsx';
import {useProjectStore} from '../../state/StudioProvider.jsx';
import {formatCommand, formatTime} from '../../shared/types/contracts.js';
import {PipelineStageRail} from '../../shared/ui/PipelineStageRail.jsx';
import {RunMonitorCard} from '../../shared/ui/RunMonitorCard.jsx';
import {ActivityFeed} from '../../shared/ui/ActivityFeed.jsx';
import {PageHeader} from '../../shared/ui/PageHeader.jsx';

export function OverviewPage() {
  const {overview, pipelineState} = useProjectStore();

  if (!overview) {
    return <section className="panel"><p className="muted">Select a project to see its overview.</p></section>;
  }

  return (
    <section className="stack wide-gap">
      <PageHeader
        eyebrow="Control room"
        title={overview.project_name}
        description="The fastest read on what is happening, what is blocked, and what output is ready."
        meta={overview.lifecycle_status}
      />
      <PipelineStageRail pipelineState={pipelineState} compact />
      <RunMonitorCard pipelineState={pipelineState || overview} title="Current activity" />
      <div className="metric-grid">
        <MetricCard label="Lifecycle" value={overview.lifecycle_status} tone="accent" />
        <MetricCard label="Progress" value={`${overview.progress?.percent ?? pipelineState?.progress?.percent ?? 0}%`} tone="success" />
        <MetricCard label="Current step" value={overview.progress?.current_stage_label || overview.current_stage || 'n/a'} />
        <MetricCard label="Next stage" value={overview.next_stage || 'n/a'} tone="success" />
      </div>

      <div className="grid-two">
        <div className="panel">
          <SectionTitle title="Recommended next action" />
          <div className="hero-action">
            <h3>{overview.next_command || 'No next command available'}</h3>
            <p className="muted">This command reflects the product-facing pipeline recommendation for the selected project.</p>
          </div>
        </div>
        <div className="panel">
          <SectionTitle title="Latest Run" meta={overview.latest_run?.status || 'idle'} />
          {overview.latest_run ? (
            <dl className="details">
              <div><dt>Action</dt><dd>{overview.latest_run.action_type}</dd></div>
              <div><dt>Started</dt><dd>{formatTime(overview.latest_run.started_at)}</dd></div>
              <div><dt>Finished</dt><dd>{formatTime(overview.latest_run.finished_at)}</dd></div>
              <div><dt>Command</dt><dd><code>{formatCommand(overview.latest_run.command)}</code></dd></div>
            </dl>
          ) : <p className="muted">No persisted run history yet.</p>}
        </div>
      </div>

      <div className="panel">
        <SectionTitle title="Recent Events" meta={`${overview.recent_events?.length || 0} events`} />
        <ActivityFeed events={overview.recent_events || pipelineState?.recent_events || []} />
      </div>

      <div className="grid-two">
        <div className="panel">
          <SectionTitle title="Blockers" meta={`${overview.blocked.length}`} />
          <ListBlock title="Blocked reasons" rows={overview.blocked} empty="No blockers currently." tone="warn" />
        </div>
        <div className="panel">
          <SectionTitle title="Warnings" meta={`${overview.warnings.length}`} />
          <ListBlock title="Warning signals" rows={overview.warnings} empty="No warnings currently." tone="accent" />
        </div>
      </div>

      <div className="panel">
        <SectionTitle title="Recent Outputs" meta={`${overview.latest_outputs.length}`} />
        <ListBlock title="Latest outputs" rows={overview.latest_outputs} empty="No tracked outputs yet." tone="accent" />
      </div>
    </section>
  );
}
