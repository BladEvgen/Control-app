from __future__ import annotations

import json
from typing import Any, Optional

PAD_DIAGNOSTICS_VERSION = "pad_diagnostics_v5"

PAD_TRACE_SCHEMA = "pad_trace_v12"


def _quality_poor_threshold() -> float:
    """Return configured PAD threshold for «quality poor» (decision gate).

    Returns:
        ``decision_quality_poor_min`` from ``settings.PHOTO_PAD_NUMBERS`` or default.
    """
    from django.conf import settings

    nums = getattr(settings, "PHOTO_PAD_NUMBERS", None)
    if isinstance(nums, dict) and "decision_quality_poor_min" in nums:
        try:
            return float(nums["decision_quality_poor_min"])
        except (TypeError, ValueError):
            pass
    return 0.45


def _device_present_floor() -> float:
    """Return face-gated device «present» floor (aligns with PAD rule engine).

    Returns:
        Configured ``decision_device_present_min`` or default ``0.25``.
    """
    from django.conf import settings

    nums = getattr(settings, "PHOTO_PAD_NUMBERS", None)
    if isinstance(nums, dict) and "decision_device_present_min" in nums:
        try:
            return float(nums["decision_device_present_min"])
        except (TypeError, ValueError):
            pass
    return 0.25


def _frame_present_floor() -> float:
    """Return face-gated frame «present» floor (aligns with PAD rule engine).

    Returns:
        Configured ``decision_frame_present_min`` or default ``0.40``.
    """
    from django.conf import settings

    nums = getattr(settings, "PHOTO_PAD_NUMBERS", None)
    if isinstance(nums, dict) and "decision_frame_present_min" in nums:
        try:
            return float(nums["decision_frame_present_min"])
        except (TypeError, ValueError):
            pass
    return 0.40


def extract_pad_struct_from_tags(tags: list[str]) -> Optional[dict[str, Any]]:
    """Parse the ``pad_struct:{json}`` tag if present.

    Args:
        tags: Tag list as stored on ``LessonAttendance.photo_spoof_tags``.

    Returns:
        Decoded dict or None.
    """
    prefix = "pad_struct:"
    for tag in tags:
        if isinstance(tag, str) and tag.startswith(prefix):
            raw = tag[len(prefix) :].strip()
            try:
                out = json.loads(raw)
            except json.JSONDecodeError:
                return None
            return out if isinstance(out, dict) else None
    return None


def filter_operator_facing_tags(tags: list[str]) -> list[str]:
    """Drop internal machine tags (rules, JSON blob, numeric evidence line).

    Args:
        tags: Raw tag list from PAD.

    Returns:
        Tags suitable for operator UI (COCO hints, quality, recapture hints).
    """
    out: list[str] = []
    for tag in tags:
        if not isinstance(tag, str):
            continue
        if tag.startswith("pad_rule:"):
            continue
        if tag.startswith("pad_struct:"):
            continue
        if tag.startswith("pad_evidence:"):
            continue
        if tag.startswith("pad_ensemble:"):
            continue
        if tag.startswith("pad_global:"):
            continue
        if tag.startswith("pad_ui_reason:"):
            continue
        out.append(tag)


def parse_pad_evidence_line(tags: list[str]) -> Optional[dict[str, float]]:
    """Parse ``pad_evidence:df=...`` key=value pairs into floats.

    Args:
        tags: Raw PAD tags.

    Returns:
        Mapping of short keys to values, or None.
    """
    prefix = "pad_evidence:"
    for tag in tags:
        if isinstance(tag, str) and tag.startswith(prefix):
            body = tag[len(prefix) :].strip()
            pairs: dict[str, float] = {}
            for part in body.split(","):
                part = part.strip()
                if "=" not in part:
                    continue
                k, v = part.split("=", 1)
                try:
                    pairs[k.strip()] = float(v.strip())
                except ValueError:
                    continue
            return pairs or None
    return None


