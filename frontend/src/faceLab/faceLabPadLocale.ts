import { humanizeApiTokenString, humanizePadTag } from "./faceLabHumanMessages";
import type { PadDiagnosticsPayload } from "./faceLabPadTypes";

const BRANCH_SUMMARY_RU: Record<string, string> = {
  fake_quality_poor_review:
    "FasNet указывает на подмену, но кадр низкого качества — нужна ручная проверка.",
  fake_extreme_score_suspicious:
    "Очень высокий балл FasNet — сильный признак подмены.",
  fake_plus_face_gated_screen:
    "FasNet и заметные признаки экрана/рамки именно у лица.",
  fake_high_plus_suspicious_device_face:
    "Высокий сигнал подмены и устройство, пересекающееся с лицом.",
  fake_mid_plus_dual_mid_geometry:
    "FasNet и два умеренных геометрических канала у лица (устройство и рамка).",
  fake_plus_strong_recapture_corroborated:
    "FasNet подкреплён сильной периодикой на лице.",
  fake_mid_plus_background_display_suspicious:
    "FasNet и сильный экранный контекст по всему кадру — «подозрительно».",
  fake_background_display_review:
    "FasNet и заметный экранный контекст по всему кадру — нужна проверка, но не «норма».",
  fake_single_geometry_channel_review:
    "Устаревшая ветка; сейчас: fake_single_mid_geometry_suspicious.",
  fake_single_mid_geometry_suspicious:
    "FasNet и одно среднее геометрическое плечо у лица — автоматически «подозрительно».",
  fake_low_confidence_no_geometry_clean:
    "FasNet ниже порога проверки, геометрия слабая — «норма».",
  fake_autonomous_high_without_geometry_suspicious:
    "Высокий FasNet без средней геометрии у лица — автоматически «подозрительно».",
  fake_default_review_not_clean:
    "FasNet в сомнительной зоне без геометрии — без авто-«норма»; не жёсткое доказательство.",
  no_fake_dual_suspicious_geometry:
    "Без FasNet, но сильные устройство и рамка у лица при крупном лице.",
  no_fake_dual_geom_small_face_review:
    "Сильная геометрия при мелком лице — проверка вместо «подозрительно».",
  strong_screen_dual_mid_geometry_suspicious:
    "Сильный экранный паттерн и два умеренных канала у лица — «подозрительно».",
  strong_face_gated_screen_review:
    "Сильный «экранный» паттерн у лица без однозначного FasNet — проверка.",
  strong_device_only_face_attack_suspicious:
    "Сильное устройство у лица без рамки — «подозрительно».",
  recapture_strong_review:
    "Устаревшая ветка; в новых сканах см. изолированные ветки (муар / один канал / двойная текстура).",
  recapture_strong_with_context:
    "Устаревшая ветка; см. recapture_strong_face_geometry_suspicious, recapture_strong_loose_context_ambiguous_review, recapture_strong_quality_context_review.",
  recapture_strong_face_geometry_suspicious:
    "Сильная периодика на лице при подкрепляющей геометрии — «подозрительно».",
  recapture_strong_without_face_geometry_clean:
    "Устаревшая ветка; сейчас см. recapture_strong_loose_context_ambiguous_review.",
  recapture_strong_loose_context_suspicious:
    "Устаревшая ветка; сейчас см. recapture_strong_loose_context_ambiguous_review.",
  recapture_strong_loose_context_ambiguous_review:
    "Сильная периодика при слабом экранном контексте — на проверку (без авто-«подозрительно»).",
  recapture_strong_quality_context_review:
    "Сильная периодика и низкое качество кадра — проверка.",
  recapture_isolated_fft_aniso_corroborated_review:
    "Устаревшая ветка; см. recapture_isolated_dual_texture_ambiguous_review или муар-«норма».",
  recapture_isolated_dual_texture_uncertain_clean:
    "Устаревшая ветка; см. recapture_isolated_dual_texture_ambiguous_review или муар-«норма».",
  recapture_isolated_dual_texture_suspicious:
    "Устаревшая ветка; сейчас см. recapture_isolated_dual_texture_ambiguous_review.",
  recapture_isolated_dual_texture_ambiguous_review:
    "FFT и анизотропия при сильной периодике без FasNet/геометрии — на проверку, не «подозрительно».",
  recapture_isolated_extreme_moire_live_uncertain_clean:
    "Очень высокая периодика, два текстурных канала и «чистое» качество — вероятный муар, «норма» без полного подтверждения проверки фото.",
  recapture_isolated_extreme_single_channel_uncertain_clean:
    "Экстремальная периодика, один текстурный канал — «норма» без полного подтверждения проверки фото.",
  recapture_isolated_dual_texture_low_rec_uncertain_clean:
    "Два текстурных канала на нижней границе «сильно» — «норма» без полного подтверждения проверки фото.",
  recapture_isolated_single_cue_texture_clean:
    "Один текстурный канал без второго и без экранной геометрии — «норма» без полного подтверждения проверки фото.",
  recapture_mid_with_context:
    "Устаревшая ветка; см. recapture_mid_with_suspicious_context_suspicious или recapture_mid_weak_geometry_clean.",
  recapture_mid_with_suspicious_context_suspicious:
    "Умеренная периодика и подозрительная геометрия у лица — «подозрительно».",
  recapture_mid_weak_geometry_clean:
    "Умеренная периодика при слабой геометрии — «норма» без полного подтверждения проверки фото.",
  spoof_model_uncertain_low_recapture_clean:
    "FasNet недоступен, периодика слабая — «норма» с пониженной уверенностью.",
  recapture_with_spoof_model_uncertain:
    "Устаревшая ветка; см. spoof_model_uncertain_recapture_uncertain_clean или spoof_uncertain_texture_ambiguous_review.",
  spoof_model_uncertain_recapture_uncertain_clean:
    "FasNet недоступен; периодика заметна, но без сильной текстуры — «норма» с пониженной уверенностью.",
  spoof_uncertain_strong_recapture_texture_suspicious:
    "Устаревшая ветка; см. spoof_uncertain_texture_ambiguous_review.",
  spoof_uncertain_texture_ambiguous_review:
    "FasNet недоступен; сильная периодика и текстура — на проверку.",
  quality_poor_with_face_gated_screen:
    "Низкое качество и слабые «экранные» признаки у лица — проверка.",
  image_quality_low_review: "Низкое качество без признаков подмены — проверка.",
  image_quality_degraded_review:
    "Сильно снижено качество или слабые признаки презентации — проверка.",
  image_quality_uncertain_clean:
    "Качество снижено умеренно, признаков подмены по лицу нет — «норма» без полного доверия к проверке фото.",
  no_fake_recapture_strong_corroborated_dual_geometry:
    "Сильная периодика и две подозрительные геометрии у лица — «подозрительно».",
  no_fake_recapture_strong_dual_geometry_small_face_review:
    "Сильная периодика и геометрия при мелком лице — проверка.",
  spoof_model_uncertain_weak_face_geometry:
    "Нет FasNet; слабая геометрия — проверка.",
  spoof_model_uncertain_clean_fallback:
    "Нет FasNet; остальные сигналы слабые — осторожный «норма».",
  weak_face_gated_combined_review:
    "Слабая комбинация признаков у лица — проверка.",
  shield_weak_geometry_clean:
    "Защита «обычный живой» кадр при слабой геометрии без сильной подмены.",
  default_clean: "Признаков подмены по лицу нет; фон в вердикт не входит.",
  presentation_insufficient_input_review:
    "Лицо в кадре или качество ROI недостаточны для авто-вердикта по текстуре — нужна ручная проверка.",
};

