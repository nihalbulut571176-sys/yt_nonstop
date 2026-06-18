import {useState} from 'react';
import {Badge} from './Badge.jsx';
import {SectionTitle} from './SectionTitle.jsx';

const restartStages = [
  {label: 'Transcribe', value: 'transcription'},
  {label: 'Clean SRT', value: 'cleanup_transcript_from_source'},
  {label: 'Scene Plan', value: 'build_scene_map'},
  {label: 'Prompts', value: 'build_frame_briefs'},
  {label: 'Images', value: 'generate_images'},
  {label: 'QC', value: 'image_qc'},
  {label: 'Render', value: 'timeline'}
];

function findAction(pipelineState, key) {
  return (pipelineState?.recovery_actions || []).find((item) => item.key === key) || {key, enabled: false, reason: 'Action is not available yet.'};
}

export function RecoveryPanel({pipelineState, busyAction, onRun, compact = false}) {
  const [restartFrom, setRestartFrom] = useState(pipelineState?.resume_from_stage || 'transcription');
  if (!pipelineState) return null;

  const failed = Boolean(pipelineState.failed_run_id || pipelineState.progress?.is_failed);
  const continueAction = findAction(pipelineState, 'continue_from_last_success');
  const retryStepAction = findAction(pipelineState, 'retry_failed_step');
  const retryImagesAction = findAction(pipelineState, 'retry_failed_only');
  const restartAction = findAction(pipelineState, 'restart_from_stage');

  const run = (payload) => onRun?.({...payload, to_stage: payload.to_stage || pipelineState.resume_to_stage || 'render'});

  return (
    <section className={`recovery-panel ${failed ? 'recovery-failed' : ''} ${compact ? 'recovery-compact' : ''}`}>
      <SectionTitle
        title="Recovery controls"
        meta={failed ? <Badge tone="warn">failed</Badge> : <Badge tone="success">safe resume</Badge>}
      />
      <div className="recovery-copy">
        <strong>{failed ? `Stopped at ${pipelineState.failed_stage_label || pipelineState.progress?.current_stage_label || 'pipeline step'}` : 'Project can continue safely'}</strong>
        <p>{pipelineState.failed_error_summary || 'Studio will reuse completed artifacts and continue with --resume. Nothing is deleted automatically.'}</p>
      </div>
      <div className="recovery-actions">
        <button
          type="button"
          disabled={!continueAction.enabled || busyAction === 'continue_from_last_success'}
          onClick={() => run({action: 'continue_from_last_success'})}
        >
          Continue pipeline
        </button>
        <button
          type="button"
          disabled={!retryStepAction.enabled || busyAction === 'retry_failed_step'}
          onClick={() => run({action: 'retry_failed_step'})}
        >
          Retry from {pipelineState.failed_stage_label || 'failed step'}
        </button>
        <button
          type="button"
          className="ghost-button"
          disabled={!retryImagesAction.enabled || busyAction === 'retry_failed_only'}
          onClick={() => run({action: 'retry_failed_only'})}
        >
          Retry failed images only
        </button>
      </div>
      <div className="restart-row">
        <label>
          <span>Restart from selected stage</span>
          <select value={restartFrom} onChange={(event) => setRestartFrom(event.target.value)}>
            {restartStages.map((stage) => <option key={stage.value} value={stage.value}>{stage.label}</option>)}
          </select>
        </label>
        <button
          type="button"
          className="ghost-button"
          disabled={!restartAction.enabled || busyAction === 'restart_from_stage'}
          onClick={() => run({action: 'restart_from_stage', from_stage: restartFrom})}
        >
          Restart from stage
        </button>
      </div>
      <div className="recovery-hints">
        {[continueAction, retryStepAction, retryImagesAction, restartAction].filter((item) => item.reason).map((item) => (
          <small key={item.key}>{item.label}: {item.reason}</small>
        ))}
      </div>
    </section>
  );
}
