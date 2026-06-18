import {useEffect, useState} from 'react';
import {useNavigate} from 'react-router-dom';
import {Badge} from '../../shared/ui/Badge.jsx';
import {ListBlock} from '../../shared/ui/ListBlock.jsx';
import {PipelineStageRail} from '../../shared/ui/PipelineStageRail.jsx';
import {RunMonitorCard} from '../../shared/ui/RunMonitorCard.jsx';
import {SectionTitle} from '../../shared/ui/SectionTitle.jsx';
import {FileInputCard} from '../../shared/ui/FileInputCard.jsx';
import {PageHeader} from '../../shared/ui/PageHeader.jsx';
import {RecoveryPanel} from '../../shared/ui/RecoveryPanel.jsx';
import {useProjectStore, useSettingsStore, useStudioShell} from '../../state/StudioProvider.jsx';

const intakeSteps = [
  'Upload source audio, narration text, and optional creative brief.',
  'Studio creates a clean project folder in YT_visual.',
  'Studio runs audio range -> Whisper Base -> cleaned SRT -> prompts -> images -> render.'
];

const emptyPreviewState = {
  stage_groups: [
    {key: 'upload', label: 'Upload', status: 'pending'},
    {key: 'transcribe', label: 'Transcribe', status: 'pending'},
    {key: 'clean_srt', label: 'Clean SRT', status: 'pending'},
    {key: 'scene_plan', label: 'Scene Plan', status: 'pending'},
    {key: 'prompts', label: 'Prompts', status: 'pending'},
    {key: 'images', label: 'Images', status: 'pending'},
    {key: 'qc', label: 'QC', status: 'pending'},
    {key: 'render', label: 'Render', status: 'pending'},
    {key: 'done', label: 'Done', status: 'pending'}
  ],
  progress: {percent: 0, current_stage_label: 'Ready to start'}
};

