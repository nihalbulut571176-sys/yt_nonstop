import {Navigate, Route, Routes} from 'react-router-dom';
import {AppLayout} from './app-shell/AppLayout.jsx';
import {AssetsPage} from './domains/assets/AssetsPage.jsx';
import {LoginPage} from './domains/auth/LoginPage.jsx';
import {OverviewPage} from './domains/overview/OverviewPage.jsx';
import {PipelinePage} from './domains/pipeline/PipelinePage.jsx';
import {ProjectsPage} from './domains/projects/ProjectsPage.jsx';
import {SetupPage} from './domains/projects/SetupPage.jsx';
import {ReviewPage} from './domains/review/ReviewPage.jsx';
import {RunsPage} from './domains/runs/RunsPage.jsx';
import {SettingsPage} from './domains/settings/SettingsPage.jsx';
import {StudioProvider, useAuthStore, useWorkspaceStore} from './state/StudioProvider.jsx';

function LegacyRedirect({screen}) {
  const {selectedProjectId, projects} = useWorkspaceStore();
  const fallback = selectedProjectId || projects[0]?.id;
  if (!fallback) {
    return <Navigate to="/projects" replace />;
  }
  return <Navigate to={`/projects/${fallback}/${screen}`} replace />;
}

function AppRoutes() {
  const {session, authReady} = useAuthStore();

  if (!authReady) {
    return <div className="auth-shell"><div className="auth-card"><p>Loading studio session...</p></div></div>;
  }

  if (!session) {
    return <LoginPage />;
  }

  return (
    <Routes>
      <Route path="/" element={<Navigate to="/projects" replace />} />
      <Route path="/login" element={<Navigate to="/projects" replace />} />
      <Route element={<AppLayout />}>
        <Route path="/projects" element={<ProjectsPage />} />
        <Route path="/projects/new" element={<SetupPage />} />
        <Route path="/projects/:projectId/overview" element={<OverviewPage />} />
        <Route path="/projects/:projectId/pipeline" element={<PipelinePage />} />
        <Route path="/projects/:projectId/review" element={<ReviewPage />} />
        <Route path="/projects/:projectId/assets" element={<AssetsPage />} />
        <Route path="/projects/:projectId/runs" element={<RunsPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="/overview" element={<LegacyRedirect screen="overview" />} />
        <Route path="/pipeline" element={<LegacyRedirect screen="pipeline" />} />
        <Route path="/review" element={<LegacyRedirect screen="review" />} />
        <Route path="/assets" element={<LegacyRedirect screen="assets" />} />
        <Route path="/runs" element={<LegacyRedirect screen="runs" />} />
        <Route path="/setup" element={<Navigate to="/projects/new" replace />} />
      </Route>
    </Routes>
  );
}

export default function App() {
  return (
    <StudioProvider>
      <AppRoutes />
    </StudioProvider>
  );
}