const INTERPRETABILITY_CODE_RU: Record<string, string> = {
  review_primarily_face_texture_periodicity:
    "Итог в основном от текстуры лица; FasNet и геометрия почти не участвовали.",
  texture_fft_and_anisotropy_both_elevated:
    "Два текстурных канала согласованы — основание сильнее одного шумного признака.",
  liveness_model_signal_weak_not_strong_proof:
    "Сигнал FasNet слабый — не жёсткое доказательство подмены.",
  single_texture_channel_downweighted_automatic_clean:
    "Один текстурный канал без подкрепления — автоматически «норма».",
  fasnet_below_review_threshold_auto_cleared:
    "FasNet ниже порога проверки без средней геометрии — «норма».",
  recapture_mid_downgraded_no_suspicious_geometry:
    "Периодика умеренная, геометрия не «подозрительная» — «норма».",
  spoof_model_missing_low_recapture_auto_cleared:
    "Нет FasNet, слабая периодика — «норма».",
  isolated_dual_texture_auto_cleared_without_geometry:
    "Устаревшее пояснение; см. актуальную ветку решения выше.",
  presentation_roi_unreliable_for_attack_verdict:
    "ROI лица или качество не позволяют считать текстуру доказательством подмены — нужен осмотр.",
};

const UNCERTAINTY_CODE_RU: Record<string, string> = {
  trust_indeterminate:
    "Автоматическое подтверждение проверки фото не выставлено (итог неоднозначен).",
  low_image_quality:
    "Снижено качество изображения — это отдельно от оценки атаки презентации.",
  fake_model_unavailable:
    "Модель FasNet недоступна или завершилась ошибкой — снижена уверенность.",
  outcome_review_recommended: "Рекомендуется ручная проверка.",
  high_presentation_attack_risk:
    "Высокий риск атаки презентации по согласованным сигналам у лица.",
  presentation_roi_insufficient:
    "Недостаточно данных по лицу для авто-вердикта — нужен осмотр.",
};