def parse_pad_ui_reason_from_tags(tags: list[str]) -> Optional[str]:
    """Return operator-facing Russian copy from ``pad_ui_reason:…`` tag."""
    prefix = "pad_ui_reason:"
    for tag in tags:
        if isinstance(tag, str) and tag.startswith(prefix):
            text = tag[len(prefix) :].strip()
            return text or None
    return None


def _evidence_line_to_english_metrics(
    raw: Optional[dict[str, float]]
) -> dict[str, float]:
    """Map legacy short keys on ``pad_evidence`` to stable English metric names.

    Args:
        raw: Parsed ``pad_evidence`` pairs or None.

    Returns:
        English-keyed floats for the diagnostics contract.
    """
    if not raw:
        return {}
    key_map = {
        "df": "fake_signal_score",
        "dev_f": "face_device_score",
        "dev_bg": "background_device_score",
        "frm_f": "face_frame_score",
        "frm_gl": "background_frame_score",
        "rec": "recapture_score",
        "refl": "face_reflection_score",
        "clr": "color_hist_score",
        "qp": "quality_penalty",
    }
    out: dict[str, float] = {}
    for short, val in raw.items():
        name = key_map.get(short.strip(), short.strip())
        out[name] = val
    return out


def _rule_codes_from_tags(tags: list[str]) -> list[str]:
    """Collect ``pad_rule:*`` suffixes as stable rule codes."""
    out: list[str] = []
    for tag in tags:
        if isinstance(tag, str) and tag.startswith("pad_rule:"):
            code = tag[len("pad_rule:") :].strip()
            if code:
                out.append(code)
    return out


def _quality_flag_codes(tags: list[str]) -> list[str]:
    """Return quality-related pipeline tags as machine codes (no prose)."""
    flags: list[str] = []
    for tag in tags:
        if not isinstance(tag, str):
            continue
        if tag == "quality_poor" or tag.startswith("quality_"):
            flags.append(tag)
    return sorted(set(flags))


def _evidence_codes_from_inputs(
    *,
    deepface_score: float,
    device_score: float,
    frame_score: float,
    recapture_score: float,
    face_reflection_score: float,
    color_hist_score: float = 0.0,
    tags: list[str],
) -> list[str]:
    """Derive machine codes for which presentation channels fired (not natural language)."""
    codes: list[str] = []
    spoof_model_fake = "fasnet_fake" in tags or "minifasnet_onnx_fake" in tags
    if deepface_score >= 0.01 and spoof_model_fake:
        codes.append("fake_model_signal")
    if "pad_spoof_model_missing" in tags or (
        "deepface_error" in tags and "minifasnet_onnx_used" not in tags
    ):
        codes.append("fake_model_missing_or_error")
    if device_score >= 0.18:
        codes.append("elevated_face_device_score")
    if frame_score >= 0.22:
        codes.append("elevated_face_frame_score")
    if recapture_score >= 0.2:
        codes.append("elevated_recapture_score")
    if face_reflection_score >= 0.24:
        codes.append("elevated_face_reflection_score")
    if color_hist_score >= 0.24:
        codes.append("elevated_color_histogram_score")
    return codes


