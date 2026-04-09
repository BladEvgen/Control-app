from __future__ import annotations

from typing import Optional

from django.utils.html import format_html, format_html_join
from django.utils.safestring import SafeString
from monitoring_app.models import LessonAttendance
from monitoring_app.pad_diagnostics import diagnostics_payload_for_lesson_attendance

_BRANCH_EXPLANATION_RU: dict[str, str] = {
    "fake_quality_poor_review": (
        "FasNet указал на подмену, но качество кадра низкое — нужна ручная "
        "проверка вместо жёсткого автоматического вердикта."
    ),
    "fake_extreme_score_suspicious": "Очень высокий балл FasNet — сильный признак атаки презентации.",
    "fake_plus_face_gated_screen": (
        "Подмена по FasNet и заметные признаки экрана/рамки именно у области лица."
    ),
    "fake_high_plus_suspicious_device_face": "Высокий сигнал подмены и устройство, пересекающееся с лицом.",
    "fake_mid_plus_dual_mid_geometry": (
        "Сигнал FasNet при двух умеренных геометрических каналах у лица (устройство и рамка)."
    ),
    "fake_plus_strong_recapture_corroborated": (
        "Подмена по FasNet подкреплена сильным признаком рекапчера на ROI лица."
    ),
    "fake_mid_plus_background_display_suspicious": (
        "FasNet и сильный экранный контекст по всему кадру — автоматически «подозрительно»."
    ),
    "fake_background_display_review": (
        "FasNet и заметный экранный контекст по всему кадру — требуется проверка, не авто-«норма»."
    ),
    "fake_single_geometry_channel_review": (
        "Устаревшая ветка: раньше «на проверку». Сейчас см. fake_single_mid_geometry_suspicious."
    ),
    "fake_single_mid_geometry_suspicious": (
        "FasNet и одно среднее геометрическое плечо у лица — автоматически «подозрительно»."
    ),
    "fake_low_confidence_no_geometry_clean": (
        "Сигнал FasNet ниже порога для проверки, геометрия экрана у лица слабая — автоматически «норма»."
    ),
    "fake_autonomous_high_without_geometry_suspicious": (
        "Высокий FasNet без средней геометрии у лица — автоматически «подозрительно»."
    ),
    "fake_default_review_not_clean": (
        "FasNet в сомнительной зоне без подкрепления геометрией — автоматического «норма» нет, "
        "но это не сильное доказательство подмены; проверка как запасной путь."
    ),
    "no_fake_dual_suspicious_geometry": (
        "Без FasNet, но сильные признаки устройства и рамки у лица при достаточно крупном лице."
    ),
    "no_fake_dual_geom_small_face_review": (
        "Сильная геометрия при мелком лице — проверка вместо «подозрительно», чтобы снизить ложные срабатывания."
    ),
    "strong_screen_dual_mid_geometry_suspicious": (
        "Сильный экранный паттерн и два умеренных геометрических канала у лица при достаточном размере лица — "
        "автоматически «подозрительно»."
    ),
    "strong_face_gated_screen_review": (
        "Сильный «экранный» паттерн у лица без однозначного спуфа FasNet — проверка."
    ),
    "strong_device_only_face_attack_suspicious": (
        "Сильное устройство у лица без рамки — автоматически «подозрительно»."
    ),
    "recapture_strong_review": (
        "Устаревшая ветка редкой проверки по экстремальной текстуре; в новых сканах см. ветки moiré / single-channel."
    ),
    "recapture_strong_with_context": (
        "Устаревшая ветка; см. recapture_strong_face_geometry_suspicious / "
        "recapture_strong_loose_context_ambiguous_review / recapture_strong_quality_context_review."
    ),
    "recapture_strong_face_geometry_suspicious": (
        "Сильный рекапчер на лице при подкрепляющей геометрии у лица — автоматически «подозрительно»."
    ),
    "recapture_strong_without_face_geometry_clean": (
        "Устаревшая ветка; сейчас см. recapture_strong_loose_context_ambiguous_review."
    ),
    "recapture_strong_loose_context_suspicious": (
        "Устаревшая ветка; сейчас см. recapture_strong_loose_context_ambiguous_review."
    ),
    "recapture_strong_loose_context_ambiguous_review": (
        "Сильная периодика при слабом экранном контексте без жёсткой геометрии — проверка, не авто-«подозрительно»."
    ),
    "recapture_strong_quality_context_review": (
        "Сильный рекапчер при одновременно низком качестве кадра — проверка (качество и текстура вместе неоднозначны)."
    ),
    "recapture_isolated_fft_aniso_corroborated_review": (
        "Устаревшая ветка; см. recapture_isolated_dual_texture_ambiguous_review / moiré clean."
    ),
    "recapture_isolated_dual_texture_uncertain_clean": (
        "Устаревшая ветка; см. recapture_isolated_dual_texture_ambiguous_review или moiré clean."
    ),
    "recapture_isolated_dual_texture_suspicious": (
        "Устаревшая ветка; сейчас см. recapture_isolated_dual_texture_ambiguous_review."
    ),
    "recapture_isolated_dual_texture_ambiguous_review": (
        "FFT и анизотропия на лице при сильной периодике, но FasNet и геометрия спокойны — проверка, не авто-«подозрительно»."
    ),
    "recapture_isolated_extreme_moire_live_uncertain_clean": (
        "Очень высокий рекапчер при двух текстурных каналах и «чистом» качестве — вероятный муар, «норма» без полного подтверждения проверки фото."
    ),
    "recapture_isolated_extreme_single_channel_uncertain_clean": (
        "Экстремальный рекапчер, один текстурный канал — «норма» без полного подтверждения проверки фото."
    ),
    "recapture_isolated_dual_texture_low_rec_uncertain_clean": (
        "Два текстурных канала при рекапчере на нижней границе «сильно» — «норма» без полного подтверждения проверки фото."
    ),
    "recapture_isolated_single_cue_texture_clean": (
        "Повышенная периодика на лице без второго текстурного канала и без экранной геометрии — "
        "автоматически «норма» без полного подтверждения проверки фото."
    ),
    "recapture_isolated_below_review_bar_clean": (
        "Устаревшая ветка: ранее «ниже порога изоляции»; в новых сканах см. "
        "recapture_isolated_single_cue_texture_clean."
    ),
    "recapture_mid_with_context": (
        "Устаревшая ветка: раньше «проверка». Сейчас — либо «подозрительно» при сильной геометрии, либо «норма»."
    ),
    "recapture_mid_with_suspicious_context_suspicious": (
        "Умеренный рекапчер на лице при подозрительной геометрии устройства или рамки — автоматически «подозрительно»."
    ),
    "recapture_mid_weak_geometry_clean": (
        "Умеренный рекапчер при слабой геометрии у лица — «норма» без полного подтверждения проверки фото."
    ),
    "spoof_model_uncertain_low_recapture_clean": (
        "FasNet недоступен, рекапчер слабый — автоматически «норма» с пониженной уверенностью."
    ),
    "recapture_with_spoof_model_uncertain": (
        "Устаревшая ветка: раньше проверка при недоступном FasNet и среднем рекапчере. "
        "Сейчас см. spoof_model_uncertain_recapture_uncertain_clean и "
        "spoof_uncertain_texture_ambiguous_review."
    ),
    "spoof_model_uncertain_recapture_uncertain_clean": (
        "FasNet недоступен; рекапчер заметен, но без порога сильной текстуры — «норма» с пониженной уверенностью."
    ),
    "spoof_uncertain_strong_recapture_texture_suspicious": (
        "Устаревшая ветка; сейчас см. spoof_uncertain_texture_ambiguous_review."
    ),
    "spoof_uncertain_texture_ambiguous_review": (
        "FasNet недоступен; сильная периодика с текстурным подтверждением без спокойной геометрии — проверка."
    ),
    "quality_poor_with_face_gated_screen": (
        "Низкое качество и слабые «экранные» признаки у лица — проверка (качество ≠ подделка)."
    ),
    "image_quality_degraded_review": (
        "Сильно снижено качество или есть слабые признаки презентации — нужна ручная проверка."
    ),
    "image_quality_low_review": (
        "Устаревшая ветка: низкое качество без достаточных признаков подмены — проверка "
        "(в новых сканах используется image_quality_degraded_review / image_quality_uncertain_clean)."
    ),
    "image_quality_uncertain_clean": (
        "Качество снижено умеренно, явных признаков подмены по лицу нет — «норма» без полного авто-доверия к проверке фото."
    ),
    "no_fake_recapture_strong_corroborated_dual_geometry": (
        "Сильный рекапчер при двух подозрительных геометрических каналах у лица — «подозрительно»."
    ),
    "no_fake_recapture_strong_dual_geometry_small_face_review": (
        "Сильный рекапчер и геометрия при мелком лице — проверка."
    ),
    "spoof_model_uncertain_weak_face_geometry": (
        "Нет ответа FasNet; слабая геометрия у лица — проверка."
    ),
    "spoof_model_uncertain_clean_fallback": (
        "Нет ответа FasNet; остальные сигналы слабые — осторожный допуск «норма»."
    ),
    "weak_face_gated_combined_review": (
        "Слабая комбинация признаков у лица (ниже порога «подозрительно») — проверка."
    ),
    "shield_weak_geometry_clean": (
        "Сработала защита «обычный живой» кадр: слабая геометрия без сильной подмены и с приемлемым качеством."
    ),
    "default_clean": "Значимых признаков подмены по лицу не зафиксировано.",
    "presentation_insufficient_input_review": (
        "Кадр или область лица недостаточны для уверенного вердикта по текстуре/периодике — "
        "нужна ручная проверка вместо авто-«подозрительно» или авто-«норма»."
    ),
}