const CONTEXT_CODE_RU: Record<string, string> = {
  background_scores_excluded_from_presentation_risk:
    "Оценки устройства/рамки по всему кадру не смешиваются с риском подмены по лицу.",
  face_gated_geometry_required_for_suspicious:
    "Для «подозрительно» требуются сигналы, привязанные к области лица.",
};

const SUPPORT_FLAG_RU: Record<string, string> = {
  shield_normal_live_active:
    "Сработала защита от ложных срабатываний на слабой геометрии при живом кадре.",
  corroboration_fasnet_fake: "В короборации учтён сигнал FasNet о подмене.",
  corroboration_mid_device:
    "В короборации: средний уровень сигнала «устройство у лица».",
  corroboration_mid_frame:
    "В короборации: средний уровень сигнала «рамка у лица».",
  corroboration_recapture_threshold:
    "В короборации: рекапчер на лице достиг порога подтверждения.",
};

const PRESENTATION_METRIC_LABEL_RU: Record<string, string> = {
  spoof_risk: "Сводный риск по лицу",
  fake_signal_score: "FasNet (подмена)",
  face_device_score: "Устройство у лица",
  face_frame_score: "Рамка у лица",
  recapture_score: "Периодика на лице",
};

const QUALITY_METRIC_LABEL_RU: Record<string, string> = {
  overall_penalty: "Качество кадра (отдельно от подмены)",
  face_area_ratio: "Доля лица в кадре",
};

const QUALITY_FLAG_RU: Record<string, string> = {
  quality_blur: "размытие",
  quality_exposure: "экспозиция",
  quality_low_contrast: "низкий контраст",
  quality_small_face: "мелкое лицо",
  quality_poor: "сниженное качество",
};

export type PadEvidenceChip = {
  key: string;
  label: string;
  value: string;
};

export type PadDevDetailRow = { label: string; value: string };

