from __future__ import annotations

from collections.abc import Iterable
from typing import Optional, cast

from django.utils.html import format_html, format_html_join
from django.utils.safestring import SafeString
from monitoring_app.models import LessonAttendance
from monitoring_app.pad_diagnostics import (
    diagnostics_payload_for_lesson_attendance,
    parse_pad_ui_reason_from_tags,
)


def _html(format_string: str, *args: object, **kwargs: object) -> SafeString:
    return cast(SafeString, format_html(format_string, *args, **kwargs))


def _html_join(
    sep: str,
    format_string: str,
    args_generator: Iterable[tuple[object, ...]],
) -> SafeString:
    return cast(SafeString, format_html_join(sep, format_string, args_generator))


_BRANCH_EXPLANATION_RU: dict[str, str] = {
    "fake_quality_poor_review": (
        "Модель видит риск подмены, но кадр слабый. Нужна ручная проверка."
    ),
    "fake_extreme_score_suspicious": "Модель почти уверена: кадр похож на подмену.",
    "fake_plus_face_gated_screen": (
        "Модель видит подмену, рядом с лицом есть признаки экрана или рамки."
    ),
    "fake_high_plus_suspicious_device_face": "Высокий риск подмены, у лица видно устройство.",
    "fake_mid_plus_dual_mid_geometry": (
        "Модель и два признака у лица вместе указывают на подмену."
    ),
    "fake_plus_strong_recapture_corroborated": (
        "Модель видит подмену, текстура лица похожа на пересъёмку."
    ),
    "fake_mid_plus_background_display_suspicious": (
        "Модель видит подмену, а в кадре много признаков экрана."
    ),
    "fake_plus_color_histogram_suspicious": (
        "Модель видит подмену, цвета лица похожи на фото с экрана."
    ),
    "fake_background_display_review": (
        "Модель видит риск, в фоне есть признаки экрана. Нужна проверка."
    ),
    "fake_color_histogram_review": (
        "Модель и цвета лица настораживают, но подтверждений мало. Нужна проверка."
    ),
    "fake_single_geometry_channel_review": (
        "Старая ветка проверки больше не используется для новых кадров."
    ),
    "fake_single_mid_geometry_suspicious": (
        "Модель подмены и одно среднее геометрическое плечо у лица — автоматически «подозрительно»."
    ),
    "fake_low_confidence_no_geometry_clean": (
        "Сигнал модели слабый, признаков экрана у лица нет. Кадр принят."
    ),
    "fake_autonomous_high_without_geometry_suspicious": (
        "Модель даёт высокий риск подмены даже без явного экрана у лица."
    ),
    "fake_default_review_not_clean": (
        "Модель сомневается, других сильных признаков нет. Нужна проверка."
    ),
    "no_fake_dual_suspicious_geometry": (
        "Модель спокойна, но у лица видны сильные признаки экрана."
    ),
    "no_fake_dual_geom_small_face_review": (
        "Сильная геометрия при мелком лице — проверка вместо «подозрительно», чтобы снизить ложные срабатывания."
    ),
    "strong_screen_dual_mid_geometry_suspicious": (
        "У лица устойчиво видны признаки экрана. Кадр подозрительный."
    ),
    "strong_face_gated_screen_review": (
        "У лица есть признаки экрана, но модель не уверена. Нужна проверка."
    ),
    "strong_device_only_face_attack_suspicious": (
        "Сильное устройство у лица без рамки — автоматически «подозрительно»."
    ),
    "recapture_strong_review": (
        "Старая ветка проверки больше не используется для новых кадров."
    ),
    "recapture_strong_with_context": (
        "Старая ветка проверки больше не используется для новых кадров."
    ),
    "recapture_strong_face_geometry_suspicious": (
        "Текстура лица похожа на пересъёмку, и это подтверждает геометрия кадра."
    ),
    "recapture_strong_without_face_geometry_clean": (
        "Старая ветка проверки больше не используется для новых кадров."
    ),
    "recapture_strong_loose_context_suspicious": (
        "Старая ветка проверки больше не используется для новых кадров."
    ),
    "recapture_strong_loose_context_ambiguous_review": (
        "Текстура лица настораживает, но признаков экрана мало. Нужна проверка."
    ),
    "recapture_strong_quality_context_review": (
        "Текстура лица настораживает, но кадр слабый. Нужна проверка."
    ),
    "recapture_isolated_fft_aniso_corroborated_review": (
        "Старая ветка проверки больше не используется для новых кадров."
    ),
    "recapture_isolated_dual_texture_uncertain_clean": (
        "Старая ветка проверки больше не используется для новых кадров."
    ),
    "recapture_isolated_dual_texture_suspicious": (
        "Старая ветка проверки больше не используется для новых кадров."
    ),
    "recapture_isolated_dual_texture_ambiguous_review": (
        "Два текстурных признака лица настораживают, но модель и геометрия спокойны."
    ),
    "recapture_isolated_extreme_moire_live_uncertain_clean": (
        "Очень сильная периодика похожа на муар камеры. Кадр принят без полного доверия."
    ),
    "recapture_isolated_extreme_single_channel_uncertain_clean": (
        "Один сильный текстурный признак без подтверждений. Кадр принят осторожно."
    ),
    "recapture_isolated_dual_texture_low_rec_uncertain_clean": (
        "Два текстурных канала при рекапчере на нижней границе «сильно» — «норма» без полного подтверждения проверки фото."
    ),
    "recapture_isolated_single_cue_texture_clean": (
        "Повышенная периодика на лице без второго текстурного канала и без экранной геометрии — "
        "автоматически «норма» без полного подтверждения проверки фото."
    ),
    "recapture_isolated_below_review_bar_clean": (
        "Старая ветка проверки больше не используется для новых кадров."
    ),
    "recapture_mid_with_context": (
        "Старая ветка проверки больше не используется для новых кадров."
    ),
    "recapture_mid_with_suspicious_context_suspicious": (
        "Умеренный рекапчер на лице при подозрительной геометрии устройства или рамки — автоматически «подозрительно»."
    ),
    "recapture_mid_weak_geometry_clean": (
        "Умеренный рекапчер при слабой геометрии у лица — «норма» без полного подтверждения проверки фото."
    ),
    "spoof_model_uncertain_low_recapture_clean": (
        "Модель подмены недоступна, остальные признаки слабые. Кадр принят осторожно."
    ),
    "recapture_with_spoof_model_uncertain": (
        "Старая ветка проверки больше не используется для новых кадров."
    ),
    "spoof_model_uncertain_recapture_uncertain_clean": (
        "Модель подмены недоступна, текстура лица чуть настораживает. Кадр принят осторожно."
    ),
    "spoof_uncertain_strong_recapture_texture_suspicious": (
        "Старая ветка проверки больше не используется для новых кадров."
    ),
    "spoof_uncertain_texture_ambiguous_review": (
        "Модель подмены недоступна, текстура лица подозрительная. Нужна проверка."
    ),
    "quality_poor_with_face_gated_screen": (
        "Низкое качество и слабые «экранные» признаки у лица — проверка (качество ≠ подделка)."
    ),
    "image_quality_degraded_review": (
        "Сильно снижено качество или есть слабые признаки презентации — нужна ручная проверка."
    ),
    "image_quality_low_review": (
        "Старая ветка проверки больше не используется для новых кадров."
    ),
    "image_quality_uncertain_clean": (
        "Кадр не идеальный, но признаков подмены по лицу нет. Принято осторожно."
    ),
    "face_reflection_isolated_uncertain_clean": (
        "Сильный блик на лице без рамки, устройства и текстуры пересъёмки. Кадр принят осторожно."
    ),
    "live_selfie_surface_noise_uncertain_clean": (
        "Живое лицо по основной модели: блики или цвет кожи настораживают, "
        "но экрана и пересъёмки в кадре нет. Кадр принят осторожно."
    ),
    "no_fake_recapture_strong_corroborated_dual_geometry": (
        "Сильный рекапчер при двух подозрительных геометрических каналах у лица — «подозрительно»."
    ),
    "no_fake_recapture_strong_dual_geometry_small_face_review": (
        "Сильный рекапчер и геометрия при мелком лице — проверка."
    ),
    "color_histogram_display_suspicious": (
        "Цвета лица похожи на фото с экрана и подтверждены другим признаком."
    ),
    "color_histogram_context_review": (
        "Цвета лица похожи на пересъёмку, но подтверждений мало. Нужна проверка."
    ),
    "spoof_model_uncertain_weak_face_geometry": (
        "Нет ответа модели подмены; слабая геометрия у лица — проверка."
    ),
    "spoof_model_uncertain_clean_fallback": (
        "Нет ответа модели подмены; остальные сигналы слабые — осторожный допуск «норма»."
    ),
    "weak_face_gated_combined_review": (
        "Слабая комбинация признаков у лица (ниже порога «подозрительно») — проверка."
    ),
    "shield_weak_geometry_clean": (
        "Сработала защита «обычный живой» кадр: слабая геометрия без сильной подмены и с приемлемым качеством."
    ),
    "default_clean": "Значимых признаков подмены по лицу не зафиксировано.",
    "presentation_insufficient_input_review": (
        "Лицо или качество кадра не дают уверенного ответа. Нужен новый кадр или проверка."
    ),
    "presentation_insufficient_input_uncertain_clean": (
        "Данных по лицу мало, но явных признаков подмены нет. Кадр принят осторожно."
    ),
    "spoof_model_disagreement_review": (
        "Модели не согласились между собой. Нужна проверка, без жёсткого отказа."
    ),
    "ensemble_consensus_suspicious": (
        "Несколько независимых признаков сошлись: кадр похож на подмену."
    ),
    "ensemble_consensus_review": (
        "Несколько признаков настораживают, но уверенности мало. Нужна проверка."
    ),
    "fake_plus_face_reflection_suspicious": (
        "Обе модели видят подмену; отражение и цвета лица как на экране."
    ),
    "fake_high_confidence_no_geometry_suspicious": (
        "Обе модели уверены в подмене."
    ),
    "face_reflection_display_suspicious": (
        "Отражение и цвета лица как на экране; подмена вероятна."
    ),
    "color_histogram_display_suspicious": (
        "Цвета лица как на экране, есть подтверждающие признаки."
    ),
    "fake_plus_color_histogram_suspicious": (
        "Подмена: модели и цвета лица как на экране."
    ),
    "fake_quality_poor_review": (
        "Модели видят подмену, но кадр слабый — нужна проверка, не автоблок."
    ),
    "fake_quality_limited_review": (
        "Модели видят риск подмены при ограниченном качестве кадра. Нужна проверка."
    ),
    "background_screen_context_review": (
        "В фоне есть признаки экрана, но у лица подтверждений мало. Нужна проверка."
    ),
    "background_screen_context_uncertain_clean": (
        "Экранные признаки остались в фоне и не привязаны к лицу. Кадр принят осторожно."
    ),
    "device_only_context_uncertain_clean": (
        "В кадре есть устройство, но у лица нет сильных признаков подмены."
    ),
}

