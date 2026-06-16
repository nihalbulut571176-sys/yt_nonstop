const jsonHeaders = {'Content-Type': 'application/json'};

async function request(path, options = {}) {
  const response = await fetch(path, options);
  const text = await response.text();
  const payload = text ? JSON.parse(text) : null;
  if (!response.ok) {
    throw new Error(payload?.detail || `Request failed: ${response.status}`);
  }
  return payload;
}

export const api = {
  listProjects: () => request('/api/projects'),
  getProject: (id) => request(`/api/projects/${id}`),
  getStatus: (id) => request(`/api/projects/${id}/status`),
  getArtifacts: (id) => request(`/api/projects/${id}/artifacts`),
  getTimeline: (id) => request(`/api/projects/${id}/timeline`),
  getReview: (id) => request(`/api/projects/${id}/review`),
  listJobs: () => request('/api/jobs'),
  getJob: (id) => request(`/api/jobs/${id}`),
  getJobLogs: (id) => request(`/api/jobs/${id}/logs`),
  preview: (id, path) => request(`/api/projects/${id}/preview?path=${encodeURIComponent(path)}`),
  validate: (id, body) => request(`/api/projects/${id}/validate`, {method: 'POST', headers: jsonHeaders, body: JSON.stringify(body)}),
  run: (id, body) => request(`/api/projects/${id}/run`, {method: 'POST', headers: jsonHeaders, body: JSON.stringify(body)}),
  applyReview: (id, body) => request(`/api/projects/${id}/review/apply`, {method: 'POST', headers: jsonHeaders, body: JSON.stringify(body)})
};
