const jsonHeaders = {'Content-Type': 'application/json'};
const TOKEN_KEY = 'yt-nonstop-studio-token';

function getToken() {
  return window.localStorage.getItem(TOKEN_KEY) || '';
}

function setToken(token) {
  if (!token) {
    window.localStorage.removeItem(TOKEN_KEY);
    return;
  }
  window.localStorage.setItem(TOKEN_KEY, token);
}

function authHeaders(extra = {}) {
  const token = getToken();
  return {
    ...extra,
    ...(token ? {Authorization: `Bearer ${token}`} : {})
  };
}

async function request(path, options = {}) {
  const response = await fetch(path, {...options, headers: authHeaders(options.headers || {})});
  const text = await response.text();
  const payload = text ? JSON.parse(text) : null;
  if (response.status === 401) {
    setToken('');
    throw new Error(payload?.message || payload?.detail || 'Authentication required');
  }
  if (!response.ok) {
    throw new Error(payload?.message || payload?.detail || `Request failed: ${response.status}`);
  }
  return payload;
}

export const api = {
  getToken,
  mediaUrl: (projectId, path) => `/api/projects/${projectId}/media?path=${encodeURIComponent(path)}&token=${encodeURIComponent(getToken())}`,
  login: async (body) => {
    const response = await fetch('/api/auth/login', {method: 'POST', headers: jsonHeaders, body: JSON.stringify(body)});
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload?.message || payload?.detail || `Request failed: ${response.status}`);
    }
    setToken(payload?.session?.token || '');
    return payload;
  },
  logout: async () => {
    try {
      await request('/api/auth/logout', {method: 'POST'});
    } finally {
      setToken('');
    }
  },
  me: () => request('/api/auth/me'),
  getWorkspaceSummary: () => request('/api/workspace/summary'),
  listProjects: () => request('/api/projects'),
  createProject: (body) => request('/api/projects', {method: 'POST', headers: jsonHeaders, body: JSON.stringify(body)}),
  intakeAudioTextProject: (body) => request('/api/projects/intake/audio-text', {method: 'POST', body}),
  intakeProject: (body) => request('/api/projects/intake', {method: 'POST', body}),
  getProject: (id) => request(`/api/projects/${id}`),
  getOverview: (id) => request(`/api/projects/${id}/overview`),
  getPipelineState: (id) => request(`/api/projects/${id}/pipeline`),
  getAssets: (id) => request(`/api/projects/${id}/assets`),
  getTimeline: (id) => request(`/api/projects/${id}/timeline`),
  getReviewQueue: (id) => request(`/api/projects/${id}/review`),
  listRuns: (limit = 50) => request(`/api/runs?limit=${limit}`),
  getRun: (id) => request(`/api/runs/${id}`),
  getRunLogs: (id) => request(`/api/runs/${id}/logs`),
  getProjectRuns: (id, limit = 50) => request(`/api/projects/${id}/runs?limit=${limit}`),
  preview: (id, path) => request(`/api/projects/${id}/preview?path=${encodeURIComponent(path)}`),
  pipelineAction: (id, body) => request(`/api/projects/${id}/pipeline/actions`, {method: 'POST', headers: jsonHeaders, body: JSON.stringify(body)}),
  applyReview: (id, body) => request(`/api/projects/${id}/review/apply`, {method: 'POST', headers: jsonHeaders, body: JSON.stringify(body)}),
  saveReviewDecision: (id, body) => request(`/api/projects/${id}/review/decisions`, {method: 'POST', headers: jsonHeaders, body: JSON.stringify(body)}),
  getSettings: () => request('/api/settings'),
  updateSettings: (body) => request('/api/settings', {method: 'PATCH', headers: jsonHeaders, body: JSON.stringify(body)})
};
