export function ProgressBar({value = 0, label}) {
  const percent = Math.max(0, Math.min(100, Number(value || 0)));
  return (
    <div className="progress-bar-wrap" aria-label={label || `Progress ${percent}%`}>
      <div className="progress-bar">
        <span style={{width: `${percent}%`}} />
      </div>
      {label ? <small>{label}</small> : null}
    </div>
  );
}
