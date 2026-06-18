import {Badge} from './Badge.jsx';
import {ActivityFeed} from './ActivityFeed.jsx';
import {LogPanel} from './LogPanel.jsx';
import {ProgressBar} from './ProgressBar.jsx';

function toneForStatus(status) {
  if (status === 'running' || status === 'done') return 'success';
  if (status === 'failed' || status === 'blocked') return 'warn';
  return 'neutral';
}

export function RunMonitorCard({pipelineState, title = 'Live progress', showLogs = true}) {
  const activity = pipelineState?.current_activity;
  const progress = pipelineState?.progress || {};
  const status = activity?.status || (progress.is_running ? 'running' : progress.is_failed ? 'failed' : 'pending');
  const percent = Math.max(0, Math.min(100, Number(progress.percent || 0)));
  return (
    <section className={`monitor-card monitor-${status}`}>
      <div className="monitor-head">
        <div>
          <p className="eyebrow">{title}</p>
          <h3>{activity?.title || progress.current_stage_label || 'Waiting for pipeline'}</h3>
          <p className="muted">{activity?.detail || 'Studio will update this panel as soon as a run starts.'}</p>
        </div>
        <Badge tone={toneForStatus(status)}>{status}</Badge>
      </div>
      <ProgressBar value={percent} />
      <div className="monitor-meta">
        <span>{percent}% complete</span>
        <span>{progress.active_run_id ? `run ${progress.active_run_id}` : 'no active run'}</span>
        <span>{progress.elapsed_sec ? `${Math.round(progress.elapsed_sec)}s elapsed` : 'elapsed n/a'}</span>
      </div>
      <ActivityFeed events={pipelineState?.recent_events || []} empty="No recent events yet. When the worker writes logs, they appear here." />
      {showLogs && activity?.log_tail?.length ? (
        <LogPanel lines={activity.log_tail} />
      ) : null}
    </section>
  );
}