_INTERPRETABILITY_RU: dict[str, str] = {
    "review_primarily_face_texture_periodicity": (
        "Решение в основном по текстуре лица. Это повод проверить, но не жёсткое доказательство."
    ),
    "texture_fft_and_anisotropy_both_elevated": (
        "Два текстурных признака совпали, поэтому сигнал надёжнее одиночного шума."
    ),
    "liveness_model_signal_weak_not_strong_proof": (
        "Модельный сигнал в зоне сомнений — это не сильное доказательство подмены, решение осторожное."
    ),
    "single_texture_channel_downweighted_automatic_clean": (
        "Один текстурный канал без подкрепления — автоматически «норма»."
    ),
    "fasnet_below_review_threshold_auto_cleared": (
        "Модельный балл не дотягивает до порога «проверка» и нет средней геометрии — автоматический допуск «норма»."
    ),
    "recapture_mid_downgraded_no_suspicious_geometry": (
        "Рекапчер умеренный, геометрия экрана у лица не на уровне «подозрительно» — автоматически «норма»."
    ),
    "spoof_model_missing_low_recapture_auto_cleared": (
        "Модель подмены недоступна, текстурный сигнал слабый — автоматически «норма»."
    ),
    "presentation_roi_unreliable_for_attack_verdict": (
        "Лицо или качество кадра слабые: текстуру нельзя считать доказательством подмены."
    ),
    "color_histogram_recapture_pattern": (
        "Цвета лица похожи на пересъёмку с экрана или фотографии."
    ),
    "isolated_reflection_downweighted_without_geometry": (
        "Один блик без других признаков экрана не считается доказательством подмены."
    ),
}

