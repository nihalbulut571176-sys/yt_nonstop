import {render, screen, waitFor} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {MemoryRouter} from 'react-router-dom';
import {beforeEach, expect, test, vi} from 'vitest';
import App from './App.jsx';

const {mockApi} = vi.hoisted(() => ({
  mockApi: {
    getToken: vi.fn(),
    login: vi.fn(),
    logout: vi.fn(),
    me: vi.fn(),
    getWorkspaceSummary: vi.fn(),
    listProjects: vi.fn(),
    createProject: vi.fn(),
    getProject: vi.fn(),
    getOverview: vi.fn(),
    getPipelineState: vi.fn(),
    getAssets: vi.fn(),
    getTimeline: vi.fn(),
    getReviewQueue: vi.fn(),
    listRuns: vi.fn(),
    getRun: vi.fn(),
    getRunLogs: vi.fn(),
    getProjectRuns: vi.fn(),
    preview: vi.fn(),
    mediaUrl: vi.fn(),
    pipelineAction: vi.fn(),
    applyReview: vi.fn(),
    saveReviewDecision: vi.fn(),
    getSettings: vi.fn(),
    updateSettings: vi.fn()
  }
}));

vi.mock('./api.js', () => ({
  api: mockApi
}));

const authPayload = {
  user: {id: 1, username: 'operator', display_name: 'Operator', role: 'Admin', is_active: true, created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z'},
  session: {token: 'token-1', user_id: 1, created_at: '2026-01-01T00:00:00Z', expires_at: '2026-01-02T00:00:00Z', last_seen_at: '2026-01-01T00:00:00Z'}
};

const project = {
  id: 'demo-project',
  name: 'Demo Project',
  path: 'C:\\demo',
  kind: 'repo-native',
  support: 'full',
  status: 'generate_images',
  lifecycle_status: 'awaiting_review',
  current_stage: 'generate_images',
  next_stage: 'render',
  blocked_count: 1,
  warning_count: 1,
  available_outputs: ['work', 'images']
};

const overview = {
  project_id: 'demo-project',
  project_name: 'Demo Project',
  path: 'C:\\demo',
  kind: 'repo-native',
  support: 'full',
  lifecycle_status: 'awaiting_review',
  current_stage: 'generate_images',
  next_stage: 'render',
  next_command: 'yt-nonstop run --resume',
  blocked: ['visual allocation plan is missing'],
  warnings: ['1 frame still in manual review'],
  latest_outputs: ['reports/notes.md'],
  latest_run: null,
  recent_runs: [],
  review_decision_count: 0,
  active_run: null
};

const pipelineState = {
  project_id: 'demo-project',
  project_name: 'Demo Project',
  support: 'full',
  lifecycle_status: 'awaiting_review',
  current_stage: 'generate_images',
  next_stage: 'render',
  next_command: 'yt-nonstop run --resume',
  blocked: ['visual allocation plan is missing'],
  warnings: ['1 frame still in manual review'],
  info: ['selected images exist'],
  blocked_count: 1,
  warning_count: 1,
  ready_for_generation: false,
  ready_for_qc: false,
  ready_for_render: false,
  ready_for_human_review: true,
  completed: false,
  active_run: null,
  recent_runs: [],
  available_actions: [
    {key: 'validate', label: 'Validate', recommended: true, enabled: true, reason: null},
    {key: 'resume', label: 'Resume', recommended: true, enabled: true, reason: null},
    {key: 'retry_failed_only', label: 'Retry failed only', recommended: false, enabled: true, reason: null},
    {key: 'render_dry_run', label: 'Render dry run', recommended: false, enabled: true, reason: null},
    {key: 'run_range', label: 'Run stage range', recommended: false, enabled: true, reason: null}
  ]
};

function primeMocks() {
  mockApi.getToken.mockReturnValue('token-1');
  mockApi.me.mockResolvedValue(authPayload);
  mockApi.login.mockResolvedValue(authPayload);
  mockApi.logout.mockResolvedValue({ok: true});
  mockApi.getWorkspaceSummary.mockResolvedValue({total_projects: 1, full_support_projects: 1, limited_support_projects: 0, active_runs: 0, awaiting_review_projects: 1, ready_for_render_projects: 0, blocked_projects: 0, workspace_root: 'C:\\YT_visual'});
  mockApi.listProjects.mockResolvedValue([project]);
  mockApi.createProject.mockResolvedValue({project_id: 'demo-project'});
  mockApi.getProject.mockResolvedValue(project);
  mockApi.getOverview.mockResolvedValue(overview);
  mockApi.getPipelineState.mockResolvedValue(pipelineState);
  mockApi.getAssets.mockResolvedValue({project_id: 'demo-project', total_count: 0, groups: []});
  mockApi.getTimeline.mockResolvedValue({rows: []});
  mockApi.getReviewQueue.mockResolvedValue({project_id: 'demo-project', source: 'review.csv', items: [], decisions: [], summary: {manual_review: 0, regenerate: 0}});
  mockApi.listRuns.mockResolvedValue([]);
  mockApi.getRun.mockResolvedValue(null);
  mockApi.getRunLogs.mockResolvedValue({lines: []});
  mockApi.getProjectRuns.mockResolvedValue([]);
  mockApi.preview.mockResolvedValue({preview_kind: 'text', content: 'demo'});
  mockApi.mediaUrl.mockReturnValue('/demo.mp4');
  mockApi.pipelineAction.mockResolvedValue({accepted: true, run_id: 'run-1', state: 'queued', message: 'Run accepted.'});
  mockApi.applyReview.mockResolvedValue({accepted: true, run_id: 'run-2', state: 'queued', message: 'Review run accepted.'});
  mockApi.saveReviewDecision.mockResolvedValue({id: 1, item_id: 'B0001', decision: 'approved'});
  mockApi.getSettings.mockResolvedValue([{category: 'environment', key: 'environment', value: {default_profile: 'no_vlm_production'}}]);
  mockApi.updateSettings.mockResolvedValue({category: 'operator_preferences', key: 'studio_preferences', value: {default_concurrency: 10}});
}

beforeEach(() => {
  window.localStorage.clear();
  Object.values(mockApi).forEach((fn) => fn.mockReset());
  primeMocks();
});

test('renders production shell and overview for authenticated user', async () => {
  render(
    <MemoryRouter initialEntries={['/projects/demo-project/overview']}>
      <App />
    </MemoryRouter>
  );

  expect(await screen.findByText('yt_nonstop')).toBeInTheDocument();
  expect(await screen.findByText('Recommended Next Command')).toBeInTheDocument();
  expect((await screen.findAllByText((content) => content.includes('yt-nonstop run --resume'))).length).toBeGreaterThan(0);
});

test('shows login screen and signs in', async () => {
  mockApi.getToken.mockReturnValue('');
  const user = userEvent.setup();
  render(
    <MemoryRouter initialEntries={['/login']}>
      <App />
    </MemoryRouter>
  );

  expect(await screen.findByRole('heading', {name: /sign in to yt_nonstop/i})).toBeInTheDocument();
  await user.type(screen.getByLabelText(/password/i), 'operator');
  await user.click(screen.getByRole('button', {name: /sign in/i}));

  await waitFor(() => {
    expect(mockApi.login).toHaveBeenCalledWith({username: 'operator', password: 'operator'});
  });
});

test('pipeline quick action calls product api action endpoint', async () => {
  const user = userEvent.setup();
  render(
    <MemoryRouter initialEntries={['/projects/demo-project/pipeline']}>
      <App />
    </MemoryRouter>
  );

  const validateButtons = await screen.findAllByRole('button', {name: /validate/i});
  await user.click(validateButtons[0]);

  await waitFor(() => {
    expect(mockApi.pipelineAction).toHaveBeenCalledWith('demo-project', expect.objectContaining({action: 'validate'}));
  });
});