_INTERPRETABILITY_RU: dict[str, str] = {
    "review_primarily_face_texture_periodicity": (
        "Итог в основном опирается на текстуру/периодику в области лица; FasNet и геометрия "
        "экрана у лица почти не участвовали — не трактуйте это как жёсткое доказательство."
    ),
    "texture_fft_and_anisotropy_both_elevated": (
        "Два текстурных канала (FFT и направленность градиентов) согласованы — основание сильнее, "
        "чем у одного шумного признака."
    ),
    "liveness_model_signal_weak_not_strong_proof": (
        "Сигнал FasNet в зоне сомнений — это не сильное доказательство подмены, решение осторожное."
    ),
    "single_texture_channel_downweighted_automatic_clean": (
        "Один текстурный канал без подкрепления — автоматически «норма»."
    ),
    "fasnet_below_review_threshold_auto_cleared": (
        "Балл FasNet не дотягивает до порога «проверка» и нет средней геометрии — автоматический допуск «норма»."
    ),
    "recapture_mid_downgraded_no_suspicious_geometry": (
        "Рекапчер умеренный, геометрия экрана у лица не на уровне «подозрительно» — автоматически «норма»."
    ),
    "spoof_model_missing_low_recapture_auto_cleared": (
        "Модель подмены недоступна, текстурный сигнал слабый — автоматически «норма»."
    ),
    "presentation_roi_unreliable_for_attack_verdict": (
        "Область лица или качество кадра не позволяют трактовать текстуру как доказательство подмены — "
        "нужен визуальный осмотр."
    ),
}

