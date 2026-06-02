from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from monitoring_app.photo_pad import (
    STATUS_CLEAN,
    STATUS_REVIEW,
    STATUS_SUSPICIOUS,
    DecisionInputs,
    _mean_clamped,
    _pad_float,
    _pad_int,
    _presentation_device_confirmed,
    _presentation_input_insufficient,
    _presentation_roi_reliable_for_texture,
    _recapture_dual_inner_cues,
)


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


@dataclass
class PadDecisionContext:
    inputs: DecisionInputs
    tags: list[str]
    rec: float
    refl: float
    clr: float
    fasnet_live: bool
    model_disagreement: bool
    deepfake: bool
    spoof_model_uncertain: bool
    device_confirmed: bool
    has_device: bool
    has_frame: bool
    mid_device: bool
    mid_frame: bool
    dual_mid_geometry: bool
    dual_susp_geometry: bool
    strong_screen: bool
    quality_poor: bool
    insufficient_input: bool
    reflection_guard_fake: bool
    background_screen_context: bool
    background_frame_only: bool
    credible_display_context: bool
    roi_texture_ok: bool
    isolated_recapture: bool


def _build_context(inputs: DecisionInputs, tags: list[str]) -> PadDecisionContext:
    rec = _clamp01(inputs.recapture_score)
    refl = _clamp01(inputs.face_reflection_score)
    clr = _clamp01(inputs.color_hist_score)
    model_disagreement = "spoof_model_disagreement" in tags
    fasnet_live = "fasnet_real" in tags
    deepfake = "spoof_model_family_fake" in tags or (
        ("fasnet_fake" in tags or "minifasnet_onnx_fake" in tags)
        and not (model_disagreement and fasnet_live)
    )
    spoof_model_uncertain = (
        "pad_spoof_model_missing" in tags
        or ("deepface_error" in tags and "minifasnet_onnx_used" not in tags)
        or (model_disagreement and not fasnet_live)
    )
    device_confirmed = _presentation_device_confirmed(tags, inputs.device_score)
    has_device = inputs.device_score >= _pad_float("decision_device_present_min")
    has_frame = inputs.frame_score >= _pad_float("decision_frame_present_min")
    mid_device = inputs.device_score >= _pad_float("decision_mid_device_min")
    mid_frame = inputs.frame_score >= _pad_float("decision_mid_frame_min")
    dual_mid_geometry = mid_device and mid_frame
    dual_susp_geometry = (
        inputs.device_score >= _pad_float("decision_suspicious_device_min")
        and inputs.frame_score >= _pad_float("decision_suspicious_frame_min")
    )
    strong_screen = (
        inputs.device_score >= _pad_float("decision_strong_device_min")
        and inputs.frame_score >= _pad_float("decision_strong_frame_min")
    )
    quality_poor = (
        inputs.quality_penalty >= _pad_float("decision_quality_poor_min")
        or "quality_poor" in tags
    )
    insufficient_input = _presentation_input_insufficient(
        tags, inputs.face_area_ratio, inputs.quality_penalty
    )
    reflection_guard_fake = (
        "glasses_reflection_guard" in tags
        and not has_device
        and not has_frame
        and rec < _pad_float("decision_recapture_review_min")
    )
    background_frame_only = "screen_frame_background_only" in tags
    background_screen_context = (
        inputs.device_bg_score >= max(_pad_float("decision_strong_device_min"), 0.52)
        or inputs.frame_global_score >= max(_pad_float("decision_strong_frame_min"), 0.42)
        or (
            "screen_bezel_context" in tags
            and inputs.frame_global_score >= _pad_float("decision_weak_frame_min")
        )
    )
    device_on_face_tags = [t for t in tags if t.startswith("device_on_face:")]
    bezel_only_live = (
        fasnet_live
        and "screen_bezel_context" in tags
        and not device_on_face_tags
        and not background_frame_only
    )
    credible_display_context = (
        device_confirmed
        or (has_device and has_frame)
        or (background_screen_context and not fasnet_live)
        or (
            "screen_bezel_context" in tags
            and inputs.frame_global_score >= _pad_float("decision_weak_frame_min")
            and not bezel_only_live
            and (not fasnet_live or bool(device_on_face_tags))
        )
    )
    isolated_recapture = not has_device and not has_frame and not quality_poor
    roi_texture_ok = _presentation_roi_reliable_for_texture(
        tags, inputs.face_area_ratio, inputs.quality_penalty
    )
    return PadDecisionContext(
        inputs=inputs,
        tags=tags,
        rec=rec,
        refl=refl,
        clr=clr,
        fasnet_live=fasnet_live,
        model_disagreement=model_disagreement,
        deepfake=deepfake,
        spoof_model_uncertain=spoof_model_uncertain,
        device_confirmed=device_confirmed,
        has_device=has_device,
        has_frame=has_frame,
        mid_device=mid_device,
        mid_frame=mid_frame,
        dual_mid_geometry=dual_mid_geometry,
        dual_susp_geometry=dual_susp_geometry,
        strong_screen=strong_screen,
        quality_poor=quality_poor,
        insufficient_input=insufficient_input,
        reflection_guard_fake=reflection_guard_fake,
        background_screen_context=background_screen_context,
        background_frame_only=background_frame_only,
        credible_display_context=credible_display_context,
        roi_texture_ok=roi_texture_ok,
        isolated_recapture=isolated_recapture,
    )