function decisionHeadlineRu(d: PadDiagnosticsPayload): string {
  const outcome =
    d.decision?.product_outcome ?? d.decision?.final_decision ?? "";
  const st = d.decision?.final_decision ?? "";
  const trust = d.decision?.trust_confirmed;
  if (outcome === "insufficient_input_review") {
    return "Недостаточно данных: система не получила достаточно чёткое лицо для авто-вердикта.";
  }
  if (st === "clean" && trust === true) {
    return "Норма: проверка фото пройдена автоматически.";
  }
  if (st === "clean" && trust === null) {
    return "Норма по признакам подмены; проверка фото без полного подтверждения — см. блок неопределённости.";
  }
  if (st === "suspicious") {
    return "Подозрительно: сильные согласованные признаки у лица.";
  }
  if (st === "review") {
    return "На проверку: автоматического достаточного итога нет.";
  }
  if (st === "error") {
    return "Ошибка или нет лица для проверки.";
  }
  return "Итог не определён — при необходимости повторите анализ.";
}

function trustLabelRu(trust: boolean | null | undefined): string {
  if (trust === true) return "да";
  if (trust === false) return "нет";
  return "не определено";
}

function branchExplanationRu(branch: string | undefined): string | null {
  if (!branch) return null;
  return BRANCH_SUMMARY_RU[branch] ?? null;
}

/** Ordered presentation keys for the evidence chip grid. */
const PRESENTATION_KEYS: (keyof NonNullable<
  PadDiagnosticsPayload["presentation"]
>)[] = [
  "spoof_risk",
  "fake_signal_score",
  "face_device_score",
  "face_frame_score",
  "recapture_score",
];

/**
 * Builds compact metric chips for the primary Face Lab UI (human labels only).
 *
 * Args:
 *     d: PAD diagnostics payload.
 *
 * Returns:
 *     Chip descriptors with short percentage values.
 */
export function buildPadEvidenceChips(
  d: PadDiagnosticsPayload,
): PadEvidenceChip[] {
  const out: PadEvidenceChip[] = [];
  const p = d.presentation;
  if (p) {
    for (const k of PRESENTATION_KEYS) {
      const v = p[k];
      if (typeof v === "number" && Number.isFinite(v)) {
        out.push({
          key: String(k),
          label:
            PRESENTATION_METRIC_LABEL_RU[String(k)] ?? "Показатель по лицу",
          value: `${(v * 100).toFixed(0)}%`,
        });
      }
    }
  }
  const q = d.quality;
  if (q) {
    if (
      typeof q.overall_penalty === "number" &&
      Number.isFinite(q.overall_penalty)
    ) {
      out.push({
        key: "overall_penalty",
        label: QUALITY_METRIC_LABEL_RU.overall_penalty,
        value: `${(q.overall_penalty * 100).toFixed(0)}%`,
      });
    }
    if (
      typeof q.face_area_ratio === "number" &&
      Number.isFinite(q.face_area_ratio)
    ) {
      out.push({
        key: "face_area_ratio",
        label: QUALITY_METRIC_LABEL_RU.face_area_ratio,
        value: `${(q.face_area_ratio * 100).toFixed(1)}%`,
      });
    }
  }
  return out;
}

/**
 * Builds rows for the collapsed technical section (no JSON, no raw contract keys as values).
 *
 * Args:
 *     d: PAD diagnostics payload.
 *
 * Returns:
 *     Label/value pairs in Russian for operators who expand «Техническая информация».
 */
