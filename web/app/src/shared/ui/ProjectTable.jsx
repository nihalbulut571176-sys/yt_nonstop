import {Badge} from './Badge.jsx';
import {formatTime} from '../types/contracts.js';

function toneForLifecycle(value) {
  if (value === 'running' || value === 'completed' || value === 'ready_for_render') return 'success';
  if (value === 'failed' || value === 'blocked') return 'warn';
  if (value === 'awaiting_review') return 'accent';
  return 'neutral';
}

export function ProjectTable({projects = [], onOpen, onPipeline}) {
  return (
    <div className="table-wrap project-table-wrap">
      <table className="project-table">
        <thead>
          <tr>
            <th>Project</th>
            <th>Status</th>
            <th>Current step</th>
            <th>Progress</th>
            <th>Updated</th>
            <th>Action</th>
          </tr>
        </thead>
        <tbody>
          {projects.map((item) => {
            const percent = item.lifecycle_status === 'completed' ? 100 : item.lifecycle_status === 'running' ? 50 : 0;
            return (
              <tr key={item.id}>
                <td>
                  <strong>{item.name}</strong>
                  <span className="table-path">{item.path}</span>
                </td>
                <td><Badge tone={toneForLifecycle(item.lifecycle_status)}>{item.lifecycle_status || item.status}</Badge></td>
                <td>{item.current_stage || item.next_stage || 'Not started'}</td>
                <td>
                  <div className="mini-progress"><span style={{width: `${percent}%`}} /></div>
                  <small>{item.blocked_count ? `${item.blocked_count} blockers` : item.warning_count ? `${item.warning_count} warnings` : `${percent}%`}</small>
                </td>
                <td>{formatTime(item.last_updated)}</td>
                <td>
                  <div className="table-actions">
                    <button type="button" onClick={() => onOpen(item.id)}>Open</button>
                    <button type="button" className="ghost-button" onClick={() => onPipeline(item.id)}>{item.lifecycle_status === 'failed' || item.lifecycle_status === 'blocked' ? 'Fix' : item.lifecycle_status === 'running' ? 'Watch' : 'Pipeline'}</button>
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