def _presentation_confidence(
    *,
    status: str,
    trust_confirmed: Optional[bool],
    branch_str: Optional[str] = None,
) -> float:
    """Heuristic alignment of verdict strength with corroboration (presentation axis).

    ``Suspicious`` uses higher values when FasNet and/or strong face geometry agree;
    texture-only outcomes are ``review``, not ``suspicious``, so they use review-tier
    scores here.

    Args:
        status: PAD status string.
        trust_confirmed: Tri-state trust from PAD.
        branch_str: Rule branch from ``pad_struct`` when available.

    Returns:
        Float in ``[0, 1]`` (how decisive corroborated presentation evidence is).
    """
    if status == "error":
        return 0.0
    if status == "suspicious":
        strong = (
            "fake_extreme_score_suspicious",
            "fake_plus_face_gated_screen",
            "fake_high_plus_suspicious_device_face",
            "fake_mid_plus_dual_mid_geometry",
            "fake_plus_strong_recapture_corroborated",
            "fake_single_mid_geometry_suspicious",
            "fake_autonomous_high_without_geometry_suspicious",
            "no_fake_dual_suspicious_geometry",
            "strong_screen_dual_mid_geometry_suspicious",
            "strong_device_only_face_attack_suspicious",
            "no_fake_recapture_strong_corroborated_dual_geometry",
            "recapture_strong_face_geometry_suspicious",
            "fake_plus_face_reflection_suspicious",
            "face_reflection_display_suspicious",
            "fake_plus_color_histogram_suspicious",
            "color_histogram_display_suspicious",
        )
        if branch_str in strong:
            return 0.72
        if branch_str == "recapture_mid_with_suspicious_context_suspicious":
            return 0.58
        return 0.65
    if status == "review":
        if branch_str == "fake_default_review_not_clean":
            return 0.34
        if branch_str == "recapture_isolated_fft_aniso_corroborated_review":
            return 0.44
        if branch_str == "recapture_strong_review":
            return 0.60
        if branch_str in (
            "recapture_strong_with_context",
            "recapture_strong_quality_context_review",
        ):
            return 0.50
        if branch_str == "presentation_insufficient_input_review":
            return 0.36
        if branch_str in (
            "recapture_isolated_dual_texture_ambiguous_review",
            "recapture_strong_loose_context_ambiguous_review",
            "spoof_uncertain_texture_ambiguous_review",
        ):
            return 0.46
        if branch_str == "background_screen_context_review":
            return 0.40
        return 0.45
    if status == "clean" and trust_confirmed is True:
        if branch_str == "fake_low_confidence_no_geometry_clean":
            return 0.62
        return 0.88
    if status == "clean" and trust_confirmed is None:
        if branch_str in (
            "recapture_isolated_single_cue_texture_clean",
            "recapture_isolated_extreme_moire_live_uncertain_clean",
            "recapture_isolated_extreme_single_channel_uncertain_clean",
            "recapture_isolated_dual_texture_low_rec_uncertain_clean",
        ):
            return 0.42
        if branch_str in (
            "recapture_mid_weak_geometry_clean",
            "spoof_model_uncertain_low_recapture_clean",
            "spoof_model_uncertain_recapture_uncertain_clean",
            "recapture_strong_without_face_geometry_clean",
            "face_reflection_isolated_uncertain_clean",
        ):
            return 0.40
        return 0.38
    if status == "clean":
        return 0.55
    return 0.5


def _uncertainty_codes(
    *,
    status: str,
    trust_confirmed: Optional[bool],
    tags: list[str],
    quality_degraded: bool,
) -> list[str]:
    """Build machine codes describing uncertainty (separate from verdict label)."""
    codes: list[str] = []
    if trust_confirmed is None and status not in ("error",):
        codes.append("trust_indeterminate")
    if quality_degraded:
        codes.append("low_image_quality")
    if "pad_spoof_model_missing" in tags or (
        "deepface_error" in tags and "minifasnet_onnx_used" not in tags
    ):
        codes.append("fake_model_unavailable")
    if status == "review":
        codes.append("outcome_review_recommended")
    if status == "suspicious":
        codes.append("high_presentation_attack_risk")
    return codes


def _append_insufficient_roi_uncertainty(
    uncertainty_codes: list[str],
    *,
    status: str,
    branch_str: Optional[str],
) -> None:
    """Tag review outcomes that stem from inadequate ROI for texture/geometry fusion."""
    if (
        status == "review"
        and branch_str == "presentation_insufficient_input_review"
    ):
        uncertainty_codes.append("presentation_roi_insufficient")