export function SetupPage() {
  const navigate = useNavigate();
  const {createProject, intakeProject, intakeAudioTextProject} = useSettingsStore();
  const {busyAction, runPipelineAction} = useStudioShell();
  const {pipelineState, refreshProject} = useProjectStore();
  const [mode, setMode] = useState('audio_text');
  const [result, setResult] = useState(null);
  const [validationError, setValidationError] = useState('');
  const [files, setFiles] = useState({
    source_srt: null,
    source_audio: null,
    raw_text: null,
    setup_notes: null
  });
  const [form, setForm] = useState({
    project_name: '',
    source_srt_path: '',
    source_audio_path: '',
    raw_text_path: '',
    setup_notes_path: '',
    profile: 'no_vlm_production',
    timing_mode: 'full',
    range_start_min: '',
    range_start_sec: '',
    range_end_min: '',
    range_end_sec: ''
  });

  const setField = (key, value) => setForm((current) => ({...current, [key]: value}));
  const setFile = (key, value) => setFiles((current) => ({...current, [key]: value}));

  useEffect(() => {
    if (!result?.project_id) return undefined;
    refreshProject(result.project_id);
    const timer = window.setInterval(() => refreshProject(result.project_id), 2500);
    return () => window.clearInterval(timer);
  }, [result?.project_id]);

  const secondsFromFields = (minutes, seconds) => {
    const min = Number(minutes || 0);
    const sec = Number(seconds || 0);
    if (!Number.isFinite(min) || !Number.isFinite(sec)) return NaN;
    return min * 60 + sec;
  };

  const selectedTimingRange = () => {
    if (form.timing_mode !== 'custom') return null;
    return {
      start: secondsFromFields(form.range_start_min, form.range_start_sec),
      end: secondsFromFields(form.range_end_min, form.range_end_sec)
    };
  };

  const validateTimingRange = () => {
    const range = selectedTimingRange();
    if (!range) return '';
    if (!Number.isFinite(range.start) || !Number.isFinite(range.end)) return 'Timing range must use numbers only.';
    if (range.start < 0 || range.end < 0) return 'Timing range cannot be negative.';
    if (range.end <= range.start) return 'End time must be greater than start time.';
    return '';
  };

  const validateUploadMode = () => {
    if (!form.project_name.trim()) return 'Project name is required.';
    if (!files.source_audio) return 'Source audio file is required.';
    if (!files.raw_text) return 'Raw text file is required.';
    if (form.timing_mode === 'custom') return validateTimingRange();
    return '';
  };

  const validateSrtUploadMode = () => {
    const uploadError = validateUploadMode();
    if (uploadError) return uploadError;
    if (!files.source_srt) return 'Source SRT file is required.';
    return '';
  };

  const validatePathMode = () => {
    const requiredFields = [
      ['project_name', 'Project name'],
      ['source_srt_path', 'Source SRT path'],
      ['source_audio_path', 'Source audio path'],
      ['raw_text_path', 'Raw text path']
    ];
    const missing = requiredFields.find(([key]) => !String(form[key] || '').trim());
    return missing ? `${missing[1]} is required.` : '';
  };

  const submitAudioTextUploads = async () => {
    const body = new FormData();
    body.append('project_name', form.project_name);
    body.append('profile', form.profile || 'no_vlm_production');
    body.append('to_stage', 'render');
    body.append('real_generation', 'true');
    body.append('concurrency', '4');
    const range = selectedTimingRange();
    if (range) {
      body.append('start_sec', String(range.start));
      body.append('end_sec', String(range.end));
    }
    body.append('source_audio', files.source_audio);
    body.append('raw_text', files.raw_text);
    if (files.setup_notes) {
      body.append('style_notes', files.setup_notes);
    }
    return intakeAudioTextProject(body);
  };

  const submitSrtUploads = async () => {
    const body = new FormData();
    body.append('project_name', form.project_name);
    body.append('profile', form.profile || 'no_vlm_production');
    body.append('source_srt', files.source_srt);
    body.append('source_audio', files.source_audio);
    body.append('raw_text', files.raw_text);
    if (files.setup_notes) {
      body.append('setup_notes', files.setup_notes);
    }
    return intakeProject(body);
  };

  const onSubmit = async (event) => {
    event.preventDefault();
    const error = mode === 'audio_text' ? validateUploadMode() : mode === 'srt_upload' ? validateSrtUploadMode() : validatePathMode();
    if (error) {
      setValidationError(error);
      return;
    }
    setValidationError('');
    const payload = mode === 'audio_text' ? await submitAudioTextUploads() : mode === 'srt_upload' ? await submitSrtUploads() : await createProject(form);
    setResult(payload);
    if (mode !== 'audio_text') {
      navigate(payload.next_route || `/projects/${payload.project_id}/overview`);
    }
  };

  return (
    <section className="stack wide-gap">
      <PageHeader
        eyebrow="Launch pipeline"
        title="Create a new video project"
        description="Upload sources, choose an optional range, and keep the live monitor visible from the first second."
        meta={mode === 'audio_text' ? 'Audio + script' : mode === 'srt_upload' ? 'Advanced SRT timing' : 'Local paths'}
      />
      <div className="new-project-layout">
      <div className="panel launch-form-panel">
        <SectionTitle title="1. Source package" meta={mode === 'audio_text' ? 'default' : 'advanced'} />
        <div className="mode-switch">
          <button type="button" className={mode === 'audio_text' ? 'active' : ''} onClick={() => setMode('audio_text')}>Upload audio + script</button>
          <button type="button" className={mode === 'srt_upload' ? 'active' : ''} onClick={() => setMode('srt_upload')}>Advanced: I already have SRT timing</button>
          <button type="button" className={mode === 'paths' ? 'active' : ''} onClick={() => setMode('paths')}>Use local paths</button>
        </div>
        <form className="stack compact" onSubmit={onSubmit}>
          <label><span>Project name</span><input value={form.project_name} onChange={(event) => setField('project_name', event.target.value)} placeholder="illyuziya_vybora" /></label>
          <label><span>Profile</span><input value={form.profile} onChange={(event) => setField('profile', event.target.value)} /></label>

          {mode === 'audio_text' ? (
            <div className="stack compact">
              <FileInputCard label="Source audio" file={files.source_audio} accept="audio/*,.mp3,.wav,.m4a" helper="MP3, WAV, M4A" onChange={(file) => setFile('source_audio', file)} />
              <FileInputCard label="Raw narration text" file={files.raw_text} accept=".txt,.md,text/plain" helper="TXT or Markdown script" onChange={(file) => setFile('raw_text', file)} />
              <FileInputCard label="Creative brief" file={files.setup_notes} accept=".txt,.md,text/plain" optional helper="Optional style notes or references" onChange={(file) => setFile('setup_notes', file)} />
              <TimingRangePicker form={form} setField={setField} />
              <p className="muted">Default flow: audio range, Whisper Base SRT, cleaned timing against the script, scene plan, prompts, images, QC, render.</p>
            </div>
          ) : mode === 'srt_upload' ? (
            <div className="stack compact">
              <FileInputCard label="Source SRT" file={files.source_srt} accept=".srt,text/plain" onChange={(file) => setFile('source_srt', file)} />
              <FileInputCard label="Source audio" file={files.source_audio} accept="audio/*,.mp3,.wav,.m4a" onChange={(file) => setFile('source_audio', file)} />
              <FileInputCard label="Raw narration text" file={files.raw_text} accept=".txt,.md,text/plain" onChange={(file) => setFile('raw_text', file)} />
              <FileInputCard label="Creative brief" file={files.setup_notes} accept=".txt,.md,text/plain" optional onChange={(file) => setFile('setup_notes', file)} />
            </div>
          ) : (
            <div className="stack compact">
              <label><span>Source SRT path</span><input value={form.source_srt_path} onChange={(event) => setField('source_srt_path', event.target.value)} placeholder="C:\\..." /></label>
              <label><span>Source audio path</span><input value={form.source_audio_path} onChange={(event) => setField('source_audio_path', event.target.value)} placeholder="C:\\..." /></label>
              <label><span>Raw text path</span><input value={form.raw_text_path} onChange={(event) => setField('raw_text_path', event.target.value)} placeholder="C:\\..." /></label>
              <label><span>Setup notes path</span><input value={form.setup_notes_path} onChange={(event) => setField('setup_notes_path', event.target.value)} placeholder="Optional" /></label>
            </div>
          )}

          {validationError ? <p className="error-inline">{validationError}</p> : null}
          <div className="action-row">
            <button type="submit" disabled={busyAction === 'intake_audio_text_project' || busyAction === 'intake_project' || busyAction === 'create_project'}>
              {busyAction ? 'Creating...' : mode === 'audio_text' ? 'Create project and start pipeline' : 'Create project and open overview'}
            </button>
          </div>
        </form>
      </div>
      <div className="panel sticky-panel launch-monitor-panel">
        <SectionTitle title={result ? 'Live Run Monitor' : '2. Pipeline preview'} />
        {result ? (
          <LaunchMonitor result={result} pipelineState={pipelineState} busyAction={busyAction} onRun={runPipelineAction} onOpen={(route) => navigate(route)} />
        ) : (
          <div className="stack compact">
            <PipelineStageRail pipelineState={emptyPreviewState} compact />
            {intakeSteps.map((item, index) => (
              <div className="setup-step" key={item}>
                <Badge tone="accent">{index + 1}</Badge>
                <span>{item}</span>
              </div>
            ))}
            <p className="muted">After launch, this panel becomes the live monitor. You can stay here and watch the pipeline move stage by stage.</p>
          </div>
        )}
        {result ? (
          <dl className="details">
            <div><dt>Project ID</dt><dd>{result.project_id}</dd></div>
            <div><dt>Root</dt><dd>{result.project_root}</dd></div>
            <div><dt>project.json</dt><dd>{result.project_json_path}</dd></div>
          </dl>
        ) : null}
      </div>
      </div>
    </section>
  );
}

