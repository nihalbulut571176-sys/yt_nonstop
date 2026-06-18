export function LogPanel({lines = [], empty = 'No log output yet.'}) {
  return (
    <pre className="log-panel">
      {(lines || []).length ? lines.join('\n') : empty}
    </pre>
  );
}