def _operator_action(
    *,
    status: str,
    product_outcome: str,
    trust_confirmed: Optional[bool],
    branch_str: Optional[str],
    quality_degraded: bool,
    missing_signals: list[str],
) -> tuple[str, str]:
    if status == "pending":
        return "wait", "scan_pending"
    if status == "error":
        return "retry_photo", "scan_failed_retry_photo"
    if status == "suspicious" or trust_confirmed is False:
        return "reject", "presentation_attack_risk"
    if status == "clean" and trust_confirmed is True:
        return "accept", "accepted_automatically"
    if status == "clean":
        return "accept_with_caution", "accepted_with_lower_confidence"

    branch = branch_str or ""
    retry_branches = {
        "presentation_insufficient_input_review",
        "fake_quality_limited_review",
        "fake_quality_poor_review",
        "image_quality_degraded_review",
        "quality_poor_with_face_gated_screen",
        "background_screen_context_review",
        "no_fake_dual_geom_small_face_review",
        "no_fake_recapture_strong_dual_geometry_small_face_review",
        "recapture_strong_quality_context_review",
    }
    manual_branches = {
        "spoof_model_disagreement_review",
        "ensemble_consensus_review",
        "fake_default_review_not_clean",
        "fake_color_histogram_review",
        "face_reflection_context_review",
        "color_histogram_context_review",
        "recapture_isolated_dual_texture_ambiguous_review",
        "recapture_strong_loose_context_ambiguous_review",
        "spoof_uncertain_texture_ambiguous_review",
        "spoof_model_uncertain_weak_face_geometry",
        "weak_face_gated_combined_review",
    }
    if product_outcome == "insufficient_input_review" or branch in retry_branches:
        return "retry_photo", "quality_or_pose_blocks_auto_decision"
    if branch in manual_branches:
        return "manual_review", "ambiguous_presentation_signals"
    if quality_degraded:
        return "retry_photo", "quality_degraded_retry_photo"
    if missing_signals:
        return "retry_photo", "model_signal_missing_retry_photo"
    return "manual_review", "insufficient_consensus_for_auto_decision"


def _background_context_codes() -> list[str]:
    """Static policy codes: background channels are diagnostic-only for presentation."""
    return [
        "background_scores_excluded_from_presentation_risk",
        "face_gated_geometry_required_for_suspicious",
    ]