_UNCERTAINTY_RU: dict[str, str] = {
    "trust_indeterminate": "Система сомневается. Лучше переснять.",
    "low_image_quality": "Кадр слабый.",
    "fake_model_unavailable": "Одна проверка не сработала.",
    "outcome_review_recommended": "Нужен новый кадр или оператор.",
    "high_presentation_attack_risk": "Похоже на подмену.",
    "presentation_roi_insufficient": (
        "Лицо видно недостаточно хорошо."
    ),
}

_CONTEXT_RU: dict[str, str] = {
    "background_scores_excluded_from_presentation_risk": (
        "Фон не смешивается с оценкой лица."
    ),
    "face_gated_geometry_required_for_suspicious": (
        "Для отказа нужны признаки у лица."
    ),
}

_SUPPORT_FLAG_RU: dict[str, str] = {
    "shield_normal_live_active": "Похоже на обычный живой кадр.",
    "corroboration_fasnet_fake": "Дополнительная модель тоже видит подмену.",
    "corroboration_minifasnet_onnx_fake": "Один модельный канал насторожился.",
    "corroboration_mid_device": "У лица заметно устройство.",
    "corroboration_mid_frame": "У лица заметна рамка экрана.",
    "corroboration_recapture_threshold": "Текстура лица похожа на пересъёмку.",
    "corroboration_face_reflection": "Блики на лице похожи на экран.",
    "corroboration_color_histogram": "Цвета лица похожи на пересъёмку.",
}

_OPERATOR_ACTION_RU: dict[str, str] = {
    "accept": "Принять.",
    "accept_with_caution": "Принять.",
    "retry_photo": "Новый кадр.",
    "manual_review": "Оператор.",
    "reject": "Отклонить.",
    "wait": "Подождать.",
}

_OPERATOR_ACTION_REASON_RU: dict[str, str] = {
    "scan_pending": "Проверка идёт.",
    "scan_failed_retry_photo": "Кадр не обработался.",
    "presentation_attack_risk": "Похоже на подмену.",
    "accepted_automatically": "Кадр принят.",
    "accepted_with_lower_confidence": "Явной подмены нет.",
    "quality_or_pose_blocks_auto_decision": (
        "Мешает качество или ракурс."
    ),
    "ambiguous_presentation_signals": (
        "Система сомневается."
    ),
    "quality_degraded_retry_photo": (
        "Кадр слабый."
    ),
    "model_signal_missing_retry_photo": (
        "Не все проверки сработали."
    ),
    "insufficient_consensus_for_auto_decision": (
        "Недостаточно уверенности."
    ),
}

