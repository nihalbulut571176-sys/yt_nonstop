import {ListBlock} from '../../shared/ui/ListBlock.jsx';
import {MetricCard} from '../../shared/ui/MetricCard.jsx';
import {SectionTitle} from '../../shared/ui/SectionTitle.jsx';
import {useProjectStore} from '../../state/StudioProvider.jsx';
import {formatCommand, formatTime} from '../../shared/types/contracts.js';

export function OverviewPage() {
  const {overview} = useProjectStore();

  if (!overview) {
    return <section className="panel"><p className="muted">Select a project to see its overview.</p></section>;
  }

  return (
    <section className="stack wide-gap">
      <div className="metric-grid">
        <MetricCard label="Lifecycle" value={overview.lifecycle_status} tone="accent" />
        <MetricCard label="Current stage" value={overview.current_stage || 'n/a'} />
        <MetricCard label="Next stage" value={overview.next_stage || 'n/a'} tone="success" />
        <MetricCard label="Review decisions" value={overview.review_decision_count} tone="warn" />
      </div>

      <div className="grid-two">
        <div className="panel">
          <SectionTitle title="Recommended Next Command" />
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