def _neural_debate(ctx: PadDecisionContext) -> dict[str, Any]:
    """FasNet vs MiniFASNet (+ optional guide): one neural spoof score."""
    inp = ctx.inputs
    tags = ctx.tags
    votes: dict[str, float] = {}
    for key, val in inp.model_scores.items():
        votes[str(key)] = _clamp01(val)

    fasnet_spoof = _clamp01(inp.deepface_score)
    minifas_spoof = votes.get("minifasnet_onnx", 0.0)
    if "minifasnet_onnx_fake" in tags and "minifasnet_onnx" not in votes:
        minifas_spoof = max(minifas_spoof, _pad_float("minifasnet_onnx_mid"))

    guide_spoof = 0.0
    if "guide_ycrcb_luv_model_fake" in tags:
        guide_spoof = _pad_float("guide_color_model_strong")
    elif "guide_ycrcb_luv_model_elevated" in tags:
        guide_spoof = _pad_float("guide_color_model_mid")

    outcome = "agree_live"
    score = 0.0
    if ctx.fasnet_live and ctx.model_disagreement:
        outcome = "fasnet_live_overrides_minifas"
        score = 0.0
    elif "fasnet_fake" in tags and "minifasnet_onnx_fake" in tags:
        outcome = "both_fake"
        score = _mean_clamped([fasnet_spoof, minifas_spoof, guide_spoof])
    elif "fasnet_fake" in tags:
        outcome = "fasnet_fake"
        score = max(fasnet_spoof, guide_spoof * 0.85)
    elif "minifasnet_onnx_fake" in tags and not ctx.fasnet_live:
        if ctx.model_disagreement:
            outcome = "minifas_disagreement_conservative"
            score = fasnet_spoof
        else:
            outcome = "minifas_only"
            score = max(minifas_spoof, fasnet_spoof, guide_spoof)
    elif guide_spoof > 0.0 and not ctx.fasnet_live:
        outcome = "guide_elevated"
        score = guide_spoof
    else:
        outcome = "live"
        score = 0.0

    return {
        "outcome": outcome,
        "score": round(score, 4),
        "fasnet_spoof": round(fasnet_spoof, 4),
        "minifas_spoof": round(minifas_spoof, 4),
        "guide_spoof": round(guide_spoof, 4),
    }


def _face_geometry_vote(ctx: PadDecisionContext) -> float:
    inp = ctx.inputs
    on_face = [t for t in ctx.tags if t.startswith("device_on_face:")]
    if len(on_face) > 1:
        return 0.0
    if ctx.device_confirmed:
        return max(_clamp01(inp.device_score), _clamp01(inp.frame_score))
    if ctx.strong_screen:
        return _mean_clamped([inp.device_score, inp.frame_score])
    if ctx.dual_mid_geometry:
        return min(
            max(_clamp01(inp.device_score), _clamp01(inp.frame_score)) * 0.92,
            0.48,
        )
    if ctx.has_device or ctx.has_frame:
        return min(
            _mean_clamped([inp.device_score, inp.frame_score]) * 0.55,
            _pad_float("decision_weak_device_min"),
        )
    return 0.0