function LaunchMonitor({result, pipelineState, busyAction, onRun, onOpen}) {
  const active = Boolean(pipelineState?.active_run?.run_id);
  const failed = pipelineState?.lifecycle_status === 'failed' || pipelineState?.recent_runs?.[0]?.status === 'failed';
  const tone = active ? 'success' : failed ? 'warn' : 'accent';
  const statusText = active ? 'Pipeline is running' : failed ? 'Pipeline stopped' : 'Waiting for next stage';
  return (
    <div className="launch-monitor">
      <div className={`launch-status launch-${tone}`}>
        <div>
          <strong>{statusText}</strong>
          <span>{pipelineState?.progress?.current_stage_label || pipelineState?.current_stage || 'starting'} to {pipelineState?.next_stage || 'render'}</span>
        </div>
        <Badge tone={tone}>{active ? 'live' : failed ? 'needs action' : 'watching'}</Badge>
      </div>
      <PipelineStageRail pipelineState={pipelineState} compact />
      <RunMonitorCard pipelineState={pipelineState} title="Worker status" showLogs={false} />
      <RecoveryPanel pipelineState={pipelineState} busyAction={busyAction} onRun={onRun} compact />
      <ListBlock title="Problems" rows={pipelineState?.blocked || []} empty="No blockers yet. Green means the process is moving." tone="warn" />
      <ListBlock title="Warnings" rows={pipelineState?.warnings || []} empty="No warnings yet." tone="accent" />
      <div className="action-row">
        <button type="button" onClick={() => onOpen(`/projects/${result.project_id}/pipeline`)}>Open Pipeline</button>
        <button type="button" className="ghost-button" onClick={() => onOpen(`/projects/${result.project_id}/overview`)}>Open Overview</button>
      </div>
    </div>
  );
}

function TimingRangePicker({form, setField}) {
  const custom = form.timing_mode === 'custom';
  return (
    <fieldset className="timing-range">
      <legend>Timing range</legend>
      <div className="mode-switch compact-switch">
        <button type="button" className={!custom ? 'active' : ''} onClick={() => setField('timing_mode', 'full')}>Entire video</button>
        <button type="button" className={custom ? 'active' : ''} onClick={() => setField('timing_mode', 'custom')}>Custom range</button>
      </div>
      {custom ? (
        <div className="time-grid">
          <label><span>Start min</span><input inputMode="numeric" value={form.range_start_min} onChange={(event) => setField('range_start_min', event.target.value)} placeholder="2" /></label>
          <label><span>Start sec</span><input inputMode="decimal" value={form.range_start_sec} onChange={(event) => setField('range_start_sec', event.target.value)} placeholder="0" /></label>
          <label><span>End min</span><input inputMode="numeric" value={form.range_end_min} onChange={(event) => setField('range_end_min', event.target.value)} placeholder="3" /></label>
          <label><span>End sec</span><input inputMode="decimal" value={form.range_end_sec} onChange={(event) => setField('range_end_sec', event.target.value)} placeholder="0" /></label>
        </div>
      ) : null}
      <p className="muted small">Use this for test renders, for example 2:00 to 3:00. The generated video starts at 0:00 but uses that original audio window.</p>
    </fieldset>
  );
}