_PRESENTATION_ROW_RU: tuple[tuple[str, str], ...] = (
    ("spoof_risk", "Сводный риск по лицу"),
    ("fake_signal_score", "Подмена (модели)"),
    ("face_device_score", "Устройство у лица"),
    ("face_frame_score", "Рамка у лица"),
    ("recapture_score", "Периодика на лице"),
    ("face_reflection_score", "Блики на лице"),
    ("color_hist_score", "Цветовой паттерн лица"),
)

_QUALITY_FLAG_LABEL_RU: dict[str, str] = {
    "quality_blur": "размытие",
    "quality_exposure": "экспозиция",
    "quality_low_contrast": "низкий контраст",
    "quality_small_face": "мелкое лицо",
    "quality_poor": "качество снижено",
}


def _lesson_attendance_tags(obj: LessonAttendance) -> list[str]:
    raw = getattr(obj, "photo_spoof_tags", None)
    if not isinstance(raw, list):
        return []
    return [str(t) for t in raw]


def _is_auto_insufficient_input(obj: LessonAttendance) -> bool:
    """Return whether the stored automatic PAD outcome is insufficient-input review.

    Args:
        obj: LessonAttendance row with ``photo_spoof_tags`` already loaded.

    Returns:
        ``True`` only for ``review`` with the dedicated insufficient-input rule.
    """
    la = LessonAttendance
    if str(getattr(obj, "photo_spoof_status", "") or "") != la.PHOTO_SPOOF_STATUS_REVIEW:
        return False
    return "pad_rule:presentation_insufficient_input_review" in _lesson_attendance_tags(obj)


def _primary_reason_ru(
    obj: LessonAttendance,
    *,
    branch_str: Optional[str],
    status: str,
) -> Optional[str]:
    """Operator-facing reason: persisted ``pad_ui_reason`` first, then branch copy."""
    from monitoring_app.photo_pad import _PAD_UI_REASON_RU
    ui = parse_pad_ui_reason_from_tags(_lesson_attendance_tags(obj))
    if ui:
        return ui
    if branch_str:
        if branch_str in _BRANCH_EXPLANATION_RU:
            return _BRANCH_EXPLANATION_RU[branch_str]
        if branch_str in _PAD_UI_REASON_RU:
            return _PAD_UI_REASON_RU[branch_str]
    if status == LessonAttendance.PHOTO_SPOOF_STATUS_SUSPICIOUS:
        return "Автопроверка: согласованные признаки подмены."
    if status == LessonAttendance.PHOTO_SPOOF_STATUS_REVIEW:
        return "Автопроверка: сигналы неоднозначны — нужна проверка."
    return None


def _humanize_admin_quality_flag(flag: str) -> str:
    """Map a pipeline quality flag to a short Russian phrase for operators.

    Args:
        flag: Raw tag such as ``quality_blur``.

    Returns:
        Human-readable fragment for inline lists.
    """
    t = (flag or "").strip()
    if not t:
        return ""
    return _QUALITY_FLAG_LABEL_RU.get(t, t.replace("_", " ").replace("quality ", ""))


def _lesson_attendance_verdict_pill_class(obj: LessonAttendance) -> str:
    """Return a CSS modifier for the effective verdict pill in admin.

    Args:
        obj: Row with manual verdict and auto spoof status.

    Returns:
        Suffix for ``la-pad-verdict-pill--*`` (without manual/auto distinction in class;
        source text already says ручной/авто).
    """
    la = LessonAttendance
    mv = getattr(obj, "photo_manual_verdict", None)
    if mv == la.PHOTO_MANUAL_VERDICT_CLEAN:
        return "clean"
    if mv == la.PHOTO_MANUAL_VERDICT_SUSPICIOUS:
        return "suspicious"
    st = str(getattr(obj, "photo_spoof_status", "") or "")
    if st == la.PHOTO_SPOOF_STATUS_CLEAN:
        return "clean"
    if st == la.PHOTO_SPOOF_STATUS_SUSPICIOUS:
        return "suspicious"
    if st == la.PHOTO_SPOOF_STATUS_REVIEW and _is_auto_insufficient_input(obj):
        return "insufficient"
    if st == la.PHOTO_SPOOF_STATUS_REVIEW:
        return "review"
    if st == la.PHOTO_SPOOF_STATUS_ERROR:
        return "error"
    if st == la.PHOTO_SPOOF_STATUS_PENDING or not st:
        return "pending"
    return "muted"


def _pct01(x: float) -> str:
    return f"{max(0.0, min(1.0, float(x))) * 100:.1f}%"


def _decision_label_ru(code: str) -> str:
    return {
        "clean": "Норма",
        "insufficient_input_review": "Недостаточно данных",
        "review": "На проверку",
        "suspicious": "Подозрительно",
        "error": "Ошибка",
        "pending": "Ожидает проверки",
    }.get(code, code or "—")


