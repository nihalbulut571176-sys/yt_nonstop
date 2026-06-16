export function ListBlock({title, rows, empty, tone = 'neutral'}) {
  return (
    <div className="callout-list">
      <h3>{title}</h3>
      {rows?.length ? (
        <ul className={`flat-list tone-${tone}`}>
          {rows.map((item) => <li key={item}>{item}</li>)}
        </ul>
      ) : (
        <p className="muted">{empty}</p>
      )}
    </div>
  );
}
