from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from django.conf import settings

FRONT_ANGLE = "front"
LEFT_ANGLE = "left"
RIGHT_ANGLE = "right"


def _float_or_none(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _setting_float(name: str, default: float) -> float:
    return float(getattr(settings, name, default))


def bootstrap_quality_decision(
    probe_meta: Mapping[str, object],
    angle: str,
) -> tuple[bool, dict[str, Any]]:
    """Decide if an already detected face is usable as an enrollment sample.

    Verification probes are deliberately strict because they protect a live
    decision. Enrollment needs a different gate: reject only frames that are
    unlikely to produce a stable template, while allowing normal webcam noise.
    """

    if bool(probe_meta.get("quality_pass")):
        return True, {"reason": "strict_quality_passed", "reason_codes": []}

    if probe_meta.get("face_present") is False:
        return False, {
            "reason": "face_not_found",
            "message": "Лицо не найдено. Снимите ещё раз.",
            "reason_codes": ["face_not_found"],
        }

    reason_codes: list[str] = []

    det_score = _float_or_none(probe_meta.get("det_score"))
    min_det = _setting_float("FACE_BOOTSTRAP_SAMPLE_DET_SCORE_MIN", 0.2)
    if det_score is not None and det_score < min_det:
        reason_codes.append("low_det_score")

    face_area = _float_or_none(probe_meta.get("face_area_ratio"))
    min_face = _setting_float("FACE_BOOTSTRAP_SAMPLE_FACE_AREA_RATIO_MIN", 0.0035)
    if face_area is not None and face_area < min_face:
        reason_codes.append("small_face")

    blur = _float_or_none(probe_meta.get("blur_laplacian_var"))
    min_blur = _setting_float("FACE_BOOTSTRAP_SAMPLE_BLUR_MIN", 4.0)
    if blur is not None and min_blur > 0 and blur < min_blur:
        reason_codes.append("blurry_face")

    brightness = _float_or_none(probe_meta.get("brightness_mean"))
    min_brightness = _setting_float("FACE_BOOTSTRAP_SAMPLE_BRIGHTNESS_MIN", 8.0)
    max_brightness = _setting_float("FACE_BOOTSTRAP_SAMPLE_BRIGHTNESS_MAX", 252.0)
    if brightness is not None and brightness < min_brightness:
        reason_codes.append("too_dark")
    if brightness is not None and max_brightness < 255 and brightness > max_brightness:
        reason_codes.append("too_bright")

    yaw = _float_or_none(probe_meta.get("pose_yaw"))
    pitch = _float_or_none(probe_meta.get("pose_pitch"))
    max_yaw = _setting_float(
        "FACE_BOOTSTRAP_SAMPLE_FRONT_MAX_ABS_YAW"
        if angle == FRONT_ANGLE
        else "FACE_BOOTSTRAP_SAMPLE_SIDE_MAX_ABS_YAW",
        42.0 if angle == FRONT_ANGLE else 62.0,
    )
    max_pitch = _setting_float("FACE_BOOTSTRAP_SAMPLE_MAX_ABS_PITCH", 42.0)
    if yaw is not None and abs(yaw) > max_yaw:
        reason_codes.append("face_yaw_too_large")
    if pitch is not None and abs(pitch) > max_pitch:
        reason_codes.append("face_pitch_too_large")

    if reason_codes:
        message = "Кадр не сохранён. Снимите ещё раз."
        if "low_det_score" in reason_codes or "small_face" in reason_codes:
            message = "Подойдите ближе. Лицо должно быть крупнее."
        elif "blurry_face" in reason_codes:
            message = "Кадр смазан. Держите камеру ровно."
        elif "too_dark" in reason_codes or "too_bright" in reason_codes:
            message = "Свет мешает. Снимите при ровном свете."
        elif "face_yaw_too_large" in reason_codes or "face_pitch_too_large" in reason_codes:
            message = "Поворот слишком сильный. Поверните меньше."
        return False, {
            "reason": "bootstrap_quality_failed",
            "message": message,
            "reason_codes": reason_codes,
        }

    raw_soft_codes = probe_meta.get("quality_reason_codes")
    soft_codes = (
        [str(code) for code in raw_soft_codes]
        if isinstance(raw_soft_codes, (list, tuple))
        else []
    )
    return True, {
        "reason": "bootstrap_relaxed_quality_passed",
        "reason_codes": soft_codes,
    }