def _background_vote(ctx: PadDecisionContext) -> float:
    if ctx.background_frame_only and not ctx.device_confirmed:
        return min(
            _mean_clamped(
                [ctx.inputs.frame_global_score, ctx.inputs.device_bg_score]
            ),
            0.55,
        )
    if not ctx.background_screen_context:
        return 0.0
    if ctx.fasnet_live and not any(
        t.startswith("device_on_face:") for t in ctx.tags
    ):
        return min(
            _mean_clamped(
                [ctx.inputs.frame_global_score, ctx.inputs.device_bg_score]
            )
            * 0.45,
            0.28,
        )
    return _mean_clamped([ctx.inputs.frame_global_score, ctx.inputs.device_bg_score])


def _face_surface_vote(ctx: PadDecisionContext) -> float:
    raw = max(ctx.refl, ctx.clr)
    if ctx.fasnet_live and not ctx.device_confirmed and not ctx.has_frame:
        if not ctx.credible_display_context:
            return min(raw * 0.42, 0.34)
    return raw


def _live_model_vetoes_heuristic_suspicious(
    ctx: PadDecisionContext, neural: float
) -> bool:
    """FasNet «живое» без нейро-риска: блики/цвет/слабый TV не дают auto-reject."""
    if not ctx.fasnet_live or ctx.deepfake:
        return False
    return neural < _pad_float("decision_deepfake_review_min")


def _build_jury(ctx: PadDecisionContext) -> dict[str, Any]:
    debate = _neural_debate(ctx)
    neural = float(debate["score"])
    geometry = _face_geometry_vote(ctx)
    background = _background_vote(ctx)
    recapture = ctx.rec
    surface = _face_surface_vote(ctx)

    review_min = _pad_float("ensemble_review_vote_min")
    strong_min = _pad_float("ensemble_strong_vote_min")
    votes = [
        {"family": "neural_model", "score": round(neural, 4), "signals": ["debate"]},
        {
            "family": "face_display_geometry",
            "score": round(geometry, 4),
            "signals": ["device_face", "frame_face"],
        },
        {
            "family": "background_display_context",
            "score": round(background, 4),
            "signals": ["device_bg", "frame_global"],
        },
        {
            "family": "recapture_texture",
            "score": round(recapture, 4),
            "signals": ["fft", "gradient"],
        },
        {
            "family": "face_surface_artifacts",
            "score": round(surface, 4),
            "signals": ["reflection", "color_histogram"],
        },
    ]
    strong = [v["family"] for v in votes if float(v["score"]) >= strong_min]
    review = [v["family"] for v in votes if float(v["score"]) >= review_min]
    active = [float(v["score"]) for v in votes if float(v["score"]) >= review_min]
    consensus = _mean_clamped(active)

    weights = {
        "neural_model": _pad_float("risk_weight_deepface") or 0.35,
        "face_display_geometry": _pad_float("risk_weight_device")
        + _pad_float("risk_weight_frame"),
        "background_display_context": 0.08,
        "recapture_texture": _pad_float("risk_weight_recapture"),
        "face_surface_artifacts": _pad_float("risk_weight_reflection")
        + _pad_float("risk_weight_color_hist"),
    }
    wsum = sum(weights.values()) or 1.0
    global_score = sum(
        float(v["score"]) * weights.get(str(v["family"]), 0.1) for v in votes
    ) / wsum
    global_score = _clamp01(global_score)

    fam_min = _pad_int("ensemble_suspicious_family_min")
    jury_decision = STATUS_CLEAN
    if (
        len(strong) >= fam_min
        and consensus >= _pad_float("ensemble_suspicious_score_min")
    ):
        jury_decision = STATUS_SUSPICIOUS
    elif "neural_model" in strong or (
        len(review) >= fam_min
        and consensus >= _pad_float("ensemble_review_score_min")
    ):
        jury_decision = STATUS_REVIEW

    return {
        "debate": debate,
        "votes": votes,
        "strong_families": strong,
        "review_families": review,
        "consensus_score": round(consensus, 4),
        "global_spoof_score": round(global_score, 4),
        "jury_decision": jury_decision,
    }


@dataclass
class GlobalVerdict:
    status: str
    trust: Optional[bool]
    branch: str
    risk_score: float
    jury: dict[str, Any] = field(default_factory=dict)


