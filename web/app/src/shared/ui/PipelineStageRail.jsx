const FALLBACK_STAGES = [
  {key: 'upload', label: 'Upload', status: 'done'},
  {key: 'transcribe', label: 'Transcribe', status: 'pending'},
  {key: 'clean_srt', label: 'Clean SRT', status: 'pending'},
  {key: 'scene_plan', label: 'Scene Plan', status: 'pending'},
  {key: 'prompts', label: 'Prompts', status: 'pending'},
  {key: 'images', label: 'Images', status: 'pending'},
  {key: 'qc', label: 'QC', status: 'pending'},
  {key: 'render', label: 'Render', status: 'pending'},
  {key: 'done', label: 'Done', status: 'pending'}
];

function fallbackStages(pipelineState) {
  if (!pipelineState) return FALLBACK_STAGES;
  const current = pipelineState.current_stage || pipelineState.next_stage || 'transcribe';
  const map = {
    transcription: 'transcribe',
    cleanup_transcript_from_source: 'clean_srt',
    ingest_srt: 'clean_srt',
    build_scene_map: 'scene_plan',
    allocate_frames: 'scene_plan',
    build_narration_beats: 'scene_plan',
    build_visual_shot_plan: 'scene_plan',
    build_frame_briefs: 'prompts',
    generate_fastgen_prompt_drafts: 'prompts',
    generation_lock: 'prompts',
    export_generation_batches: 'prompts',
    generate_images: 'images',
    normalize_images: 'images',
    image_qc: 'qc',
    final_review: 'qc',
    timeline: 'render',
    render: 'render',
    done: 'done'
  };
  const activeKey = map[current] || current;
  const activeIndex = FALLBACK_STAGES.findIndex((stage) => stage.key === activeKey);
  const failed = pipelineState.lifecycle_status === 'failed' || pipelineState.recent_runs?.[0]?.status === 'failed';
  const blocked = pipelineState.lifecycle_status === 'blocked' || Number(pipelineState.blocked_count || 0) > 0;
  const running = Boolean(pipelineState.active_run?.run_id);
  return FALLBACK_STAGES.map((stage, index) => {
    if (pipelineState.completed) return {...stage, status: 'done'};
    if (index < activeIndex) return {...stage, status: 'done'};
    if (index === activeIndex && running) return {...stage, status: 'running'};
    if (index === activeIndex && failed) return {...stage, status: 'failed', error_message: pipelineState.blocked?.[0]};
    if (index === activeIndex && blocked) return {...stage, status: 'blocked', error_message: pipelineState.blocked?.[0]};
    return stage;
  });
}

function statusLabel(status) {
  const labels = {
    pending: 'Pending',
    running: 'Running',
    done: 'Done',
    warning: 'Warning',
    failed: 'Failed',
    blocked: 'Blocked'
  };
  return labels[status] || 'Pending';
}

export function PipelineStageRail({pipelineState, compact = false}) {
  if (!pipelineState) return null;
  const stages = pipelineState.stage_groups?.length ? pipelineState.stage_groups : fallbackStages(pipelineState);
  const progress = pipelineState.progress || {};
  const currentLabel = progress.current_stage_label || pipelineState.current_activity?.title || pipelineState.current_stage || 'Waiting';
  const isFailed = Boolean(progress.is_failed);
  const isRunning = Boolean(progress.is_running || pipelineState.active_run?.run_id);
  const caption = isRunning
    ? 'Green pulse means the pipeline is actively moving.'
    : isFailed
      ? 'Red means the last run stopped here. Open logs for the exact error.'
      : 'Gray means waiting for the next run.';

  return (
    <section className={`stage-rail ${compact ? 'stage-rail-compact' : ''}`} aria-label="Pipeline stage progress">
      <div className="stage-rail-head">
        <div>
          <strong>Pipeline progress</strong>
          <span>{currentLabel} {Number.isFinite(progress.percent) ? `- ${progress.percent}%` : ''}</span>
        </div>
        <small>{caption}</small>
      </div>
      <div className="stage-progress-line" aria-hidden="true">
        <span style={{width: `${Math.max(0, Math.min(100, Number(progress.percent || 0)))}%`}} />
      </div>
      <div className="stage-track">
        {stages.map((stage, index) => (
          <div className={`stage-node stage-${stage.status || 'pending'}`} key={stage.key} title={`${stage.label}: ${stage.message || stage.error_message || statusLabel(stage.status)}`}>
            <span className="stage-number">{stage.status === 'done' ? 'OK' : index + 1}</span>
            <span className="stage-label">{stage.label}</span>
            <span className="stage-state">{statusLabel(stage.status)}</span>
            {stage.output_label ? <span className="stage-output">{stage.output_label}</span> : null}
          </div>
        ))}
      </div>
    </section>
  );
}