_UNCERTAINTY_RU: dict[str, str] = {
    "trust_indeterminate": "Автоматическое подтверждение проверки фото не выставлено.",
    "low_image_quality": "Качество изображения снижено — учитывается отдельно от атаки презентации.",
    "fake_model_unavailable": "Модель FasNet недоступна или завершилась ошибкой.",
    "outcome_review_recommended": "По правилам автоматической проверки фото рекомендуется ручная проверка.",
    "high_presentation_attack_risk": "Высокий риск атаки презентации по согласованным сигналам у лица.",
    "presentation_roi_insufficient": (
        "Область лица или качество кадра недостаточны для автоматического вердикта по этим сигналам."
    ),
}

_CONTEXT_RU: dict[str, str] = {
    "background_scores_excluded_from_presentation_risk": (
        "Оценки устройства/рамки по всему кадру не входят в сводный риск подмены по лицу."
    ),
    "face_gated_geometry_required_for_suspicious": (
        "Для «подозрительно» используются сигналы, привязанные к области лица."
    ),
}

_SUPPORT_FLAG_RU: dict[str, str] = {
    "shield_normal_live_active": "Сработала защита от ложных срабатываний на слабой геометрии при живом кадре.",
    "corroboration_fasnet_fake": "В корреляции учтён сигнал FasNet о подмене.",
    "corroboration_mid_device": "В корреляции: средний уровень «устройство у лица».",
    "corroboration_mid_frame": "В корреляции: средний уровень «рамка у лица».",
    "corroboration_recapture_threshold": "В корреляции: рекапчер достиг порога подтверждения.",
}

