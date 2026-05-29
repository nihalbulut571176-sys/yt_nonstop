from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from project_pipeline_utils import load_json, load_project, save_json, save_project


GENERIC_REASON_MARKERS = {
    "authored visual allocation slot.",
    "visual slot",
    "show spoken idea",
    "supports narration",
    "illustrates narration",
    "visual support",
    "documentary shot",
    "generic reason",
}
ABSTRACT_MARKERS = {
    "tension",
    "mystery",
    "danger",
    "truth",
    "corruption",
    "fear",
    "pressure",
    "investigation",
    "concept",
    "idea",
    "emotion",
    "abstract",
}
WEAK_MUST_SHOW_MARKERS = {
    "something happens",
    "documentary scene",
    "evidence",
    "proof",
    "visual metaphor",
    "mood",
    "atmosphere",
}
NON_GENERATIVE_DECISIONS = {"hold_previous", "continuation_motion"}


def iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def clean_text(value: Any) -> str:
    return " ".join(str(value or "").replace("\n", " ").split()).strip()


def load_payload(path_str: str | None, default: Any) -> Any:
    if not path_str:
        return default
    path = Path(path_str)
    if not path.exists():
        return default
    return load_json(path)


def as_rows(payload: Any, key: str) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        rows = payload.get(key, [])
    else:
        rows = payload
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def as_counter(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for row in rows:
        value = clean_text(row.get(key)).lower() or "unknown"
        counter[value] += 1
    return dict(sorted(counter.items()))


def is_abstract_phrase(text: str) -> bool:
    cleaned = clean_text(text).lower()
    if not cleaned:
        return True
    if cleaned in ABSTRACT_MARKERS or cleaned in WEAK_MUST_SHOW_MARKERS:
        return True
    words = [word for word in cleaned.replace("/", " ").replace("-", " ").split() if word]
    if len(words) <= 2 and any(word in ABSTRACT_MARKERS for word in words):
        return True
    marker_hits = sum(1 for marker in ABSTRACT_MARKERS if marker in cleaned)
    return marker_hits >= 2


def is_weak_must_show(text: str) -> bool:
    cleaned = clean_text(text).lower()
    if not cleaned:
        return True
    if cleaned in WEAK_MUST_SHOW_MARKERS:
        return True
    words = [word for word in cleaned.replace("/", " ").replace("-", " ").split() if word]
    if len(words) < 3:
        return True
    if is_abstract_phrase(cleaned):
        return True
    return any(marker in cleaned for marker in WEAK_MUST_SHOW_MARKERS)


def is_generic_reason(text: str) -> bool:
    cleaned = clean_text(text).lower()
    if not cleaned:
        return True
    if cleaned in GENERIC_REASON_MARKERS:
        return True
    words = [word for word in cleaned.split() if word]
    if len(words) < 4:
        return True
    return "narration" in cleaned and ("support" in cleaned or "illustrate" in cleaned)


def cadence_policy(project: dict[str, Any]) -> dict[str, float]:
    raw = project.get("planning", {}).get("visual_cadence_policy", {}) or {}
    return {
        "min_slot_duration_sec": float(raw.get("min_slot_duration_sec", 1.2) or 1.2),
        "target_slot_duration_sec": float(raw.get("target_slot_duration_sec", 3.2) or 3.2),
        "max_slot_duration_sec": float(raw.get("max_slot_duration_sec", 5.5) or 5.5),
        "max_static_hold_sec": float(raw.get("max_static_hold_sec", 6.5) or 6.5),
    }


def build_slot_records(project: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    allocation = load_payload(project.get("planning", {}).get("visual_allocation_plan_path"), {})
    shot_plan = load_payload(project.get("prompts", {}).get("visual_shot_plan_path"), {})
    frame_briefs = load_payload(project.get("planning", {}).get("frame_briefs_json_path"), [])
    narration = load_payload(project.get("planning", {}).get("narration_beats_path"), {})

    raw_slots = as_rows(allocation, "visual_slots")
    shots = {clean_text(row.get("visual_slot_id")): row for row in as_rows(shot_plan, "shots") if clean_text(row.get("visual_slot_id"))}
    mappings = shot_plan.get("visual_slot_to_shot", {}) if isinstance(shot_plan, dict) else {}
    briefs = {clean_text(row.get("visual_slot_id") or row.get("scene_id")): row for row in frame_briefs if isinstance(row, dict)}
    beats = {clean_text(row.get("beat_id")): row for row in as_rows(narration, "beats") if clean_text(row.get("beat_id"))}

    slots: list[dict[str, Any]] = []
    for index, slot in enumerate(raw_slots, start=1):
        slot_id = clean_text(slot.get("visual_slot_id") or f"VS{index:04d}")
        shot = shots.get(slot_id, {})
        mapping = mappings.get(slot_id, {}) if isinstance(mappings, dict) else {}
        brief = briefs.get(slot_id, {})
        beat_ids = [clean_text(item) for item in slot.get("beat_ids", []) if clean_text(item)]
        duration = float(slot.get("duration", 0) or (float(slot.get("end", 0) or 0) - float(slot.get("start", 0) or 0)) or 0)
        must_show = [clean_text(item) for item in (slot.get("must_show") or brief.get("must_show") or shot.get("must_show") or []) if clean_text(item)]
        reason = clean_text(slot.get("reason") or mapping.get("variation_note") or "")
        slots.append(
            {
                "visual_slot_id": slot_id,
                "beat_ids": beat_ids,
                "duration": round(duration, 4),
                "slot_type": clean_text(slot.get("slot_type") or shot.get("slot_type") or brief.get("slot_type") or "unknown").lower(),
                "generation_decision": clean_text(slot.get("generation_decision") or shot.get("generation_decision") or brief.get("generation_decision") or "unknown").lower(),
                "must_show": must_show,
                "reason": reason,
                "source_visual_slot_id": clean_text(slot.get("source_visual_slot_id") or shot.get("source_visual_slot_id") or mapping.get("source_shot_id") or brief.get("source_shot_id")),
                "film_block_id": clean_text(slot.get("film_block_id") or shot.get("film_block_id") or brief.get("film_block_id")),
                "key_beat": bool(brief.get("key_beat") or shot.get("importance") == "hero" or any(clean_text(beats.get(beat_id, {}).get("visual_priority")).lower() == "high" for beat_id in beat_ids)),
                "shot_type": clean_text(brief.get("shot_type") or shot.get("shot_type") or slot.get("shot_design")),
                "start": float(slot.get("start", 0) or 0),
                "end": float(slot.get("end", 0) or 0),
            }
        )
    return sorted(slots, key=lambda row: (float(row.get("start", 0) or 0), row["visual_slot_id"])), beats


def repeated_streaks(values: list[str], *, min_length: int) -> list[dict[str, Any]]:
    streaks: list[dict[str, Any]] = []
    if not values:
        return streaks
    start = 0
    current = values[0]
    for index in range(1, len(values) + 1):
        next_value = values[index] if index < len(values) else None
        if next_value == current:
            continue
        length = index - start
        if current and length >= min_length:
            streaks.append({"value": current, "start_index": start + 1, "end_index": index, "length": length})
        if index < len(values):
            current = values[index]
            start = index
    return streaks


def same_setup_streaks(slots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    streaks: list[dict[str, Any]] = []
    current: list[dict[str, Any]] = []
    for slot in slots:
        decision = slot["generation_decision"]
        same_setup = decision in {"new_angle_same_setup", "hold_previous", "continuation_motion"} or bool(slot.get("source_visual_slot_id"))
        if same_setup:
            current.append(slot)
            continue
        if len(current) >= 2:
            streaks.append(
                {
                    "slot_ids": [item["visual_slot_id"] for item in current],
                    "length": len(current),
                    "decisions": [item["generation_decision"] for item in current],
                }
            )
        current = []
    if len(current) >= 2:
        streaks.append(
            {
                "slot_ids": [item["visual_slot_id"] for item in current],
                "length": len(current),
                "decisions": [item["generation_decision"] for item in current],
            }
        )
    return streaks


def build_review_exclusions(review_payload: Any, slots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = as_rows(review_payload, "decisions")
    slot_lookup = {slot["visual_slot_id"]: slot for slot in slots}
    exclusions: list[dict[str, Any]] = []
    for row in rows:
        status = clean_text(row.get("status")).lower()
        if status not in {"reject", "exclude", "render_excluded", "manual_replace"}:
            continue
        slot_id = clean_text(row.get("visual_slot_id"))
        scene_id = clean_text(row.get("scene_id"))
        matched_slot = slot_lookup.get(slot_id)
        if not matched_slot and scene_id:
            matched_slot = next((slot for slot in slots if scene_id in slot.get("beat_ids", []) or scene_id == slot.get("source_scene_id")), None)
        exclusions.append(
            {
                "visual_slot_id": matched_slot["visual_slot_id"] if matched_slot else slot_id,
                "status": status,
                "reason": clean_text(row.get("reason") or row.get("note")),
            }
        )
    return exclusions


def build_report(project_json: Path) -> dict[str, Any]:
    project = load_project(project_json)
    reports = project.setdefault("reports", {})
    policy = cadence_policy(project)
    slots, beats = build_slot_records(project)
    review_decisions = load_payload(project.get("qc", {}).get("review_decisions_path"), {})
    continuity = load_payload(project.get("qc", {}).get("continuity_qc_report_path"), {})
    edl = as_rows(load_payload(project.get("render", {}).get("edit_decision_list_path"), {}), "edl")
    production_report = load_payload(project.get("reports", {}).get("production_report_json_path"), {})

    beat_to_slots: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for slot in slots:
        for beat_id in slot.get("beat_ids", []):
            beat_to_slots[beat_id].append(slot)

    durations = [float(slot["duration"]) for slot in slots]
    slot_types = as_counter(slots, "slot_type")
    generation_decisions = as_counter(slots, "generation_decision")
    long_static_holds = [
        slot for slot in slots
        if float(slot["duration"]) > policy["max_static_hold_sec"]
        and (
            slot["generation_decision"] in NON_GENERATIVE_DECISIONS
            or any(clean_text(row.get("motion_type")).lower() == "static_hold" and clean_text(row.get("visual_slot_id")) == slot["visual_slot_id"] for row in edl)
        )
    ]
    very_short_slots = [slot for slot in slots if float(slot["duration"]) < policy["min_slot_duration_sec"]]
    repeated_slot_type_streaks = repeated_streaks([slot["slot_type"] for slot in slots], min_length=3)
    repeated_same_setup_new_angle_streaks = same_setup_streaks(slots)

    beats_with_too_many_visual_slots: list[dict[str, Any]] = []
    beats_with_no_visual_slots: list[dict[str, Any]] = []
    for beat_id, beat in beats.items():
        duration = float(beat.get("duration", float(beat.get("end", 0) or 0) - float(beat.get("start", 0) or 0)) or 0)
        beat_slots = sorted(beat_to_slots.get(beat_id, []), key=lambda row: row["start"])
        if not beat_slots:
            beats_with_no_visual_slots.append({"beat_id": beat_id, "voice_text": clean_text(beat.get("voice_text"))})
            continue
        threshold = max(2, int((duration / policy["target_slot_duration_sec"]) + 1.999))
        if len(beat_slots) > threshold:
            beats_with_too_many_visual_slots.append(
                {"beat_id": beat_id, "slot_count": len(beat_slots), "threshold": threshold, "voice_text": clean_text(beat.get("voice_text"))}
            )

    slots_with_missing_must_show = [slot for slot in slots if not slot["must_show"]]
    slots_with_abstract_or_weak_must_show = [
        {
            "visual_slot_id": slot["visual_slot_id"],
            "must_show": slot["must_show"],
        }
        for slot in slots
        if slot["must_show"] and all(is_weak_must_show(item) for item in slot["must_show"])
    ]
    slots_with_empty_or_generic_reason = [
        {"visual_slot_id": slot["visual_slot_id"], "reason": slot["reason"]}
        for slot in slots
        if is_generic_reason(slot["reason"])
    ]
    review_exclusions = build_review_exclusions(review_decisions, slots)
    continuity_warnings = continuity.get("warnings", []) if isinstance(continuity, dict) else []
    continuity_errors = continuity.get("errors", []) if isinstance(continuity, dict) else []

    blocking_issues: list[str] = []
    warnings: list[str] = []
    recommendations: list[str] = []

    if beats_with_no_visual_slots:
        blocking_issues.append(f"{len(beats_with_no_visual_slots)} beats have no visual slots.")
    if slots_with_missing_must_show:
        blocking_issues.append(f"{len(slots_with_missing_must_show)} slots are missing must_show.")
    if continuity_errors:
        blocking_issues.append(f"Continuity report has {len(continuity_errors)} error(s).")
    if review_exclusions:
        warnings.append(f"{len(review_exclusions)} slots are excluded by review decisions.")
    if long_static_holds:
        warnings.append(f"{len(long_static_holds)} long static holds may flatten pacing.")
    if very_short_slots:
        warnings.append(f"{len(very_short_slots)} very short slots may feel unreadable.")
    if slots_with_abstract_or_weak_must_show:
        warnings.append(f"{len(slots_with_abstract_or_weak_must_show)} slots use abstract or weak must_show descriptions.")
    if slots_with_empty_or_generic_reason:
        warnings.append(f"{len(slots_with_empty_or_generic_reason)} slots have empty or generic reasons.")
    if repeated_slot_type_streaks:
        warnings.append(f"{len(repeated_slot_type_streaks)} repeated slot_type streaks may reduce visual diversity.")
    if repeated_same_setup_new_angle_streaks:
        warnings.append(f"{len(repeated_same_setup_new_angle_streaks)} repeated same-setup/new-angle streaks may make the film feel stuck.")
    if beats_with_too_many_visual_slots:
        warnings.append(f"{len(beats_with_too_many_visual_slots)} beats are oversplit into too many visual slots.")
    if continuity_warnings:
        warnings.append(f"Continuity report has {len(continuity_warnings)} warning(s).")

    slots_per_beat_ratio = round(len(slots) / max(len(beats), 1), 4) if beats else 0.0
    if slots_per_beat_ratio > 1.8:
        recommendations.append("Reduce slot churn on dense beats so the film has more room to breathe.")
    if repeated_slot_type_streaks or repeated_same_setup_new_angle_streaks:
        recommendations.append("Introduce wider variation in slot type, distance, and setup changes across adjacent beats.")
    if slots_with_abstract_or_weak_must_show or slots_with_missing_must_show:
        recommendations.append("Rewrite weak must_show fields so each slot points to a concrete, observable image.")
    if slots_with_empty_or_generic_reason:
        recommendations.append("Explain why each slot exists in film terms, not just that it supports narration.")
    if not recommendations:
        recommendations.append("Calibration looks balanced enough for a pilot pass; focus next on image quality and continuity consistency.")

    summary_lines = [
        f"{len(beats)} narration beats mapped to {len(slots)} visual slots.",
        f"Slots per beat ratio: {slots_per_beat_ratio}.",
        f"Average slot duration: {round(sum(durations) / len(durations), 4) if durations else 0.0}s.",
        f"New image slots: {sum(1 for slot in slots if slot['generation_decision'] not in NON_GENERATIVE_DECISIONS)}.",
        f"Hold/continuation slots: {sum(1 for slot in slots if slot['generation_decision'] in NON_GENERATIVE_DECISIONS)}.",
    ]

    payload = {
        "project_id": project.get("project_id"),
        "created_at": iso_now(),
        "report_type": "visual_calibration_report",
        "paths": {
            "project_json": str(project_json),
            "project_status_command": f'yt-nonstop status --project-json "{project_json}"',
            "production_report_json_path": project.get("reports", {}).get("production_report_json_path"),
        },
        "metrics": {
            "narration_beats_count": len(beats),
            "visual_slots_count": len(slots),
            "slots_per_beat_ratio": slots_per_beat_ratio,
            "average_slot_duration": round(sum(durations) / len(durations), 4) if durations else 0.0,
            "min_slot_duration": round(min(durations), 4) if durations else 0.0,
            "max_slot_duration": round(max(durations), 4) if durations else 0.0,
            "count_by_slot_type": slot_types,
            "count_by_generation_decision": generation_decisions,
            "new_image_slots": sum(1 for slot in slots if slot["generation_decision"] not in NON_GENERATIVE_DECISIONS),
            "hold_previous_or_continuation_slots": sum(1 for slot in slots if slot["generation_decision"] in NON_GENERATIVE_DECISIONS),
            "key_beat_slots": sum(1 for slot in slots if slot["key_beat"]),
            "long_static_holds": len(long_static_holds),
            "very_short_slots": len(very_short_slots),
            "repeated_slot_type_streaks": len(repeated_slot_type_streaks),
            "repeated_same_setup_new_angle_streaks": len(repeated_same_setup_new_angle_streaks),
            "beats_with_too_many_visual_slots": len(beats_with_too_many_visual_slots),
            "beats_with_no_visual_slots": len(beats_with_no_visual_slots),
            "slots_with_abstract_or_weak_must_show": len(slots_with_abstract_or_weak_must_show),
            "slots_with_missing_must_show": len(slots_with_missing_must_show),
            "slots_with_empty_or_generic_reason": len(slots_with_empty_or_generic_reason),
            "slots_excluded_by_review": len(review_exclusions),
            "continuity_warnings": len(continuity_warnings),
            "continuity_errors": len(continuity_errors),
        },
        "blocking_issues": blocking_issues,
        "warnings": warnings,
        "pacing_analysis": {
            "long_static_holds": long_static_holds,
            "very_short_slots": [{"visual_slot_id": slot["visual_slot_id"], "duration": slot["duration"]} for slot in very_short_slots],
            "beats_with_too_many_visual_slots": beats_with_too_many_visual_slots,
        },
        "visual_diversity_analysis": {
            "count_by_slot_type": slot_types,
            "count_by_generation_decision": generation_decisions,
            "repeated_slot_type_streaks": repeated_slot_type_streaks,
            "repeated_same_setup_new_angle_streaks": repeated_same_setup_new_angle_streaks,
        },
        "beat_coverage_analysis": {
            "beats_with_no_visual_slots": beats_with_no_visual_slots,
            "beats_with_too_many_visual_slots": beats_with_too_many_visual_slots,
        },
        "justification_analysis": {
            "slots_with_abstract_or_weak_must_show": slots_with_abstract_or_weak_must_show,
            "slots_with_missing_must_show": [{"visual_slot_id": slot["visual_slot_id"]} for slot in slots_with_missing_must_show],
            "slots_with_empty_or_generic_reason": slots_with_empty_or_generic_reason,
            "slots_excluded_by_review": review_exclusions,
        },
        "continuity": {
            "warnings": continuity_warnings,
            "errors": continuity_errors,
        },
        "summary": summary_lines,
        "recommendations": recommendations,
        "production_report_status": production_report.get("status") if isinstance(production_report, dict) else None,
    }
    return payload


def write_markdown(payload: dict[str, Any], md_path: Path) -> None:
    metrics = payload["metrics"]
    lines = [
        "# Visual Calibration Report",
        "",
        f"Generated at: {payload['created_at']}",
        f"Project: {payload['project_id']}",
        f"Project status command: `{payload['paths']['project_status_command']}`",
    ]
    if payload["paths"].get("production_report_json_path"):
        lines.append(f"Production report path: `{payload['paths']['production_report_json_path']}`")
    lines.extend(
        [
            "",
            "## Summary",
            *[f"- {item}" for item in payload["summary"]],
            "",
            "## Blocking Issues",
        ]
    )
    lines.extend([f"- {item}" for item in payload["blocking_issues"]] or ["- none"])
    lines.extend(["", "## Warnings"])
    lines.extend([f"- {item}" for item in payload["warnings"]] or ["- none"])
    lines.extend(
        [
            "",
            "## Pacing Analysis",
            f"- Average slot duration: {metrics['average_slot_duration']}s",
            f"- Min/max slot duration: {metrics['min_slot_duration']}s / {metrics['max_slot_duration']}s",
            f"- Long static holds: {metrics['long_static_holds']}",
            f"- Very short slots: {metrics['very_short_slots']}",
            f"- Beats with too many visual slots: {metrics['beats_with_too_many_visual_slots']}",
            "",
            "## Visual Diversity Analysis",
            f"- Count by slot type: {metrics['count_by_slot_type']}",
            f"- Count by generation decision: {metrics['count_by_generation_decision']}",
            f"- Repeated slot_type streaks: {metrics['repeated_slot_type_streaks']}",
            f"- Repeated same_setup/new_angle streaks: {metrics['repeated_same_setup_new_angle_streaks']}",
            "",
            "## Beat Coverage Analysis",
            f"- Narration beats: {metrics['narration_beats_count']}",
            f"- Visual slots: {metrics['visual_slots_count']}",
            f"- Slots per beat ratio: {metrics['slots_per_beat_ratio']}",
            f"- Beats with no visual slots: {metrics['beats_with_no_visual_slots']}",
            "",
            "## Recommendations",
        ]
    )
    lines.extend([f"- {item}" for item in payload["recommendations"]] or ["- none"])
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-json", required=True)
    args = parser.parse_args()

    project_json = Path(args.project_json).resolve()
    project = load_project(project_json)
    json_path = Path(project["reports"]["visual_calibration_report_json_path"])
    md_path = Path(project["reports"]["visual_calibration_report_md_path"])
    payload = build_report(project_json)
    save_json(json_path, payload)
    write_markdown(payload, md_path)

    project["reports"]["visual_calibration_report_json_path"] = str(json_path)
    project["reports"]["visual_calibration_report_md_path"] = str(md_path)
    project["reports"]["visual_calibration_report_status"] = "blocked" if payload["blocking_issues"] else "needs_review" if payload["warnings"] else "ready"
    save_project(project_json, project)
    print(json_path)
    print(md_path)


if __name__ == "__main__":
    main()
