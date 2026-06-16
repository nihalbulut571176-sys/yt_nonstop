import {createContext, useContext, useEffect, useMemo, useState} from 'react';
import {api} from '../api.js';

const StudioContext = createContext(null);

export function StudioProvider({children}) {
  const [session, setSession] = useState(null);
  const [authReady, setAuthReady] = useState(false);
  const [workspace, setWorkspace] = useState(null);
  const [projects, setProjects] = useState([]);
  const [selectedProjectId, setSelectedProjectId] = useState('');
  const [project, setProject] = useState(null);
  const [overview, setOverview] = useState(null);
  const [pipelineState, setPipelineState] = useState(null);
  const [reviewQueue, setReviewQueue] = useState(null);
  const [assets, setAssets] = useState(null);
  const [timeline, setTimeline] = useState({rows: []});
  const [projectRuns, setProjectRuns] = useState([]);
  const [globalRuns, setGlobalRuns] = useState([]);
  const [settings, setSettings] = useState([]);
  const [preview, setPreview] = useState(null);
  const [activeRunDetails, setActiveRunDetails] = useState(null);
  const [busyAction, setBusyAction] = useState('');
  const [error, setError] = useState('');

  const refreshWorkspace = async () => {
    if (!session) return;
    try {
      const [workspacePayload, projectPayload, runPayload, settingPayload] = await Promise.all([
        api.getWorkspaceSummary(),
        api.listProjects(),
        api.listRuns(50),
        api.getSettings()
      ]);
      setWorkspace(workspacePayload);
      setProjects(projectPayload);
      setGlobalRuns(runPayload);
      setSettings(settingPayload);
      if (!selectedProjectId && projectPayload[0]) {
        setSelectedProjectId(projectPayload[0].id);
      } else if (selectedProjectId && !projectPayload.find((item) => item.id === selectedProjectId) && projectPayload[0]) {
        setSelectedProjectId(projectPayload[0].id);
      }
      setError('');
    } catch (err) {
      setError(err.message);
    }
  };

  const refreshProject = async (projectId) => {
    if (!session || !projectId) return;
    try {
      const [projectPayload, overviewPayload, pipelinePayload, reviewPayload, assetPayload, timelinePayload, runPayload] = await Promise.all([
        api.getProject(projectId),
        api.getOverview(projectId),
        api.getPipelineState(projectId),
        api.getReviewQueue(projectId),
        api.getAssets(projectId),
        api.getTimeline(projectId),
        api.getProjectRuns(projectId, 50)
      ]);
      setProject(projectPayload);
      setOverview(overviewPayload);
      setPipelineState(pipelinePayload);
      setReviewQueue(reviewPayload);
      setAssets(assetPayload);
      setTimeline(timelinePayload);
      setProjectRuns(runPayload);
      setPreview(null);
      if (pipelinePayload?.active_run?.run_id) {
        setActiveRunDetails(await api.getRun(pipelinePayload.active_run.run_id));
      } else {
        setActiveRunDetails(null);
      }
      setError('');
    } catch (err) {
      setError(err.message);
    }
  };

  const signIn = async (credentials) => {
    const payload = await api.login(credentials);
    setSession(payload);
    setAuthReady(true);
    setError('');
    return payload;
  };

  const signOut = async () => {
    await api.logout();
    setSession(null);
    setWorkspace(null);
    setProjects([]);
    setSelectedProjectId('');
    setProject(null);
    setOverview(null);
    setPipelineState(null);
    setReviewQueue(null);
    setAssets(null);
    setTimeline({rows: []});
    setProjectRuns([]);
    setGlobalRuns([]);
    setSettings([]);
    setPreview(null);
    setActiveRunDetails(null);
  };

  const runPipelineAction = async (payload) => {
    if (!selectedProjectId) return;
    try {
      setBusyAction(payload.action || 'run');
      await api.pipelineAction(selectedProjectId, payload);
      await Promise.all([refreshWorkspace(), refreshProject(selectedProjectId)]);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusyAction('');
    }
  };

  const applyReview = async (payload) => {
    if (!selectedProjectId) return;
    try {
      setBusyAction('review');
      await api.applyReview(selectedProjectId, payload);
      await Promise.all([refreshWorkspace(), refreshProject(selectedProjectId)]);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusyAction('');
    }
  };

  const saveReviewDecision = async (payload) => {
    if (!selectedProjectId) return;
    try {
      setBusyAction('save_review');
      await api.saveReviewDecision(selectedProjectId, payload);
      await refreshProject(selectedProjectId);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusyAction('');
    }
  };

  const createProject = async (payload) => {
    try {
      setBusyAction('create_project');
      const response = await api.createProject(payload);
      await refreshWorkspace();
      setSelectedProjectId(response.project_id);
      return response;
    } catch (err) {
      setError(err.message);
      throw err;
    } finally {
      setBusyAction('');
    }
  };

  const intakeProject = async (payload) => {
    try {
      setBusyAction('intake_project');
      const response = await api.intakeProject(payload);
      await refreshWorkspace();
      setSelectedProjectId(response.project_id);
      return response;
    } catch (err) {
      setError(err.message);
      throw err;
    } finally {
      setBusyAction('');
    }
  };

  const intakeAudioTextProject = async (payload) => {
    try {
      setBusyAction('intake_audio_text_project');
      const response = await api.intakeAudioTextProject(payload);
      await refreshWorkspace();
      setSelectedProjectId(response.project_id);
      return response;
    } catch (err) {
      setError(err.message);
      throw err;
    } finally {
      setBusyAction('');
    }
  };

  const saveSettings = async (payload) => {
    try {
      setBusyAction('settings');
      await api.updateSettings(payload);
      await refreshWorkspace();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusyAction('');
    }
  };

  useEffect(() => {
    let active = true;
    const resume = async () => {
      if (!api.getToken()) {
        setAuthReady(true);
        return;
      }
      try {
        const payload = await api.me();
        if (active) {
          setSession(payload);
        }
      } catch (_err) {
        if (active) {
          setSession(null);
        }
      } finally {
        if (active) {
          setAuthReady(true);
        }
      }
    };
    resume();
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (!session) return;
    refreshWorkspace();
  }, [session]);

  useEffect(() => {
    refreshProject(selectedProjectId);
  }, [selectedProjectId, session]);

  useEffect(() => {
    if (!session) return undefined;
    const workspaceTimer = window.setInterval(() => {
      refreshWorkspace();
    }, 15000);
    return () => window.clearInterval(workspaceTimer);
  }, [session, selectedProjectId]);

  useEffect(() => {
    if (!session || !selectedProjectId) return undefined;
    const active = Boolean(pipelineState?.active_run?.run_id);
    const interval = active ? 2500 : 7000;
    const projectTimer = window.setInterval(() => {
      refreshProject(selectedProjectId);
    }, interval);
    return () => window.clearInterval(projectTimer);
  }, [session, selectedProjectId, pipelineState?.active_run?.run_id]);

  const value = useMemo(
    () => ({
      session,
      authReady,
      workspace,
      projects,
      selectedProjectId,
      setSelectedProjectId,
      project,
      overview,
      pipelineState,
      reviewQueue,
      assets,
      timeline,
      projectRuns,
      globalRuns,
      settings,
      preview,
      setPreview,
      activeRunDetails,
      busyAction,
      error,
      setError,
      refreshWorkspace,
      refreshProject,
      signIn,
      signOut,
      runPipelineAction,
      applyReview,
      saveReviewDecision,
      createProject,
      intakeProject,
      intakeAudioTextProject,
      saveSettings
    }),
    [
      session,
      authReady,
      workspace,
      projects,
      selectedProjectId,
      project,
      overview,
      pipelineState,
      reviewQueue,
      assets,
      timeline,
      projectRuns,
      globalRuns,
      settings,
      preview,
      activeRunDetails,
      busyAction,
      error
    ]
  );

  return <StudioContext.Provider value={value}>{children}</StudioContext.Provider>;
}

