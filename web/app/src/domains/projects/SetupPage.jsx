import {useNavigate} from 'react-router-dom';
import {useState} from 'react';
import {Badge} from '../../shared/ui/Badge.jsx';
import {SectionTitle} from '../../shared/ui/SectionTitle.jsx';
import {useSettingsStore, useStudioShell} from '../../state/StudioProvider.jsx';

const intakeSteps = [
  'Add source SRT, audio, and narration text.',
  'Studio creates a clean project folder in YT_visual.',
  'Open Overview, then run Validate or Resume from Pipeline.'
];

export function SetupPage() {
  const navigate = useNavigate();
  const {createProject, intakeProject} = useSettingsStore();
  const {busyAction} = useStudioShell();
  const [mode, setMode] = useState('upload');
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
    profile: 'no_vlm_production'
  });

  const setField = (key, value) => setForm((current) => ({...current, [key]: value}));
  const setFile = (key, value) => setFiles((current) => ({...current, [key]: value}));

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

  const validateUploadMode = () => {
    if (!form.project_name.trim()) return 'Project name is required.';
    if (!files.source_srt) return 'Source SRT file is required.';
    if (!files.source_audio) return 'Source audio file is required.';
    if (!files.raw_text) return 'Raw text file is required.';
    return '';
  };

  const onSubmit = async (event) => {
    event.preventDefault();
    const error = mode === 'upload' ? validateUploadMode() : validatePathMode();
    if (error) {
      setValidationError(error);
      return;
    }
    setValidationError('');
    const payload = mode === 'upload' ? await submitUploads() : await createProject(form);
    setResult(payload);
    navigate(payload.next_route || `/projects/${payload.project_id}/overview`);
  };

  const submitUploads = async () => {
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

  return (
    <section className="grid-two">
      <div className="panel">
        <SectionTitle title="New Project Intake" meta={mode === 'upload' ? 'Upload files' : 'Local paths'} />
        <div className="mode-switch">
          <button type="button" className={mode === 'upload' ? 'active' : ''} onClick={() => setMode('upload')}>Upload source files</button>
          <button type="button" className={mode === 'paths' ? 'active' : ''} onClick={() => setMode('paths')}>Use local paths</button>
        </div>
        <form className="stack compact" onSubmit={onSubmit}>
          <label><span>Project name</span><input value={form.project_name} onChange={(event) => setField('project_name', event.target.value)} placeholder="illyuziya_vybora" /></label>
          <label><span>Profile</span><input value={form.profile} onChange={(event) => setField('profile', event.target.value)} /></label>

          {mode === 'upload' ? (
            <div className="stack compact">
              <FileInput label="Source SRT" file={files.source_srt} accept=".srt,text/plain" onChange={(file) => setFile('source_srt', file)} />
              <FileInput label="Source audio" file={files.source_audio} accept="audio/*,.mp3,.wav,.m4a" onChange={(file) => setFile('source_audio', file)} />
              <FileInput label="Raw narration text" file={files.raw_text} accept=".txt,.md,text/plain" onChange={(file) => setFile('raw_text', file)} />
              <FileInput label="Style / setup notes" file={files.setup_notes} accept=".txt,.md,text/plain" optional onChange={(file) => setFile('setup_notes', file)} />
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
            <button type="submit" disabled={busyAction === 'intake_project' || busyAction === 'create_project'}>
              {busyAction === 'intake_project' || busyAction === 'create_project' ? 'Creating...' : 'Create project and open overview'}
            </button>
          </div>
        </form>
      </div>
      <div className="panel">
        <SectionTitle title="What Happens Next" />
        <div className="stack compact">
          {intakeSteps.map((item, index) => (
            <div className="setup-step" key={item}>
              <Badge tone="accent">{index + 1}</Badge>
              <span>{item}</span>
            </div>
          ))}
          <p className="muted">For now the repo-native intake requires SRT timing. If you only have MP3 and script text, the next product step is a draft intake that runs transcription before project bootstrap.</p>
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

function FileInput({label, file, accept, optional = false, onChange}) {
  return (
    <label className="file-drop">
      <span>{label}{optional ? ' (optional)' : ''}</span>
      <input type="file" accept={accept} onChange={(event) => onChange(event.target.files?.[0] || null)} />
      <strong>{file?.name || 'Choose file'}</strong>
    </label>
  );
}