def _effective_verdict_line(obj: LessonAttendance) -> tuple[str, str, str]:
    """Return the short effective verdict tuple for operator UI.

    Args:
        obj: LessonAttendance row with manual and automatic PAD fields.

    Returns:
        Tuple ``(effective_label_ru, source_ru, detail)``.
    """
    la = LessonAttendance
    if obj.photo_manual_verdict == la.PHOTO_MANUAL_VERDICT_CLEAN:
        return (
            "Норма (эффективно)",
            "ручной вердикт оператора",
            "Ручное решение перекрывает автоматическую проверку фото.",
        )
    if obj.photo_manual_verdict == la.PHOTO_MANUAL_VERDICT_SUSPICIOUS:
        return (
            "Подозрительно (эффективно)",
            "ручной вердикт оператора",
            "Ручное решение перекрывает автоматическую проверку фото.",
        )
    if _is_auto_insufficient_input(obj):
        return (
            "Недостаточно данных",
            "автоматическая проверка фото",
            "Системе не хватило качества кадра или пригодной области лица. Это не подозрение на подмену.",
        )
    st = str(obj.photo_spoof_status or "")
    auto = _decision_label_ru(st)
    if st == la.PHOTO_SPOOF_STATUS_SUSPICIOUS:
        return (
            auto,
            "автоматическая проверка фото",
            "Согласованные признаки подмены (модели, блики, цвет лица). Ручная проверка по регламенту.",
        )
    return (
        auto,
        "автоматическая проверка фото",
        "Итог определяется последней автоматической проверкой фото.",
    )


def _humanize_operator_hint(tag: str) -> Optional[SafeString]:
    """Turn a single operator-facing tag into a short Russian line, or None to skip.

    Raw pipeline codes (especially recapture sub-tags) are folded into plain language
    and omitted when they add no information beyond the numeric block above.

    Args:
        tag: Single tag from ``operator_tags`` / filtered PAD tags.

    Returns:
        Safe HTML line or None to omit.
    """
    if not isinstance(tag, str) or not tag.strip():
        return None
    t = tag.strip()
    if t.startswith("device_present:"):
        rest = t.split(":", 1)[1].strip()
        return _html("Устройство в кадре (подсказка детектора): {}", rest)
    if t == "quality_poor":
        return _html(
            "Качество кадра помечено как сниженное (учитывается отдельно от подмены)."
        )
    if t.startswith("frame_present"):
        return None
    if t.startswith("quality_"):
        return _html("Качество: {}", t.replace("_", " "))
    if t == "recapture_fft_periodicity":
        return _html(
            "На лице есть повторяющийся рисунок, похожий на съёмку с экрана."
        )
    if t == "recapture_gradient_aniso":
        return _html(
            "Текстура лица похожа на пересъёмку экрана."
        )
    if t == "recapture_combined":
        return None
    if t == "recapture_blur_dampened":
        return _html(
            "Размытие ослабило проверку текстуры лица."
        )
    if t.startswith("face_color_histogram"):
        return _html(
            "Цвета лица похожи на пересъёмку с экрана или фотографии."
        )
    if t == "guide_ycrcb_luv_model_used":
        return _html("Цветовая модель проверила лицо.")
    if t == "guide_ycrcb_luv_model_elevated":
        return _html("Цветовая модель видит повышенный риск подмены.")
    if t == "guide_ycrcb_luv_model_fake":
        return _html("Цветовая модель считает кадр подменой.")
    if t == "guide_ycrcb_luv_model_unavailable":
        return _html(
            "Цветовая модель недоступна, использован запасной анализ цветов."
        )
    if t == "guide_ycrcb_luv_model_error":
        return _html("Цветовая модель не смогла оценить лицо.")
    if t == "minifasnet_onnx_used":
        return _html("Дополнительная модель проверила лицо.")
    if t == "minifasnet_onnx_elevated":
        return _html("Дополнительная модель видит повышенный риск подмены.")
    if t == "minifasnet_onnx_fake":
        return _html("Дополнительная модель считает кадр подменой.")
    if t == "minifasnet_onnx_unavailable":
        return _html("Дополнительная модель недоступна, этот канал пропущен.")
    if t == "minifasnet_onnx_error":
        return _html("Дополнительная модель не смогла оценить лицо.")
    if t == "minifasnet_onnx_roi_too_small":
        return _html("Лицо слишком маленькое для дополнительной модели.")
    if t == "face_color_luma_chroma_mismatch":
        return _html(
            "Яркость и цвета лица выглядят нетипично для живого кадра."
        )
    return _html("{}", t)


