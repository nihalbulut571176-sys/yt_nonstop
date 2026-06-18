export function SectionTitle({title, meta}) {
  return (
    <div className="panel-head">
      <h2>{title}</h2>
      {meta ? <span>{meta}</span> : null}
    </div>
  );
}
