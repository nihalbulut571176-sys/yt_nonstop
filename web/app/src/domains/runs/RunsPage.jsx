import {SectionTitle} from '../../shared/ui/SectionTitle.jsx';
import {RunsTable} from '../../shared/ui/RunsTable.jsx';
import {useRunsStore} from '../../state/StudioProvider.jsx';

export function RunsPage() {
  const {projectRuns, globalRuns, activeRunDetails} = useRunsStore();

  return (
    <section className="stack">
      <div className="panel">
        <SectionTitle title="Active Run Event Stream" meta={activeRunDetails?.run_id || 'idle'} />
        {activeRunDetails ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Event</th>
                  <th>Message</th>
                  <th>Created</th>
                </tr>
              </thead>
              <tbody>
                {activeRunDetails.events.map((event) => (
                  <tr key={event.event_id}>
                    <td>{event.event_type}</td>
                    <td>{event.message}</td>
                    <td>{event.created_at}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : <p className="muted">No active run events are currently available.</p>}
      </div>
      <div className="grid-two">
        <div className="panel">
          <SectionTitle title="Project Runs" meta={`${projectRuns.length} rows`} />
          <RunsTable rows={projectRuns} />
        </div>
        <div className="panel">
          <SectionTitle title="Workspace Runs" meta={`${globalRuns.length} rows`} />
          <RunsTable rows={globalRuns} />
        </div>
      </div>
    </section>
  );
}