def format_lesson_attendance_antifraud_operator_panel(
    obj: LessonAttendance,
) -> SafeString:
    """Render the primary anti-fraud explanation block for the change form.

    Presents, in order: effective verdict and source, a single prose rule explanation
    (plus optional interpretability notes), numeric presentation cues, background
    policy, non-redundant uncertainty lines, and humanized operator hints.
    Omits raw JSON, ``pad_struct``, and trace dumps.

    Args:
        obj: ``LessonAttendance`` instance (``photo_spoof_tags`` loaded).

    Returns:
        HTML safe string for a ``readonly_fields`` admin renderer.
    """
    if obj is None or not getattr(obj, "pk", None):
        return _html(
            "<p class='la-pad-muted'>Сохраните запись, чтобы увидеть результат проверки фото.</p>"
        )

    diags = diagnostics_payload_for_lesson_attendance(obj)
    decision = diags.get("decision") or {}
    final = str(decision.get("final_decision") or obj.photo_spoof_status or "")
    product_outcome = str(decision.get("product_outcome") or final or "")
    trust = decision.get("trust_confirmed")
    branch = decision.get("decision_branch")
    pc = decision.get("presentation_confidence")
    operator_action = str(decision.get("operator_action") or "").strip()
    operator_action_reason = str(decision.get("operator_action_reason") or "").strip()

    eff_label, eff_source, eff_note = _effective_verdict_line(obj)
    trust_ru = "да" if trust is True else ("нет" if trust is False else "не определено")

    branch_str = branch if isinstance(branch, str) else None
    st_raw = str(obj.photo_spoof_status or final or "")
    is_suspicious = st_raw == LessonAttendance.PHOTO_SPOOF_STATUS_SUSPICIOUS
    primary_reason = _primary_reason_ru(obj, branch_str=branch_str, status=st_raw)

    why_parts: list[SafeString] = []
    if primary_reason:
        why_parts.append(_html("{}", primary_reason))
    unc = diags.get("uncertainty") or {}
    if st_raw != LessonAttendance.PHOTO_SPOOF_STATUS_SUSPICIOUS:
        for code in list(unc.get("interpretability_codes") or []):
            if isinstance(code, str):
                txt = _INTERPRETABILITY_RU.get(code.strip())
                if txt:
                    why_parts.append(_html("{}", txt))

    if not why_parts:
        if final == "pending":
            why_parts.append(
                _html(
                    "Автоматическая проверка ещё не завершена или ожидает перескана."
                )
            )
        else:
            why_parts.append(
                _html(
                    "Сохранённых пояснений по правилу нет — смотрите сигналы по лицу ниже."
                )
            )

    why_parts = why_parts[:1]
    if operator_action and not is_suspicious:
        action_text = _OPERATOR_ACTION_RU.get(operator_action, "Действие: по регламенту.")
        reason_text = _OPERATOR_ACTION_REASON_RU.get(
            operator_action_reason,
            operator_action_reason,
        )
        action_line = (
            f"{action_text} {reason_text}".strip()
            if reason_text
            else action_text
        )
        why_parts.append(_html("{}", action_line))

    pres = diags.get("presentation") or {}
    pres_chips: list[tuple[str, str]] = []
    for key, label_ru in _PRESENTATION_ROW_RU:
        val = pres.get(key)
        if isinstance(val, (int, float)):
            pres_chips.append((label_ru, _pct01(float(val))))

    qual = diags.get("quality") or {}
    q_pen = qual.get("overall_penalty")
    if isinstance(q_pen, (int, float)):
        pres_chips.append(
            ("Качество кадра (отдельно от подмены)", _pct01(float(q_pen)))
        )
    quality_note_html: Optional[SafeString] = None
    if qual.get("is_degraded"):
        flags = qual.get("quality_flags") or []
        if isinstance(flags, list) and flags:
            human_flags = [_humanize_admin_quality_flag(str(f)) for f in flags if f]
            human_flags = [h for h in human_flags if h]
            if human_flags:
                quality_note_html = _html(
                    "Замечания по качеству: {}.",
                    ", ".join(human_flags),
                )

    bg = diags.get("background_context") or {}
    bg_dev = bg.get("background_device_score")
    bg_frm = bg.get("background_frame_score")
    bg_lines: list[SafeString] = []
    if isinstance(bg_dev, (int, float)):
        bg_lines.append(
            _html(
                "Фон — устройство (только контекст, не смешивается с риском по лицу): {}",
                _pct01(float(bg_dev)),
            )
        )
    if isinstance(bg_frm, (int, float)):
        bg_lines.append(
            _html(
                "Фон — рамка по кадру (только контекст): {}",
                _pct01(float(bg_frm)),
            )
        )
    for code in bg.get("context_codes") or []:
        if isinstance(code, str):
            txt = _CONTEXT_RU.get(code)
            if txt:
                bg_lines.append(_html("{}", txt))

    unc_lines: list[SafeString] = []
    for code in unc.get("uncertainty_codes") or []:
        if isinstance(code, str):
            c = code.strip()
            if is_suspicious and c in (
                "trust_indeterminate",
                "outcome_review_recommended",
                "presentation_roi_insufficient",
            ):
                continue
            if (
                c == "outcome_review_recommended"
                and str(final).strip().lower() == "review"
                and branch_str
            ):
                continue
            if is_suspicious and c == "low_image_quality":
                unc_lines.append(
                    _html(
                        "Качество кадра снижено; вердикт опирается на модели и признаки у лица."
                    )
                )
                continue
            txt = _UNCERTAINTY_RU.get(c, c)
            unc_lines.append(_html("{}", txt))
    if is_suspicious and not unc_lines:
        unc_lines.append(
            _html("{}", _UNCERTAINTY_RU["high_presentation_attack_risk"])
        )
    for code in unc.get("missing_signal_codes") or []:
        if code == "fake_model_score":
            unc_lines.append(
                _html("Нет устойчивого балла модели подмены для этого скана.")
            )
        elif isinstance(code, str):
            unc_lines.append(
                _html(
                    "Часть диагностики модели подмены для этого скана недоступна — "
                    "учитывайте осторожность при интерпретации."
                )
            )
    for code in unc.get("conflicting_signal_codes") or []:
        if code == "low_quality_but_high_presentation_alert":
            unc_lines.append(
                _html(
                    "Сочетание: низкое качество при высоком риске презентации — проверьте визуально."
                )
            )
        elif code == "low_quality_but_clean_presentation":
            unc_lines.append(
                _html(
                    "Сочетание: низкое качество при «чистом» презентационном вердикте — "
                    "плохой кадр не доказывает подлинность."
                )
            )
        elif isinstance(code, str):
            unc_lines.append(
                _html(
                    "Есть накладка между оценкой качества и риском подмены — смотрите кадр глазами."
                )
            )

    trace = diags.get("trace") or {}
    support_lines: list[SafeString] = []
    for flag in trace.get("decision_support_flags") or []:
        if isinstance(flag, str):
            if (
                flag == "corroboration_recapture_threshold"
                and isinstance(branch_str, str)
                and branch_str.startswith("recapture_")
            ):
                continue
            txt = _SUPPORT_FLAG_RU.get(flag, flag)
            support_lines.append(_html("{}", txt))

    hints_raw = diags.get("operator_tags") or []
    hint_lines: list[SafeString] = []
    if isinstance(hints_raw, list):
        for tag in hints_raw:
            h = _humanize_operator_hint(str(tag))
            if h is not None:
                hint_lines.append(h)

    conf_line = ""
    if isinstance(pc, (int, float)) and str(final) not in ("error", "pending"):
        conf_line = f"Согласованность сигналов по лицу (не качество кадра): {float(pc) * 100:.0f}%."
        if product_outcome == "review" and float(pc) < 0.48:
            conf_line += " Ниже высокой."

    pill_mod = _lesson_attendance_verdict_pill_class(obj)
    hero = _html(
        "<header class='la-pad-header'>"
        "<div class='la-pad-header__intro'>"
        "<span class='la-pad-verdict-pill la-pad-verdict-pill--{0}'>{1}</span>"
        "<div class='la-pad-header__text'>"
        "<p class='la-pad-header__source'>Источник: <strong>{2}</strong>. {3}</p>"
        "<p class='la-pad-header__trust'>Проверка фото: <strong>{4}</strong></p>"
        "{5}"
        "</div></div></header>",
        pill_mod,
        eff_label,
        eff_source,
        eff_note,
        trust_ru,
        (
            _html("<p class='la-pad-header__conf'>{}</p>", conf_line)
            if conf_line
            else _html("")
        ),
    )

    why_html = _html_join(
        "",
        "<p class='la-pad-prose'>{}</p>",
        ((x,) for x in why_parts),
    )
    chip_cells: list[SafeString] = []
    for lab, val in pres_chips:
        chip_cells.append(
            _html(
                "<div class='la-pad-metric'><span class='la-pad-metric__label'>{}</span>"
                "<span class='la-pad-metric__value'>{}</span></div>",
                lab,
                val,
            )
        )
    pres_block = (
        _html(
            "<div class='la-pad-metric-grid'>{}</div>",
            _html_join("", "{}", ((c,) for c in chip_cells)),
        )
        if chip_cells
        else _html("<p class='la-pad-muted'>Нет сохранённых оценок по лицу.</p>")
    )
    if quality_note_html is not None:
        pres_block = _html(
            "{}{}",
            pres_block,
            _html(
                "<p class='la-pad-prose la-pad-prose--small'>{}</p>", quality_note_html
            ),
        )

    unc_html = (
        _html_join(
            "",
            "<p class='la-pad-prose la-pad-prose--warn'>{}</p>",
            ((x,) for x in unc_lines),
        )
        if unc_lines
        else _html("<p class='la-pad-muted'>Явных предупреждений нет.</p>")
    )

    more_body: list[SafeString] = []
    if support_lines:
        more_body.append(
            _html(
                "<div class='la-pad-more__block'><span class='la-pad-more__label'>Согласованность сигналов</span>{}</div>",
                _html_join(
                    "",
                    "<p class='la-pad-prose la-pad-prose--small'>{}</p>",
                    ((x,) for x in support_lines),
                ),
            )
        )
    if bg_lines:
        more_body.append(
            _html(
                "<div class='la-pad-more__block'><span class='la-pad-more__label'>Контекст кадра</span>{}</div>",
                _html_join(
                    "",
                    "<p class='la-pad-prose la-pad-prose--small'>{}</p>",
                    ((x,) for x in bg_lines),
                ),
            )
        )
    if hint_lines:
        more_body.append(
            _html(
                "<div class='la-pad-more__block'><span class='la-pad-more__label'>Подсказки по кадру</span>{}</div>",
                _html_join(
                    "",
                    "<p class='la-pad-prose la-pad-prose--small'>{}</p>",
                    ((x,) for x in hint_lines),
                ),
            )
        )
    more_html = (
        _html(
            "<details class='la-pad-more'><summary class='la-pad-more__summary'>"
            "Ещё</summary><div class='la-pad-more__inner'>{}</div></details>",
            _html_join("", "{}", ((b,) for b in more_body)),
        )
        if more_body
        else _html("")
    )

    out = _html(
        "<div class='la-pad-review la-pad-panel'>{}"
        "<section class='la-pad-card' aria-labelledby='la-pad-why'>"
        "<h4 id='la-pad-why' class='la-pad-card__title'>Причина</h4>{}</section>"
        "<section class='la-pad-card' aria-labelledby='la-pad-ev'>"
        "<h4 id='la-pad-ev' class='la-pad-card__title'>Основания</h4>{}</section>"
        "<section class='la-pad-card la-pad-card--warn' aria-labelledby='la-pad-un'>"
        "<h4 id='la-pad-un' class='la-pad-card__title'>Неоднозначность</h4>{}</section>"
        "{}"
        "</div>",
        hero,
        why_html,
        pres_block,
        unc_html,
        more_html,
    )
    return out