def build_pad_diagnostic_payload(
    *,
    status: str,
    trust_confirmed: Optional[bool],
    risk_score: float,
    model_version: str,
    elapsed_ms: float,
    deepface_score: float,
    device_score: float,
    frame_score: float,
    quality_penalty: float,
    device_bg_score: float,
    frame_global_score: float,
    recapture_score: float,
    tags: list[str],
    face_reflection_score: float = 0.0,
    color_hist_score: float = 0.0,
) -> dict[str, Any]:
    """Build the public, English-keyed diagnostics object for clients.

    Image quality metrics are grouped under ``quality``; presentation attack
    evidence under ``presentation``. They must not be conflated in consumers.

    Args:
        status: PAD status (clean/review/suspicious/error/pending).
        trust_confirmed: Tri-state live-trust from PAD.
        risk_score: Fused presentation risk in ``[0, 1]`` (quality not mixed in).
        model_version: PAD model version string.
        elapsed_ms: Pipeline wall time.
        deepface_score: Spoof model score on face.
        device_score: Face-gated device score.
        frame_score: Face-gated frame/quad score.
        quality_penalty: Cumulative quality penalty (separate axis).
        device_bg_score: Background device diagnostic.
        frame_global_score: Global frame diagnostic.
        recapture_score: Face-inner recapture heuristic.
        face_reflection_score: Screen-like reflections on the upper face.
        color_hist_score: Face ROI YCrCb/Luv histogram recapture cue.
        tags: Full tag list from the pipeline.

    Returns:
        JSON-serializable dict with English keys only.
    """
    struct = extract_pad_struct_from_tags(tags)
    struct_dict = struct if isinstance(struct, dict) else None
    branch = struct_dict.get("branch") if isinstance(struct_dict, dict) else None
    branch_str = branch if isinstance(branch, str) else None
    product_outcome = (
        struct_dict.get("product_outcome") if isinstance(struct_dict, dict) else None
    )
    if not isinstance(product_outcome, str) or not product_outcome:
        product_outcome = status
    elif product_outcome != status and status in ("suspicious", "clean", "error"):
        product_outcome = status

    q_thr = _quality_poor_threshold()
    quality_degraded = "quality_poor" in tags or quality_penalty >= q_thr
    spoof_model_fake = "fasnet_fake" in tags or "minifasnet_onnx_fake" in tags
    face_area_ratio = 0.0
    if isinstance(struct_dict, dict):
        far = struct_dict.get("face_area_ratio")
        if isinstance(far, (int, float)):
            face_area_ratio = float(far)

    corroboration = (
        struct_dict.get("corroboration") if isinstance(struct_dict, dict) else None
    )
    corr_dict = corroboration if isinstance(corroboration, dict) else {}

    raw_evidence = parse_pad_evidence_line(tags)
    evidence_metrics = _evidence_line_to_english_metrics(raw_evidence)

    rule_codes = _rule_codes_from_tags(tags)
    evidence_codes = _evidence_codes_from_inputs(
        deepface_score=deepface_score,
        device_score=device_score,
        frame_score=frame_score,
        recapture_score=recapture_score,
        face_reflection_score=face_reflection_score,
        color_hist_score=color_hist_score,
        tags=tags,
    )

    conflicting: list[str] = []
    if quality_degraded and status == "suspicious":
        conflicting.append("low_quality_but_high_presentation_alert")
    if quality_degraded and trust_confirmed is True and status == "clean":
        conflicting.append("low_quality_but_clean_presentation")

    missing_signals: list[str] = []
    if "pad_spoof_model_missing" in tags or (
        "deepface_error" in tags and "minifasnet_onnx_used" not in tags
    ):
        missing_signals.append("fake_model_score")

    review_reason_codes: list[str] = []

    clean_reason_codes: list[str] = []

    interpretability_codes: list[str] = []
    if status == "review" and branch_str:
        if branch_str == "presentation_insufficient_input_review":
            interpretability_codes.append(
                "presentation_roi_unreliable_for_attack_verdict"
            )
        low_other = (
            deepface_score < 0.05
            and device_score < _device_present_floor()
            and frame_score < _frame_present_floor()
        )
        if branch_str in (
            "recapture_strong_review",
            "recapture_isolated_fft_aniso_corroborated_review",
        ):
            if low_other and not spoof_model_fake:
                interpretability_codes.append(
                    "review_primarily_face_texture_periodicity"
                )
            if branch_str == "recapture_isolated_fft_aniso_corroborated_review":
                interpretability_codes.append(
                    "texture_fft_and_anisotropy_both_elevated"
                )
        if (
            branch_str == "fake_default_review_not_clean"
            and spoof_model_fake
            and deepface_score < 0.48
        ):
            interpretability_codes.append("liveness_model_signal_weak_not_strong_proof")
        if branch_str == "recapture_isolated_dual_texture_ambiguous_review":
            interpretability_codes.append("texture_fft_and_anisotropy_both_elevated")
            interpretability_codes.append("review_primarily_face_texture_periodicity")
        if branch_str in (
            "recapture_strong_loose_context_ambiguous_review",
            "spoof_uncertain_texture_ambiguous_review",
            "face_reflection_context_review",
            "color_histogram_context_review",
            "fake_color_histogram_review",
        ):
            interpretability_codes.append("review_primarily_face_texture_periodicity")
        if branch_str in (
            "color_histogram_context_review",
            "fake_color_histogram_review",
        ):
            interpretability_codes.append("color_histogram_recapture_pattern")
    if status == "clean":
        if branch_str == "recapture_isolated_single_cue_texture_clean":
            interpretability_codes.append(
                "single_texture_channel_downweighted_automatic_clean",
            )
        if branch_str == "fake_low_confidence_no_geometry_clean":
            interpretability_codes.append("fasnet_below_review_threshold_auto_cleared")
        if branch_str == "recapture_mid_weak_geometry_clean":
            interpretability_codes.append(
                "recapture_mid_downgraded_no_suspicious_geometry"
            )
        if branch_str == "spoof_model_uncertain_low_recapture_clean":
            interpretability_codes.append(
                "spoof_model_missing_low_recapture_auto_cleared"
            )
        if branch_str == "recapture_isolated_extreme_moire_live_uncertain_clean":
            interpretability_codes.append("texture_fft_and_anisotropy_both_elevated")
        if branch_str == "recapture_isolated_extreme_single_channel_uncertain_clean":
            interpretability_codes.append(
                "single_texture_channel_downweighted_automatic_clean",
            )
        if branch_str == "spoof_model_uncertain_recapture_uncertain_clean":
            interpretability_codes.append(
                "spoof_model_missing_low_recapture_auto_cleared",
            )
        if branch_str == "face_reflection_isolated_uncertain_clean":
            interpretability_codes.append(
                "isolated_reflection_downweighted_without_geometry",
            )

    uncertainty_codes = _uncertainty_codes(
        status=status,
        trust_confirmed=trust_confirmed,
        tags=tags,
        quality_degraded=quality_degraded,
    )
    _append_insufficient_roi_uncertainty(
        uncertainty_codes, status=status, branch_str=branch_str
    )

    decision_support_flags: list[str] = []
    if isinstance(struct_dict, dict) and struct_dict.get("shield_normal_live") is True:
        decision_support_flags.append("shield_normal_live_active")
    if corr_dict.get("fasnet_fake"):
        decision_support_flags.append("corroboration_fasnet_fake")
    if corr_dict.get("minifasnet_onnx_fake"):
        decision_support_flags.append("corroboration_minifasnet_onnx_fake")
    if corr_dict.get("mid_device"):
        decision_support_flags.append("corroboration_mid_device")
    if corr_dict.get("mid_frame"):
        decision_support_flags.append("corroboration_mid_frame")
    if corr_dict.get("recapture_corr"):
        decision_support_flags.append("corroboration_recapture_threshold")
    if corr_dict.get("face_reflection"):
        decision_support_flags.append("corroboration_face_reflection")
    if corr_dict.get("color_histogram"):
        decision_support_flags.append("corroboration_color_histogram")

    operator_action, operator_action_reason = _operator_action(
        status=status,
        product_outcome=product_outcome,
        trust_confirmed=trust_confirmed,
        branch_str=branch_str,
        quality_degraded=quality_degraded,
        missing_signals=missing_signals,
    )

    return {
        "diagnostics_version": PAD_DIAGNOSTICS_VERSION,
        "decision": {
            "final_decision": status,
            "product_outcome": product_outcome,
            "trust_confirmed": trust_confirmed,
            "decision_branch": branch_str,
            "decision_source": "pad_rule_engine",
            "presentation_confidence": round(
                _presentation_confidence(
                    status=status,
                    trust_confirmed=trust_confirmed,
                    branch_str=branch_str,
                ),
                3,
            ),
            "operator_action": operator_action,
            "operator_action_reason": operator_action_reason,
        },
        "presentation": {
            "spoof_risk": round(float(risk_score), 4),
            "fake_signal_score": round(float(deepface_score), 4),
            "face_device_score": round(float(device_score), 4),
            "face_frame_score": round(float(frame_score), 4),
            "recapture_score": round(float(recapture_score), 4),
            "face_reflection_score": round(float(face_reflection_score), 4),
            "color_hist_score": round(float(color_hist_score), 4),
        },
        "quality": {
            "overall_penalty": round(float(quality_penalty), 4),
            "penalty_score": round(float(quality_penalty), 4),
            "face_area_ratio": round(float(face_area_ratio), 5),
            "quality_flags": _quality_flag_codes(tags),
            "is_degraded": bool(quality_degraded),
        },
        "background_context": {
            "background_device_score": round(float(device_bg_score), 4),
            "background_frame_score": round(float(frame_global_score), 4),
            "context_codes": _background_context_codes(),
        },
        "uncertainty": {
            "uncertainty_codes": uncertainty_codes,
            "review_reason_codes": review_reason_codes,
            "clean_reason_codes": clean_reason_codes,
            "interpretability_codes": interpretability_codes,
            "conflicting_signal_codes": conflicting,
            "missing_signal_codes": missing_signals,
        },
        "trace": {
            "pad_trace_schema": (
                struct_dict.get("schema") if isinstance(struct_dict, dict) else None
            ),
            "rule_codes": rule_codes,
            "evidence_codes": evidence_codes,
            "evidence_metrics": evidence_metrics,
            "decision_support_flags": decision_support_flags,
        },
        "operator_tags": filter_operator_facing_tags(tags),
        "model_version": model_version,
        "elapsed_ms": round(float(elapsed_ms), 2),
    }