def resolve_global_verdict(
    inputs: DecisionInputs, tags: list[str]
) -> GlobalVerdict:
    """Compute the single product outcome from all PAD channels."""
    ctx = _build_context(inputs, tags)
    jury = _build_jury(ctx)
    debate = jury["debate"]
    neural = float(debate["score"])
    geometry = float(
        next(v["score"] for v in jury["votes"] if v["family"] == "face_display_geometry")
    )
    background = float(
        next(
            v["score"]
            for v in jury["votes"]
            if v["family"] == "background_display_context"
        )
    )
    surface = float(
        next(v["score"] for v in jury["votes"] if v["family"] == "face_surface_artifacts")
    )
    rec = ctx.rec
    refl = ctx.refl
    clr = ctx.clr
    g = float(jury["global_spoof_score"])

    refl_strong = _pad_float("reflection_strong")
    refl_mid = _pad_float("reflection_mid")
    color_strong = _pad_float("color_hist_strong")
    color_mid = _pad_float("color_hist_mid")
    rec_strong = _pad_float("recapture_strong")
    rec_mid = _pad_float("recapture_mid")
    rec_review = _pad_float("decision_recapture_review_min")
    rec_corr = _pad_float("decision_recapture_corroboration_min")
    df_review = _pad_float("decision_deepfake_review_min")
    df_very = _pad_float("decision_deepfake_very_high")
    df_mid_susp = _pad_float("decision_deepfake_mid_suspicious_min")
    min_face_susp = _pad_float("no_fake_susp_min_face_area_ratio")

    risk = (
        _pad_float("risk_weight_deepface") * neural
        + _pad_float("risk_weight_device") * ctx.inputs.device_score
        + _pad_float("risk_weight_frame") * ctx.inputs.frame_score
        + _pad_float("risk_weight_recapture") * rec
        + _pad_float("risk_weight_reflection") * refl
        + _pad_float("risk_weight_color_hist") * clr
    )
    risk = _clamp01(risk)

    status = STATUS_CLEAN
    trust: Optional[bool] = True
    branch = "default_clean"

    def _suspicious(b: str) -> None:
        nonlocal status, trust, branch
        status = STATUS_SUSPICIOUS
        trust = False
        branch = b

    def _review(b: str) -> None:
        nonlocal status, trust, branch
        status = STATUS_REVIEW
        trust = None
        branch = b

    def _clean(b: str, uncertain: bool = False) -> None:
        nonlocal status, trust, branch
        status = STATUS_CLEAN
        trust = None if uncertain else True
        branch = b

    roi_insufficient = (
        any(
            tag in tags
            for tag in ("quality_small_face", "quality_face_edge_crop")
        )
        or (
            inputs.face_area_ratio > 1e-9
            and inputs.face_area_ratio
            < _pad_float("presentation_texture_min_face_area_ratio")
        )
        or (
            "quality_blur" in tags
            and any(
                tag in tags
                for tag in (
                    "quality_poor",
                    "quality_low_contrast",
                    "quality_exposure",
                )
            )
        )
    )

    if ctx.quality_poor and (ctx.has_device or ctx.has_frame or ctx.mid_device):
        if _live_model_vetoes_heuristic_suspicious(ctx, neural):
            _clean("image_quality_uncertain_clean", uncertain=True)
            return GlobalVerdict(status, trust, branch, risk, jury)
        _review("quality_poor_with_face_gated_screen")
        return GlobalVerdict(status, trust, branch, risk, jury)

    if ctx.deepfake and jury.get("jury_decision") == STATUS_SUSPICIOUS:
        if neural >= 0.92 and not ctx.reflection_guard_fake:
            _suspicious("fake_high_confidence_no_geometry_suspicious")
            return GlobalVerdict(status, trust, branch, risk, jury)
        if (
            neural >= df_mid_susp
            and surface >= color_mid
            and refl >= refl_mid
            and ctx.inputs.face_area_ratio
            >= _pad_float("color_hist_min_face_area_ratio")
        ):
            _suspicious("fake_plus_face_reflection_suspicious")
            return GlobalVerdict(status, trust, branch, risk, jury)
        if (
            neural >= df_review
            and clr >= color_strong
            and ctx.inputs.face_area_ratio
            >= _pad_float("color_hist_min_face_area_ratio")
        ):
            _suspicious("fake_plus_color_histogram_suspicious")
            return GlobalVerdict(status, trust, branch, risk, jury)

    if roi_insufficient:
        blur_compound = "quality_blur" in tags and any(
            tag in tags
            for tag in ("quality_poor", "quality_low_contrast", "quality_exposure")
        )
        if (
            not ctx.deepfake
            and not ctx.spoof_model_uncertain
            and not ctx.has_device
            and not ctx.has_frame
            and rec < rec_review
        ):
            edge_or_tiny = any(
                tag in tags
                for tag in ("quality_small_face", "quality_face_edge_crop")
            ) or (
                inputs.face_area_ratio > 1e-9
                and inputs.face_area_ratio
                < _pad_float("presentation_texture_min_face_area_ratio")
            )
            if edge_or_tiny:
                _clean("presentation_insufficient_input_uncertain_clean", uncertain=True)
            elif blur_compound or ctx.quality_poor:
                _clean("image_quality_uncertain_clean", uncertain=True)
            else:
                _clean("presentation_insufficient_input_uncertain_clean", uncertain=True)
            return GlobalVerdict(status, trust, branch, risk, jury)
        _review("presentation_insufficient_input_review")
        return GlobalVerdict(status, trust, branch, risk, jury)

    if (
        ctx.quality_poor
        and not ctx.has_device
        and not ctx.has_frame
        and not ctx.deepfake
    ):
        _clean("image_quality_uncertain_clean", uncertain=True)
        return GlobalVerdict(status, trust, branch, risk, jury)

    if neural >= 0.92 and ctx.quality_poor and not (ctx.has_device and ctx.has_frame):
        _review("fake_quality_poor_review")
        return GlobalVerdict(status, trust, branch, risk, jury)

    if neural >= df_very and "quality_blur" not in tags:
        _suspicious("fake_extreme_score_suspicious")
        return GlobalVerdict(status, trust, branch, risk, jury)
    if neural >= 0.92 and not ctx.reflection_guard_fake:
        _suspicious("fake_high_confidence_no_geometry_suspicious")
        return GlobalVerdict(status, trust, branch, risk, jury)

    if ctx.strong_screen and (ctx.has_device and ctx.has_frame) and ctx.deepfake:
        _suspicious("fake_plus_face_gated_screen")
        return GlobalVerdict(status, trust, branch, risk, jury)

    if (
        rec >= rec_strong
        and rec >= rec_corr
        and ctx.dual_susp_geometry
        and not ctx.quality_poor
        and ctx.inputs.face_area_ratio >= min_face_susp
        and ctx.roi_texture_ok
    ):
        _suspicious("no_fake_recapture_strong_corroborated_dual_geometry")
        return GlobalVerdict(status, trust, branch, risk, jury)

    if ctx.strong_screen and ctx.dual_mid_geometry and not ctx.quality_poor:
        if ctx.inputs.face_area_ratio >= min_face_susp and ctx.roi_texture_ok:
            _suspicious("strong_screen_dual_mid_geometry_suspicious")
            return GlobalVerdict(status, trust, branch, risk, jury)
        if roi_insufficient or ctx.inputs.face_area_ratio < min_face_susp:
            _review("presentation_insufficient_input_review")
            return GlobalVerdict(status, trust, branch, risk, jury)

    if (
        ctx.device_confirmed
        and surface >= refl_strong
        and ctx.inputs.face_area_ratio >= _pad_float("reflection_suspicious_min_face_area_ratio")
        and not ctx.reflection_guard_fake
    ):
        if _live_model_vetoes_heuristic_suspicious(ctx, neural):
            _clean("live_selfie_surface_noise_uncertain_clean", uncertain=True)
            return GlobalVerdict(status, trust, branch, risk, jury)
        _suspicious("face_reflection_display_suspicious")
        return GlobalVerdict(status, trust, branch, risk, jury)

    if (
        clr >= color_strong
        and rec >= rec_corr
        and not ctx.quality_poor
        and ctx.inputs.face_area_ratio >= _pad_float("color_hist_min_face_area_ratio")
    ):
        if _live_model_vetoes_heuristic_suspicious(ctx, neural):
            _clean("live_selfie_surface_noise_uncertain_clean", uncertain=True)
            return GlobalVerdict(status, trust, branch, risk, jury)
        _suspicious("color_histogram_display_suspicious")
        return GlobalVerdict(status, trust, branch, risk, jury)

    if ctx.deepfake:
        if ctx.model_disagreement and not ctx.fasnet_live and neural < df_review:
            _review("spoof_model_disagreement_review")
            return GlobalVerdict(status, trust, branch, risk, jury)
        if ctx.dual_mid_geometry and neural >= df_mid_susp:
            _suspicious("fake_mid_plus_dual_mid_geometry")
            return GlobalVerdict(status, trust, branch, risk, jury)
        if (
            neural >= df_mid_susp
            and ctx.background_screen_context
            and not ctx.device_confirmed
        ):
            _suspicious("fake_mid_plus_background_display_suspicious")
            return GlobalVerdict(status, trust, branch, risk, jury)
        if (
            neural >= df_review
            and clr >= color_strong
            and ctx.inputs.face_area_ratio >= _pad_float("color_hist_min_face_area_ratio")
        ):
            _suspicious("fake_plus_color_histogram_suspicious")
            return GlobalVerdict(status, trust, branch, risk, jury)
        if neural >= df_mid_susp and surface >= color_mid and refl >= refl_mid:
            _suspicious("fake_plus_face_reflection_suspicious")
            return GlobalVerdict(status, trust, branch, risk, jury)
        review_floor = _pad_float("ensemble_review_vote_min")
        if neural >= df_review and ctx.credible_display_context and background >= review_floor:
            _review("fake_background_display_review")
            return GlobalVerdict(status, trust, branch, risk, jury)
        if neural >= df_review and clr >= color_mid:
            _review("fake_color_histogram_review")
            return GlobalVerdict(status, trust, branch, risk, jury)
        if ctx.reflection_guard_fake and neural >= 0.55:
            _review("fake_reflection_guard_review")
            return GlobalVerdict(status, trust, branch, risk, jury)
        if (ctx.quality_poor or roi_insufficient) and neural < 0.92:
            _review(
                "fake_quality_poor_review"
                if ctx.quality_poor
                else "fake_quality_limited_review"
            )
            return GlobalVerdict(status, trust, branch, risk, jury)
        if "quality_blur" in tags and neural < 0.92:
            _review("fake_quality_limited_review")
            return GlobalVerdict(status, trust, branch, risk, jury)
        if (
            neural < df_review
            and not ctx.mid_device
            and not ctx.mid_frame
        ):
            _clean("fake_low_confidence_no_geometry_clean")
            return GlobalVerdict(status, trust, branch, risk, jury)
        if neural >= _pad_float("spoof_model_family_mid"):
            _review("fake_default_review_not_clean")
            return GlobalVerdict(status, trust, branch, risk, jury)

    if (
        refl >= refl_strong
        and ctx.dual_mid_geometry
        and not ctx.quality_poor
        and ctx.inputs.face_area_ratio >= _pad_float("reflection_suspicious_min_face_area_ratio")
    ):
        if _live_model_vetoes_heuristic_suspicious(ctx, neural):
            _clean("live_selfie_surface_noise_uncertain_clean", uncertain=True)
            return GlobalVerdict(status, trust, branch, risk, jury)
        _suspicious("face_reflection_display_suspicious")
        return GlobalVerdict(status, trust, branch, risk, jury)

    if jury["jury_decision"] == STATUS_SUSPICIOUS and not ctx.reflection_guard_fake:
        _suspicious("ensemble_consensus_suspicious")
        return GlobalVerdict(status, trust, branch, risk, jury)

    if (
        refl >= refl_mid
        and not ctx.has_device
        and not ctx.has_frame
        and not ctx.credible_display_context
        and rec < rec_review
        and clr < color_mid
        and not ctx.quality_poor
        and not ctx.insufficient_input
    ):
        _clean("face_reflection_isolated_uncertain_clean", uncertain=True)
        return GlobalVerdict(status, trust, branch, risk, jury)

    live_selfie = (
        ctx.fasnet_live
        and not ctx.deepfake
        and not ctx.has_frame
        and rec < rec_review
        and not ctx.quality_poor
        and not roi_insufficient
        and neural < df_review
        and ctx.inputs.face_area_ratio >= 0.05
        and (refl >= _pad_float("reflection_review_min") or clr >= color_mid)
        and (
            not ctx.device_confirmed
            or "quality_blur" in tags
            or "glasses_reflection_guard" in tags
        )
    )
    if live_selfie:
        _clean("live_selfie_surface_noise_uncertain_clean", uncertain=True)
        return GlobalVerdict(status, trust, branch, risk, jury)

    if (
        ctx.background_screen_context
        and not ctx.has_device
        and not ctx.has_frame
        and not ctx.deepfake
        and not ctx.fasnet_live
        and rec < rec_review
    ):
        _clean("background_screen_context_uncertain_clean", uncertain=True)
        return GlobalVerdict(status, trust, branch, risk, jury)

    if ctx.has_device and not ctx.has_frame and not ctx.deepfake and rec < rec_mid:
        _clean("device_only_context_uncertain_clean", uncertain=True)
        return GlobalVerdict(status, trust, branch, risk, jury)

    if (
        ctx.inputs.quality_penalty > 0.0
        and any(
            t in ctx.tags
            for t in ("quality_blur", "quality_low_contrast", "quality_exposure")
        )
        and not ctx.quality_poor
        and not ctx.deepfake
        and not ctx.has_device
        and not ctx.has_frame
        and rec < rec_review
    ):
        _clean("image_quality_uncertain_clean", uncertain=True)
        return GlobalVerdict(status, trust, branch, risk, jury)

    if ctx.spoof_model_uncertain:
        if clr >= color_mid and surface >= color_mid:
            _review("color_histogram_context_review")
            return GlobalVerdict(status, trust, branch, risk, jury)
        if (
            rec >= rec_mid
            and (rec >= rec_corr or _recapture_dual_inner_cues(ctx.tags))
        ):
            _review("spoof_uncertain_texture_ambiguous_review")
            return GlobalVerdict(status, trust, branch, risk, jury)
        if ctx.model_disagreement:
            _review("spoof_model_disagreement_review")
            return GlobalVerdict(status, trust, branch, risk, jury)
        _clean("spoof_model_uncertain_clean_fallback", uncertain=False)
        return GlobalVerdict(status, trust, branch, risk, jury)

    if ctx.model_disagreement and not ctx.fasnet_live:
        _review("spoof_model_disagreement_review")
        return GlobalVerdict(status, trust, branch, risk, jury)

    if rec >= rec_strong and ctx.isolated_recapture:
        iso = _isolated_recapture_branch(ctx, rec)
        if iso is not None:
            b, uncertain = iso
            if "review" in b or b.startswith("presentation_insufficient"):
                _review(b)
            else:
                _clean(b, uncertain=uncertain)
            return GlobalVerdict(status, trust, branch, risk, jury)

    if jury["jury_decision"] == STATUS_REVIEW and trust is True:
        _review("ensemble_consensus_review")
        return GlobalVerdict(status, trust, branch, risk, jury)

    if clr >= color_strong and not ctx.deepfake and not ctx.credible_display_context:
        pass

    return GlobalVerdict(status, trust, branch, risk, jury)