export function buildPadDevDetailRows(
  d: PadDiagnosticsPayload,
): PadDevDetailRow[] {
  const rows: PadDevDetailRow[] = [];
  const branch = d.decision?.decision_branch?.trim();
  if (branch) {
    const prose = BRANCH_SUMMARY_RU[branch];
    rows.push({
      label: "Логика решения",
      value: prose ?? "Описание для этой ветки ещё не добавлено.",
    });
  }
  if (typeof d.model_version === "string" && d.model_version.trim()) {
    rows.push({ label: "Версия проверки фото", value: d.model_version.trim() });
  }
  if (typeof d.elapsed_ms === "number" && Number.isFinite(d.elapsed_ms)) {
    rows.push({
      label: "Время анализа на сервере",
      value: `${Math.round(d.elapsed_ms)} мс`,
    });
  }
  const flags = d.trace?.decision_support_flags ?? [];
  if (flags.length > 0) {
    const parts = flags.map((f) => SUPPORT_FLAG_RU[f] ?? "").filter(Boolean);
    if (parts.length > 0) {
      rows.push({
        label: "Согласованность сигналов",
        value: parts.join(" · "),
      });
    }
  }
  const ruleCodes = d.trace?.rule_codes ?? [];
  if (ruleCodes.length > 0) {
    rows.push({
      label: "Внутренние пометки правил",
      value: ruleCodes
        .map((c) => humanizeApiTokenString(String(c)))
        .join(" · "),
    });
  }
  const evidenceCodes = d.trace?.evidence_codes ?? [];
  if (evidenceCodes.length > 0) {
    rows.push({
      label: "Внутренние пометки доказательств",
      value: evidenceCodes
        .map((c) => humanizeApiTokenString(String(c)))
        .join(" · "),
    });
  }
  const schema = d.trace?.pad_trace_schema;
  if (typeof schema === "string" && schema.trim()) {
    rows.push({
      label: "Схема следа",
      value: humanizeApiTokenString(schema.trim()),
    });
  }
  const ev = d.trace?.evidence_metrics;
  if (ev && typeof ev === "object") {
    const bits: string[] = [];
    const order = [
      "fake_signal_score",
      "face_device_score",
      "face_frame_score",
      "recapture_score",
      "quality_penalty",
    ] as const;
    for (const k of order) {
      const v = ev[k as string];
      if (typeof v === "number" && Number.isFinite(v)) {
        const lb =
          PRESENTATION_METRIC_LABEL_RU[k] ??
          QUALITY_METRIC_LABEL_RU[k as keyof typeof QUALITY_METRIC_LABEL_RU] ??
          "Дополнительная метрика";
        bits.push(`${lb}: ${(v * 100).toFixed(0)}%`);
      }
    }
    if (bits.length > 0) {
      rows.push({ label: "Снимок метрик в тегах", value: bits.join(" · ") });
    }
  }
  return rows;
}

/**
 * Human-readable lines from operator_tags for optional disclosure.
 *
 * Args:
 *     tags: Filtered operator-facing tag list from the API.
 *
 * Returns:
 *     Deduplicated humanized strings.
 */
export function buildPadHumanizedHints(tags: string[]): string[] {
  const out: string[] = [];
  for (const t of tags) {
    const s = String(t).trim();
    if (!s) continue;
    out.push(humanizePadTag(s));
  }
  return [...new Set(out)].filter((x) => x.length > 0);
}

export type PadVerdictBadgeTone = "success" | "warning" | "danger" | "muted";

export function padVerdictBadgeTone(
  d: PadDiagnosticsPayload,
): PadVerdictBadgeTone {
  const outcome =
    d.decision?.product_outcome ?? d.decision?.final_decision ?? "";
  const st = d.decision?.final_decision ?? "";
  if (st === "suspicious") return "danger";
  if (outcome === "insufficient_input_review") return "warning";
  if (st === "review" || st === "error") return "warning";
  if (st === "clean" && d.decision?.trust_confirmed === null) return "muted";
  if (st === "clean") return "success";
  return "muted";
}

export function padVerdictBadgeLabel(d: PadDiagnosticsPayload): string {
  const st = d.decision?.product_outcome ?? d.decision?.final_decision ?? "";
  const map: Record<string, string> = {
    clean: "Норма",
    insufficient_input_review: "Недостаточно данных",
    review: "На проверку",
    suspicious: "Подозрительно",
    error: "Ошибка",
    pending: "Ожидание",
  };
  return map[st] || "Статус уточняется";
}