def diagnostics_payload_for_lesson_attendance(record: Any) -> dict[str, Any]:
    """Rebuild the public PAD diagnostics dict from a persisted ``LessonAttendance`` row.

    Channel scores are taken from the ``pad_evidence:`` tag when present; stored
    columns supply status, trust, fused risk, model version, and the full tag list.

    Args:
        record: Model instance with ``photo_spoof_*`` and ``photo_trust_confirmed``.

    Returns:
        Same structure as :func:`build_pad_diagnostic_payload`.
    """
    tags_raw = getattr(record, "photo_spoof_tags", None)
    tags: list[str] = [str(t) for t in tags_raw] if isinstance(tags_raw, list) else []
    raw_evidence = parse_pad_evidence_line(tags)
    metrics = _evidence_line_to_english_metrics(raw_evidence)
    score = getattr(record, "photo_spoof_score", None)
    risk = float(score) if score is not None else 0.0
    trust = getattr(record, "photo_trust_confirmed", None)
    if trust is not None and not isinstance(trust, bool):
        trust = bool(trust)
    mv = getattr(record, "photo_spoof_model_version", None)
    return build_pad_diagnostic_payload(
        status=str(getattr(record, "photo_spoof_status", "") or ""),
        trust_confirmed=trust,
        risk_score=risk,
        model_version=str(mv or ""),
        elapsed_ms=0.0,
        deepface_score=float(metrics.get("fake_signal_score", 0.0)),
        device_score=float(metrics.get("face_device_score", 0.0)),
        frame_score=float(metrics.get("face_frame_score", 0.0)),
        quality_penalty=float(metrics.get("quality_penalty", 0.0)),
        device_bg_score=float(metrics.get("background_device_score", 0.0)),
        frame_global_score=float(metrics.get("background_frame_score", 0.0)),
        recapture_score=float(metrics.get("recapture_score", 0.0)),
        face_reflection_score=float(metrics.get("face_reflection_score", 0.0)),
        color_hist_score=float(metrics.get("color_hist_score", 0.0)),
        tags=tags,
    )