def format_lesson_attendance_pad_technical_compact(
    obj: LessonAttendance,
) -> SafeString:
    """Render a compact secondary table of PAD metrics and meta for admins.

    Intended for a collapsed fieldset; avoids JSON dumps while still exposing
    numbers for troubleshooting.

    Args:
        obj: Persisted lesson attendance row.

    Returns:
        HTML table safe string.
    """
    if obj is None:
        return _html("")
    diags = diagnostics_payload_for_lesson_attendance(obj)
    rows: list[tuple[str, str]] = []
    rows.append(("Версия модели проверки фото", str(diags.get("model_version") or "—")))
    pres = diags.get("presentation") or {}
    for key, label in _PRESENTATION_ROW_RU:
        v = pres.get(key)
        if isinstance(v, (int, float)):
            rows.append((label, _pct01(float(v))))
    qual = diags.get("quality") or {}
    far = qual.get("face_area_ratio")
    if isinstance(far, (int, float)):
        rows.append(("Доля лица в кадре", _pct01(float(far))))
    qp = qual.get("overall_penalty")
    if isinstance(qp, (int, float)):
        rows.append(("Штраф качества", _pct01(float(qp))))

    inner = _html_join(
        "",
        "<tr><th scope='row' class='la-pad-td-k'>{}</th><td class='la-pad-td-v'>{}</td></tr>",
        ((_html("{}", a), _html("{}", b)) for a, b in rows),
    )
    return _html(
        "<div class='la-pad-tech'><p class='la-pad-tech__lead'>Сводка чисел последнего скана (вторичный блок).</p>"
        "<table class='la-pad-table'><tbody>{}</tbody></table></div>",
        inner,
    )


