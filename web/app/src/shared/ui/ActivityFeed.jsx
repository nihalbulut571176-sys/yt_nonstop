import {formatTime} from '../types/contracts.js';

function toneClass(tone) {
  return `event-${tone || 'neutral'}`;
}

export function ActivityFeed({events = [], empty = 'No events yet.'}) {
  if (!events.length) {
    return <p className="muted">{empty}</p>;
  }
  return (
    <div className="activity-feed">
      {events.map((event, index) => (
        <div className={`activity-item ${toneClass(event.tone)}`} key={`${event.timestamp || 'event'}-${index}`}>
          <span className="activity-dot" />
          <time>{event.timestamp ? formatTime(event.timestamp) : 'log'}</time>
          <p>{event.message}</p>
        </div>
      ))}
    </div>
  );
}