def diagnostics_from_pad_result(pad: object) -> dict[str, Any]:
    """Build diagnostics dict from any object exposing PAD result fields (e.g. PadResult).

    Args:
        pad: Object with ``status``, scores, ``tags``, ``model_version``, ``elapsed_ms``.

    Returns:
        English-keyed structure from :func:`build_pad_diagnostic_payload`.
    """
    tags = list(getattr(pad, "tags", []) or [])
    return build_pad_diagnostic_payload(
        status=str(getattr(pad, "status", "")),
        trust_confirmed=getattr(pad, "trust_confirmed", None),
        risk_score=float(getattr(pad, "risk_score", 0.0)),
        model_version=str(getattr(pad, "model_version", "")),
        elapsed_ms=float(getattr(pad, "elapsed_ms", 0.0)),
        deepface_score=float(getattr(pad, "deepface_score", 0.0)),
        device_score=float(getattr(pad, "device_score", 0.0)),
        frame_score=float(getattr(pad, "frame_score", 0.0)),
        quality_penalty=float(getattr(pad, "quality_penalty", 0.0)),
        device_bg_score=float(getattr(pad, "device_bg_score", 0.0)),
        frame_global_score=float(getattr(pad, "frame_global_score", 0.0)),
        recapture_score=float(getattr(pad, "recapture_score", 0.0)),
        face_reflection_score=float(getattr(pad, "face_reflection_score", 0.0)),
        color_hist_score=float(getattr(pad, "color_hist_score", 0.0)),
        tags=tags,
    )