def _isolated_recapture_branch(
    ctx: PadDecisionContext, rec: float
) -> Optional[tuple[str, bool]]:
    """Return (branch, uncertain_clean) for strong isolated recapture, or None."""
    dual_tex = _recapture_dual_inner_cues(ctx.tags)
    moire_rec = _pad_float("recapture_isolated_moire_forgive_min_rec")
    moire_qp = _pad_float("recapture_isolated_moire_max_quality_penalty")
    ext_single = _pad_float("recapture_isolated_extreme_single_channel_min")
    if dual_tex and rec >= moire_rec and ctx.inputs.quality_penalty < moire_qp:
        if ctx.roi_texture_ok:
            return ("recapture_isolated_extreme_moire_live_uncertain_clean", True)
        return ("presentation_insufficient_input_review", False)
    if dual_tex:
        if ctx.roi_texture_ok:
            return ("recapture_isolated_dual_texture_ambiguous_review", False)
        return ("presentation_insufficient_input_review", False)
    if rec >= ext_single and not dual_tex:
        if ctx.roi_texture_ok:
            return ("recapture_isolated_extreme_single_channel_uncertain_clean", True)
        return ("presentation_insufficient_input_review", False)
    if ctx.roi_texture_ok:
        if dual_tex:
            return ("recapture_isolated_dual_texture_low_rec_uncertain_clean", True)
        return ("recapture_isolated_single_cue_texture_clean", True)
    return ("presentation_insufficient_input_review", False)