const DECISION_SOURCE_RU: Record<string, string> = {
  auto_pad: "Авто-разбор",
  pad_rule_engine: "Авто-разбор",
  automatic: "Авто-разбор",
  manual: "Решение оператора",
  operator: "Решение оператора",
  admin_override: "Исправление в админке",
};

/**
 * Short Russian label for where the verdict came from (no raw API keys in UI).
 *
 * Args:
 *     d: PAD diagnostics payload.
 *
 * Returns:
 *     One-line source description, or null if unknown.
 */
export function verdictSourceLineRu(d: PadDiagnosticsPayload): string | null {
  const src = d.decision?.decision_source?.trim();
  if (!src) return null;
  return DECISION_SOURCE_RU[src] ?? "Источник итога зафиксирован системой.";
}

export function localizePadDiagnostics(d: PadDiagnosticsPayload): {
  headline: string;
  trustLine: string;
  branchExplanation: string | null;
  reviewReasonLines: string[];
  cleanReasonLines: string[];
  interpretabilityLines: string[];
  confidenceLine: string | null;
  presentationLines: string[];
  qualityLines: string[];
  backgroundLines: string[];
  uncertaintyLines: string[];
  supportLines: string[];
} {
  const headline = decisionHeadlineRu(d);
  const productOutcome =
    d.decision?.product_outcome ?? d.decision?.final_decision ?? "";
  const trustLine =
    productOutcome === "insufficient_input_review"
      ? "Это не признак подмены. Системе не хватило качества кадра."
      : `Проверка фото: ${trustLabelRu(d.decision?.trust_confirmed)}.`;
  const decisionBranch = d.decision?.decision_branch ?? "";
  const branchExplanation = branchExplanationRu(
    decisionBranch.length > 0 ? decisionBranch : undefined,
  );

  const reviewReasonLines = (d.uncertainty?.review_reason_codes ?? [])
    .filter((c): c is string => typeof c === "string" && c.length > 0)
    .filter((c) => c !== decisionBranch)
    .map((c) => {
      const txt = BRANCH_SUMMARY_RU[c];
      return (
        txt ??
        "Дополнительное основание вердикта зафиксировано системой (без технических кодов)."
      );
    });

  const cleanReasonLines = (d.uncertainty?.clean_reason_codes ?? [])
    .filter((c): c is string => typeof c === "string" && c.length > 0)
    .filter((c) => c !== decisionBranch)
    .map((c) => {
      const txt = BRANCH_SUMMARY_RU[c];
      return (
        txt ??
        "Дополнительное пояснение для статуса «норма» (без технических кодов)."
      );
    });

  const interpretabilityLines = (d.uncertainty?.interpretability_codes ?? [])
    .filter((c): c is string => typeof c === "string" && c.length > 0)
    .map(
      (c) =>
        INTERPRETABILITY_CODE_RU[c] ??
        "Дополнительное пояснение системы (без технических кодов).",
    );

  const pc = d.decision?.presentation_confidence;
  const finalDecision = d.decision?.final_decision ?? "";
  let confidenceLine: string | null =
    typeof pc === "number" && Number.isFinite(pc)
      ? `Согласованность сигналов по лицу (не про качество кадра): ${(pc * 100).toFixed(0)}%.`
      : null;
  if (
    confidenceLine &&
    finalDecision === "review" &&
    typeof pc === "number" &&
    pc < 0.48
  ) {
    confidenceLine += " Ниже высокой.";
  }

  const presentationLines: string[] = [];
  const p = d.presentation;
  if (p) {
    (Object.entries(p) as [string, number | undefined][]).forEach(([k, v]) => {
      if (typeof v !== "number" || !Number.isFinite(v)) return;
      const label =
        PRESENTATION_METRIC_LABEL_RU[k] ?? "Дополнительная метрика по лицу";
      presentationLines.push(`${label}: ${(v * 100).toFixed(0)}%.`);
    });
  }

  const qualityLines: string[] = [];
  const q = d.quality;
  if (q) {
    if (typeof q.overall_penalty === "number") {
      qualityLines.push(
        `${QUALITY_METRIC_LABEL_RU.overall_penalty}: ${(q.overall_penalty * 100).toFixed(1)}%.`,
      );
    }
    if (typeof q.face_area_ratio === "number") {
      qualityLines.push(
        `${QUALITY_METRIC_LABEL_RU.face_area_ratio}: ${(q.face_area_ratio * 100).toFixed(2)}%.`,
      );
    }
    if (q.is_degraded) {
      qualityLines.push(
        "Качество изображения снижено — это учитывается отдельно и не считается доказательством подделки.",
      );
    }
    if (q.quality_flags && q.quality_flags.length > 0) {
      const hf = q.quality_flags.map((f) => {
        const k = String(f);
        return QUALITY_FLAG_RU[k] ?? k.replace(/_/g, " ");
      });
      qualityLines.push(`Замечания по качеству: ${hf.join(", ")}.`);
    }
  }

  const backgroundLines: string[] = [];
  const bg = d.background_context;
  if (bg) {
    if (typeof bg.background_device_score === "number") {
      backgroundLines.push(
        `Устройство на фоне: ${(bg.background_device_score * 100).toFixed(1)}%.`,
      );
    }
    if (typeof bg.background_frame_score === "number") {
      backgroundLines.push(
        `Рамка на фоне: ${(bg.background_frame_score * 100).toFixed(1)}%.`,
      );
    }
    (bg.context_codes ?? []).forEach((c) => {
      backgroundLines.push(
        CONTEXT_CODE_RU[c] ??
          "Фоновый контекст учтён отдельно от оценки подмены по лицу.",
      );
    });
  }

  const uncertaintyLines: string[] = [];
  (d.uncertainty?.uncertainty_codes ?? []).forEach((c) => {
    if (
      c === "outcome_review_recommended" &&
      finalDecision === "review" &&
      decisionBranch.length > 0
    ) {
      return;
    }
    uncertaintyLines.push(
      UNCERTAINTY_CODE_RU[c] ?? "Дополнительный фактор неопределённости.",
    );
  });
  (d.uncertainty?.missing_signal_codes ?? []).forEach((c) => {
    if (c === "fake_model_score") {
      uncertaintyLines.push("Нет устойчивого балла FasNet.");
    } else {
      uncertaintyLines.push(
        "Часть диагностики модели подмены недоступна — интерпретируйте осторожно.",
      );
    }
  });
  (d.uncertainty?.conflicting_signal_codes ?? []).forEach((c) => {
    if (c === "low_quality_but_high_presentation_alert") {
      uncertaintyLines.push(
        "Сочетание: сниженное качество при высоком риске презентации — проверьте визуально.",
      );
    } else if (c === "low_quality_but_clean_presentation") {
      uncertaintyLines.push(
        "Сочетание: низкое качество при «чистом» презентационном вердикте — качество не доказывает подлинность.",
      );
    } else {
      uncertaintyLines.push(
        "Качество и оценка риска расходятся — ориентируйтесь на визуальный осмотр кадра.",
      );
    }
  });

  const supportLines: string[] = [];
  (d.trace?.decision_support_flags ?? []).forEach((f) => {
    if (
      f === "corroboration_recapture_threshold" &&
      decisionBranch.startsWith("recapture_")
    ) {
      return;
    }
    supportLines.push(
      SUPPORT_FLAG_RU[f] ??
        "Служебная отметка согласованности сигналов (без технических кодов).",
    );
  });

  return {
    headline,
    trustLine,
    branchExplanation,
    reviewReasonLines,
    cleanReasonLines,
    interpretabilityLines,
    confidenceLine,
    presentationLines,
    qualityLines,
    backgroundLines,
    uncertaintyLines,
    supportLines,
  };
}
