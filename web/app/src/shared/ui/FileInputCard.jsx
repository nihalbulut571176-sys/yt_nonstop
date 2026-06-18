export function FileInputCard({label, file, accept, optional = false, helper, onChange}) {
  return (
    <label className="file-card">
      <span className="file-card-label">{label}{optional ? ' (optional)' : ''}</span>
      <input type="file" accept={accept} onChange={(event) => onChange(event.target.files?.[0] || null)} />
      <strong>{file?.name || 'Choose file'}</strong>
      {helper ? <small>{helper}</small> : null}
    </label>
  );
}