def format_lesson_attendance_antifraud_list_hint(
    obj: LessonAttendance,
) -> SafeString:
    """One-line anti-fraud hint for the changelist (compact).

    Distinguishes ``review`` after a completed scan (``photo_spoof_checked_at`` set)
    from ``pending`` / missing timestamp so operators do not read orange «на проверку»
    as «PAD не отработал».

    Args:
        obj: Row from the lesson attendance changelist queryset.

    Returns:
        Short HTML snippet.
    """
    if obj is None:
        return _html("—")
    la = LessonAttendance
    if obj.photo_manual_verdict == la.PHOTO_MANUAL_VERDICT_CLEAN:
        return _html(
            "<span class='la-pad-listhint la-pad-listhint--manual'>ручн.: норма</span>"
        )
    if obj.photo_manual_verdict == la.PHOTO_MANUAL_VERDICT_SUSPICIOUS:
        return _html(
            "<span class='la-pad-listhint la-pad-listhint--manual'>ручн.: подозр.</span>"
        )
    st = str(obj.photo_spoof_status or "")
    label = _decision_label_ru(st)
    cls = "la-pad-listhint"
    if st == la.PHOTO_SPOOF_STATUS_SUSPICIOUS:
        cls += " la-pad-listhint--bad"
        return _html("<span class='{}'>авто: {}</span>", cls, label)
    if st == la.PHOTO_SPOOF_STATUS_CLEAN:
        cls += " la-pad-listhint--ok"
        return _html("<span class='{}'>авто: {}</span>", cls, label)
    if st == la.PHOTO_SPOOF_STATUS_PENDING:
        cls += " la-pad-listhint--pending"
        return _html(
            "<span class='{}' title=\"Авто-разбор ещё не записан.\">авто: ожидание</span>",
            cls,
        )
    if st == la.PHOTO_SPOOF_STATUS_REVIEW:
        if _is_auto_insufficient_input(obj):
            cls += " la-pad-listhint--insufficient"
            return _html(
                "<span class='{}' title=\"Системе не хватило usable кадра для авто-вердикта.\">"
                "авто: мало данных ✓</span>",
                cls,
            )
        cls += " la-pad-listhint--review"
        if getattr(obj, "photo_spoof_checked_at", None) is not None:
            return _html(
                "<span class='{}' title=\"Авто-разбор выполнен; «на проверку» — итог правил.\">"
                "авто: на проверку ✓</span>",
                cls,
            )
        return _html(
            "<span class='{}' title=\"Нет времени скана — обновите или пересканируйте.\">"
            "авто: на проверку (?)</span>",
            cls,
        )
    if st == la.PHOTO_SPOOF_STATUS_ERROR:
        cls += " la-pad-listhint--review"
        return _html("<span class='{}'>авто: ошибка проверки фото</span>", cls)
    return _html("<span class='{}'>авто: {}</span>", cls, label)