function useStudioContext() {
  const value = useContext(StudioContext);
  if (!value) {
    throw new Error('StudioContext is missing');
  }
  return value;
}

export function useAuthStore() {
  const {session, authReady, signIn, signOut} = useStudioContext();
  return {session, authReady, signIn, signOut};
}

export function useWorkspaceStore() {
  const {workspace, projects, selectedProjectId, setSelectedProjectId, refreshWorkspace} = useStudioContext();
  return {workspace, projects, selectedProjectId, setSelectedProjectId, refreshWorkspace};
}

export function useProjectStore() {
  const {project, overview, pipelineState, assets, timeline, preview, setPreview, refreshProject, selectedProjectId} = useStudioContext();
  return {project, overview, pipelineState, assets, timeline, preview, setPreview, refreshProject, selectedProjectId};
}

export function useRunsStore() {
  const {projectRuns, globalRuns, activeRunDetails} = useStudioContext();
  return {projectRuns, globalRuns, activeRunDetails};
}

export function useReviewStore() {
  const {reviewQueue, saveReviewDecision, applyReview} = useStudioContext();
  return {reviewQueue, saveReviewDecision, applyReview};
}

export function useSettingsStore() {
  const {settings, saveSettings, createProject, intakeProject, intakeAudioTextProject} = useStudioContext();
  return {settings, saveSettings, createProject, intakeProject, intakeAudioTextProject};
}

export function useStudioShell() {
  return useStudioContext();
}
