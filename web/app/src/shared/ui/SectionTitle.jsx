export function SectionTitle({title, meta}) {
  return (
    <div className="panel-head">
      <span>{title}</span>
      {meta ? <span>{meta}</span> : null}
    </div>
  );
}