_PRESENTATION_ROW_RU: tuple[tuple[str, str], ...] = (
    ("spoof_risk", "Сводный риск по лицу"),
    ("fake_signal_score", "Подмена (FasNet)"),
    ("face_device_score", "Устройство у лица"),
    ("face_frame_score", "Рамка у лица"),
    ("recapture_score", "Периодика на лице"),
)

_QUALITY_FLAG_LABEL_RU: dict[str, str] = {
    "quality_blur": "размытие",
    "quality_exposure": "экспозиция",
    "quality_low_contrast": "низкий контраст",
    "quality_small_face": "мелкое лицо",
    "quality_poor": "качество снижено",
}


def _is_auto_insufficient_input(obj: LessonAttendance) -> bool:
    """Return whether the stored automatic PAD outcome is insufficient-input review.

    Args:
        obj: LessonAttendance row with ``photo_spoof_tags`` already loaded.

    Returns:
        ``True`` when the latest automatic PAD result is the distinct
        insufficient-input review class.
    """
    tags = getattr(obj, "photo_spoof_tags", None)
    if not isinstance(tags, list):
        return False
    return "pad_rule:presentation_insufficient_input_review" in tags


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
    auto = _decision_label_ru(str(obj.photo_spoof_status or ""))
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
        return format_html("Устройство в кадре (подсказка детектора): {}", rest)
    if t == "quality_poor":
        return format_html(
            "Качество кадра помечено как сниженное (учитывается отдельно от подмены)."
        )
    if t.startswith("frame_present"):
        return None
    if t.startswith("quality_"):
        return format_html("Качество: {}", t.replace("_", " "))
    if t == "recapture_fft_periodicity":
        return format_html(
            "Техн. подсказка: заметная периодика в спектре (FFT) на внутреннем ROI лица."
        )
    if t == "recapture_gradient_aniso":
        return format_html(
            "Техн. подсказка: преобладание горизонтальных или вертикальных градиентов на лице."
        )
    if t == "recapture_combined":
        return None
    if t == "recapture_blur_dampened":
        return format_html(
            "Техн. подсказка: текстурные метрики ослаблены из‑за размытия кропа лица."
        )
    return format_html("{}", t)


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
        return format_html(
            "<p class='la-pad-muted'>Сохраните запись, чтобы увидеть результат проверки фото.</p>"
        )

    diags = diagnostics_payload_for_lesson_attendance(obj)
    decision = diags.get("decision") or {}
    final = str(decision.get("final_decision") or obj.photo_spoof_status or "")
    product_outcome = str(decision.get("product_outcome") or final or "")
    trust = decision.get("trust_confirmed")
    branch = decision.get("decision_branch")
    pc = decision.get("presentation_confidence")

    eff_label, eff_source, eff_note = _effective_verdict_line(obj)
    trust_ru = "да" if trust is True else ("нет" if trust is False else "не определено")

    why_parts: list[SafeString] = []
    branch_str = branch if isinstance(branch, str) else None
    if branch_str:
        expl = _BRANCH_EXPLANATION_RU.get(branch_str)
        if expl:
            why_parts.append(format_html("{}", expl))
    unc = diags.get("uncertainty") or {}
    for code in list(unc.get("interpretability_codes") or []):
        if isinstance(code, str):
            txt = _INTERPRETABILITY_RU.get(code.strip())
            if txt:
                why_parts.append(format_html("{}", txt))

    if not why_parts:
        if final == "pending":
            why_parts.append(
                format_html(
                    "Автоматическая проверка ещё не завершена или ожидает перескана."
                )
            )
        else:
            why_parts.append(
                format_html(
                    "Сохранённых пояснений по правилу нет — смотрите сигналы по лицу ниже."
                )
            )

    why_parts = why_parts[:1]

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
                quality_note_html = format_html(
                    "Замечания по качеству: {}.",
                    ", ".join(human_flags),
                )

    bg = diags.get("background_context") or {}
    bg_dev = bg.get("background_device_score")
    bg_frm = bg.get("background_frame_score")
    bg_lines: list[SafeString] = []
    if isinstance(bg_dev, (int, float)):
        bg_lines.append(
            format_html(
                "Фон — устройство (только контекст, не смешивается с риском по лицу): {}",
                _pct01(float(bg_dev)),
            )
        )
    if isinstance(bg_frm, (int, float)):
        bg_lines.append(
            format_html(
                "Фон — рамка по кадру (только контекст): {}",
                _pct01(float(bg_frm)),
            )
        )
    for code in bg.get("context_codes") or []:
        if isinstance(code, str):
            txt = _CONTEXT_RU.get(code)
            if txt:
                bg_lines.append(format_html("{}", txt))

    unc_lines: list[SafeString] = []
    for code in unc.get("uncertainty_codes") or []:
        if isinstance(code, str):
            c = code.strip()
            if (
                c == "outcome_review_recommended"
                and str(final).strip().lower() == "review"
                and branch_str
            ):
                continue
            txt = _UNCERTAINTY_RU.get(c, c)
            unc_lines.append(format_html("{}", txt))
    for code in unc.get("missing_signal_codes") or []:
        if code == "fake_model_score":
            unc_lines.append(
                format_html("Нет устойчивого балла FasNet для этого скана.")
            )
        elif isinstance(code, str):
            unc_lines.append(
                format_html(
                    "Часть диагностики модели подмены для этого скана недоступна — "
                    "учитывайте осторожность при интерпретации."
                )
            )
    for code in unc.get("conflicting_signal_codes") or []:
        if code == "low_quality_but_high_presentation_alert":
            unc_lines.append(
                format_html(
                    "Сочетание: низкое качество при высоком риске презентации — проверьте визуально."
                )
            )
        elif code == "low_quality_but_clean_presentation":
            unc_lines.append(
                format_html(
                    "Сочетание: низкое качество при «чистом» презентационном вердикте — "
                    "плохой кадр не доказывает подлинность."
                )
            )
        elif isinstance(code, str):
            unc_lines.append(
                format_html(
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
            support_lines.append(format_html("{}", txt))

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
    hero = format_html(
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
            format_html("<p class='la-pad-header__conf'>{}</p>", conf_line)
            if conf_line
            else format_html("")
        ),
    )

    why_html = format_html_join(
        "",
        "<p class='la-pad-prose'>{}</p>",
        ((x,) for x in why_parts),
    )
    chip_cells: list[SafeString] = []
    for lab, val in pres_chips:
        chip_cells.append(
            format_html(
                "<div class='la-pad-metric'><span class='la-pad-metric__label'>{}</span>"
                "<span class='la-pad-metric__value'>{}</span></div>",
                lab,
                val,
            )
        )
    pres_block = (
        format_html(
            "<div class='la-pad-metric-grid'>{}</div>",
            format_html_join("", "{}", ((c,) for c in chip_cells)),
        )
        if chip_cells
        else format_html("<p class='la-pad-muted'>Нет сохранённых оценок по лицу.</p>")
    )
    if quality_note_html is not None:
        pres_block = format_html(
            "{}{}",
            pres_block,
            format_html(
                "<p class='la-pad-prose la-pad-prose--small'>{}</p>", quality_note_html
            ),
        )

    unc_html = (
        format_html_join(
            "",
            "<p class='la-pad-prose la-pad-prose--warn'>{}</p>",
            ((x,) for x in unc_lines),
        )
        if unc_lines
        else format_html("<p class='la-pad-muted'>Явных предупреждений нет.</p>")
    )

    more_body: list[SafeString] = []
    if support_lines:
        more_body.append(
            format_html(
                "<div class='la-pad-more__block'><span class='la-pad-more__label'>Согласованность сигналов</span>{}</div>",
                format_html_join(
                    "",
                    "<p class='la-pad-prose la-pad-prose--small'>{}</p>",
                    ((x,) for x in support_lines),
                ),
            )
        )
    if bg_lines:
        more_body.append(
            format_html(
                "<div class='la-pad-more__block'><span class='la-pad-more__label'>Контекст кадра</span>{}</div>",
                format_html_join(
                    "",
                    "<p class='la-pad-prose la-pad-prose--small'>{}</p>",
                    ((x,) for x in bg_lines),
                ),
            )
        )
    if hint_lines:
        more_body.append(
            format_html(
                "<div class='la-pad-more__block'><span class='la-pad-more__label'>Подсказки по кадру</span>{}</div>",
                format_html_join(
                    "",
                    "<p class='la-pad-prose la-pad-prose--small'>{}</p>",
                    ((x,) for x in hint_lines),
                ),
            )
        )
    more_html = (
        format_html(
            "<details class='la-pad-more'><summary class='la-pad-more__summary'>"
            "Ещё</summary><div class='la-pad-more__inner'>{}</div></details>",
            format_html_join("", "{}", ((b,) for b in more_body)),
        )
        if more_body
        else format_html("")
    )

    out = format_html(
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
        return format_html("")
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

    inner = format_html_join(
        "",
        "<tr><th scope='row' class='la-pad-td-k'>{}</th><td class='la-pad-td-v'>{}</td></tr>",
        ((format_html("{}", a), format_html("{}", b)) for a, b in rows),
    )
    return format_html(
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
        return format_html("—")
    la = LessonAttendance
    if obj.photo_manual_verdict == la.PHOTO_MANUAL_VERDICT_CLEAN:
        return format_html(
            "<span class='la-pad-listhint la-pad-listhint--manual'>ручн.: норма</span>"
        )
    if obj.photo_manual_verdict == la.PHOTO_MANUAL_VERDICT_SUSPICIOUS:
        return format_html(
            "<span class='la-pad-listhint la-pad-listhint--manual'>ручн.: подозр.</span>"
        )
    st = str(obj.photo_spoof_status or "")
    label = _decision_label_ru(st)
    cls = "la-pad-listhint"
    if st == la.PHOTO_SPOOF_STATUS_SUSPICIOUS:
        cls += " la-pad-listhint--bad"
        return format_html("<span class='{}'>авто: {}</span>", cls, label)
    if st == la.PHOTO_SPOOF_STATUS_CLEAN:
        cls += " la-pad-listhint--ok"
        return format_html("<span class='{}'>авто: {}</span>", cls, label)
    if st == la.PHOTO_SPOOF_STATUS_PENDING:
        cls += " la-pad-listhint--pending"
        return format_html(
            "<span class='{}' title=\"Авто-разбор ещё не записан.\">авто: ожидание</span>",
            cls,
        )
    if st == la.PHOTO_SPOOF_STATUS_REVIEW:
        if _is_auto_insufficient_input(obj):
            cls += " la-pad-listhint--insufficient"
            return format_html(
                "<span class='{}' title=\"Системе не хватило usable кадра для авто-вердикта.\">"
                "авто: мало данных ✓</span>",
                cls,
            )
        cls += " la-pad-listhint--review"
        if getattr(obj, "photo_spoof_checked_at", None) is not None:
            return format_html(
                "<span class='{}' title=\"Авто-разбор выполнен; «на проверку» — итог правил.\">"
                "авто: на проверку ✓</span>",
                cls,
            )
        return format_html(
            "<span class='{}' title=\"Нет времени скана — обновите или пересканируйте.\">"
            "авто: на проверку (?)</span>",
            cls,
        )
    if st == la.PHOTO_SPOOF_STATUS_ERROR:
        cls += " la-pad-listhint--review"
        return format_html("<span class='{}'>авто: ошибка проверки фото</span>", cls)
    return format_html("<span class='{}'>авто: {}</span>", cls, label)
