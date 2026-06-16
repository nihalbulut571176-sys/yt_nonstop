import {formatCommand, formatTime} from '../types/contracts.js';

export function RunsTable({rows}) {
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Status</th>
            <th>Action</th>
            <th>User</th>
            <th>Started</th>
            <th>Finished</th>
            <th>Exit</th>
            <th>Command</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((run) => (
            <tr key={run.run_id}>
              <td>{run.status}</td>
              <td>{run.action_type || 'n/a'}</td>
              <td>{run.username || 'n/a'}</td>
              <td>{formatTime(run.started_at)}</td>
              <td>{formatTime(run.finished_at)}</td>
              <td>{run.exit_code ?? 'n/a'}</td>
              <td><code>{formatCommand(run.command)}</code></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
