export const reviewDecisionOptions = ['pending', 'approved', 'warning', 'manual_review', 'regenerate', 'rejected', 'finalized'];

export function formatTime(value) {
  if (!value) return 'n/a';
  return new Date(value).toLocaleString();
}

export function formatCommand(command) {
  if (!command || !command.length) return 'n/a';
  return command.join(' ');
}

export function titleCase(value) {
  return String(value || '')
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (char) => char.toUpperCase());
}
