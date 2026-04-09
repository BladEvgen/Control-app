import type { FaceVerifyStatus } from "./faceVerificationSchema";

export type FriendlyError = { title: string; detail?: string };

export function sanitizeApiErrorString(raw: string): string {
  const s = raw.trim();
  if (!/errordetail/i.test(s)) return s;
  const parts: string[] = [];
  const re = /ErrorDetail\(string=['"]([^'"]*)['"]\)/gi;
  let m: RegExpExecArray | null;
  while ((m = re.exec(s)) !== null) parts.push(m[1]);
  if (parts.length > 0) return parts.join(" ").trim();
  return s;
}

function norm(s: string): string {
  return s.trim().toLowerCase();
}

function glossEnglishSnippet(s: string): string {
  return s
    .replace(/\bquality\b/gi, "качество")
    .replace(/\bblur\b/gi, "размытие")
    .replace(/\bblurry\b/gi, "размыто")
    .replace(/\bsharpness\b/gi, "резкость")
    .replace(/\bnoise\b/gi, "шум")
    .replace(/\bliveness\b/gi, "проверка фото")
    .replace(/\btimeout\b/gi, "тайм-аут");
}

export function humanizeApiError(raw: string): FriendlyError {
  const s = sanitizeApiErrorString(raw).trim();
  const n = norm(s);

  if (!s) {
    return { title: "Что-то пошло не так", detail: "Попробуйте ещё раз." };
  }

  const rules: Array<{ test: (x: string) => boolean; out: FriendlyError }> = [
    {
      test: (x) =>
        x.includes("в базе нет сотрудников") ||
        x.includes("сохранённой маской лица") ||
        x.includes("сохраненной маской лица") ||
        x.includes("нет ни одного корректного эмбеддинга"),
      out: {
        title: "В базе нет масок для поиска",
        detail: "Нужны сохранённые маски лиц (генерация на сервере).",
      },
    },
    {
      test: (x) =>
        x.includes("no face detected") || x.includes("лицо не обнаружено"),
      out: {
        title: "Лицо на фото не найдено",
        detail:
          "Снимите крупнее, при хорошем свете, лицо по центру. Не используйте сильно затемнённые или размытые кадры.",
      },
    },
    {
      test: (x) => x.includes("staff not found") || x.includes("не найден"),
      out: {
        title: "Сотрудник не найден",
        detail: "Проверьте выбор в списке или обновите страницу.",
      },
    },
    {
      test: (x) => {
        if (
          x.includes("в базе нет сотрудников") ||
          x.includes("сохранённой маской лица") ||
          x.includes("сохраненной маской лица") ||
          x.includes("корректного эмбеддинга сотрудников") ||
          (x.includes("корректного эмбеддинга") && x.includes("базе"))
        ) {
          return false;
        }
        return (
          x.includes("face mask") ||
          (x.includes("маск") && !x.includes("маски лиц в базе")) ||
          x.includes("эталон") ||
          (x.includes("gallery") && !x.includes("recognition")) ||
          x.includes("прототип")
        );
      },
      out: {
        title: "Нет эталона для сравнения",
        detail:
          "У выбранного сотрудника нет сохранённого эталона лица или аватара. Обратитесь к администратору, чтобы добавить фото в профиль.",
      },
    },
    {
      test: (x) =>
        x.includes("pin and image") ||
        x.includes("required") ||
        x.includes("обязательн"),
      out: {
        title: "Не хватает данных",
        detail: "Нужны фото и (для режима «С эталоном») выбранный сотрудник.",
      },
    },
    {
      test: (x) => x.includes("empty") && x.includes("image"),
      out: {
        title: "Пустой файл",
        detail: "Выберите другое изображение.",
      },
    },
    {
      test: (x) =>
        x.includes("network") || x.includes("timeout") || x.includes("econn"),
      out: {
        title: "Сеть или сервер не ответили",
        detail: "Проверьте подключение и попробуйте снова.",
      },
    },
    {
      test: (x) => x.includes("401") || x.includes("unauthorized"),
      out: {
        title: "Сессия истекла",
        detail: "Войдите в систему заново.",
      },
    },
    {
      test: (x) => x.includes("403") || x.includes("forbidden"),
      out: {
        title: "Нет доступа",
        detail: "Обратитесь к администратору.",
      },
    },
  ];

  for (const { test, out } of rules) {
    if (test(n)) return out;
  }

  if (/[а-яёА-ЯЁ]/.test(s) && s.length < 100 && !/^\s*\{/.test(s)) {
    return { title: s };
  }

  const clipped = s.length > 120 ? `${s.slice(0, 117)}…` : s;
  return {
    title: "Не удалось выполнить проверку",
    detail: glossEnglishSnippet(clipped),
  };
}

export type GallerySearchHelp = FriendlyError & {
  outcome: "partial" | "fail";
  headline: string;
};

export function humanizeGallerySearchError(raw: string): GallerySearchHelp {
  const s = sanitizeApiErrorString(raw).trim();
  const n = norm(s);

  if (
    n.includes("в базе нет сотрудников") ||
    n.includes("сохранённой маской лица") ||
    n.includes("сохраненной маской лица")
  ) {
    return {
      title: "База для поиска пока не готова",
      detail: "Серверу пока не из чего искать совпадение. Нужны эталоны лиц.",
      outcome: "partial",
      headline: "Поиск недоступен",
    };
  }

  if (n.includes("нет ни одного корректного эмбеддинга")) {
    return {
      title: "База поиска не готова",
      detail: "Нужно обновить серверные эталоны лиц.",
      outcome: "partial",
      headline: "Нужно обновить базу",
    };
  }

  if (n.includes("размерность маски в базе") && n.includes("не совпадает")) {
    return {
      title: "Модель и база не совпадают",
      detail: "Пересчитайте маски под текущую модель.",
      outcome: "partial",
      headline: "Настройка сервера",
    };
  }

  if (
    n.includes("разная размерность векторов") ||
    n.includes("несовпадение размерности векторов")
  ) {
    return {
      title: "База поиска устарела",
      detail: "Серверные эталоны нужно пересчитать под текущую модель.",
      outcome: "partial",
      headline: "Галерея неоднородна",
    };
  }

  if (
    n.includes("timeout") ||
    n.includes("timed out") ||
    n.includes("aborted")
  ) {
    return {
      title: "Поиск отвечает слишком долго",
      detail:
        "Сервер ещё обрабатывает кадр. Попробуйте ещё раз через несколько секунд.",
      outcome: "partial",
      headline: "Сервер занят",
    };
  }

  if (
    n.includes("лица не найдены на изображении") ||
    n.includes("no face detected")
  ) {
    return {
      title: "Лицо не найдено",
      detail: "Крупнее, ровный свет, лицо по центру.",
      outcome: "fail",
      headline: "Другой кадр",
    };
  }

  if (n.includes("no staff members recognized")) {
    return {
      title: "Надёжного совпадения нет",
      detail: "Попробуйте другой кадр: лицо ближе, ровнее и без смаза.",
      outcome: "partial",
      headline: "Не нашли",
    };
  }

  if (
    n.includes("face recognition error") ||
    n.includes("ошибка при распознавании лиц")
  ) {
    const inner = sanitizeApiErrorString(
      s.replace(/^[^:]*:\s*/i, "").trim(),
    ).trim();
    if (inner && inner !== s) {
      return humanizeGallerySearchError(inner);
    }
  }

  const f = humanizeApiError(raw);
  const softFail =
    n.includes("invalid image") ||
    n.includes("empty") ||
    n.includes("required") ||
    n.includes("format");
  return {
    title: f.title,
    detail: f.detail,
    outcome: softFail ? "fail" : "partial",
    headline: softFail ? "Проверьте файл" : "Распознавание не завершилось",
  };
}

export function humanizePadStatus(status: string): string {
  const m: Record<string, string> = {
    clean: "Кадр принят автоматически.",
    suspicious: "Есть сильные признаки подмены.",
    insufficient_input_review:
      "Системе не хватило качества кадра для авто-вердикта.",
    error: "Проверка фото не завершилась.",
    pending: "Проверка фото ещё не завершена.",
    trust_confirmed: "Система считает кадр живым и приемлемым.",
    trust_rejected: "Кадр не прошёл проверку на подлинность.",
    review: "Нужна ручная оценка.",
    rejected: "Кадр отклонён.",
    ambiguous: "Результат неоднозначный.",
  };
  return m[status] ?? "Результат проверки фото.";
}

const SNAKE_TOKEN_RU: Record<string, string> = {
  quality: "качество",
  blur: "размытие",
  sharpness: "резкость",
  noise: "шум",
  small: "мелкий",
  face: "лицо",
  penalty: "штраф",
  frame: "кадр",
  screen: "экран",
  edges: "края",
  device: "устройство",
  deepfake: "подмена",
  deepface: "анализ лица",
  trust: "доверие",
  confirmed: "подтверждено",
  rejected: "отклонено",
  unknown: "неизвестно",
  error: "ошибка",
  high: "высокий",
  low: "низкий",
  score: "оценка",
  bbox: "область",
  threshold: "порог",
  gallery: "галерея",
  embedding: "вектор",
  model: "модель",
  version: "версия",
  left: "слева",
  right: "справа",
  open: "открыто",
  closed: "закрыто",
  blink: "моргание",
  strict: "строгий",
  fallback: "запасной",
};

function humanizeSnakeOrEnglishFragment(s: string): string {
  const raw = s.trim();
  if (!raw) return raw;
  const parts = raw.split(/_+/).filter(Boolean);
  if (parts.length <= 1 && !raw.includes("_")) {
    const low = raw.toLowerCase();
    return SNAKE_TOKEN_RU[low] ?? raw;
  }
  return parts.map((p) => SNAKE_TOKEN_RU[p.toLowerCase()] ?? p).join(" ");
}

export function humanizePadTag(tag: string): string {
  const m: Record<string, string> = {
    no_face: "Лицо не найдено",
    deepface_error: "Не удалось оценить подлинность лица",
    deepfake_high: "Высокий риск подмены",
    deepfake_device: "Подозрение на съёмку с экрана",
    quality_small_face: "Лицо слишком мелкое на кадре",
    frame_screen_like: "Похоже на фото экрана",
    frame_edges: "Подозрительные края кадра",
    recapture_fft_periodicity: "Техн. метка: периодика FFT на лице",
    recapture_gradient_aniso: "Техн. метка: направленность градиентов на лице",
    recapture_combined: "Техн. метка: сводная текстура лица",
    recapture_blur_dampened: "Техн. метка: текстура ослаблена из‑за размытия",
  };
  return m[tag] ?? humanizeSnakeOrEnglishFragment(tag);
}

export function humanizeFaceVerifyStatus(status: FaceVerifyStatus): string {
  const m: Record<FaceVerifyStatus, string> = {
    VERIFIED: "Совпадение подтверждено",
    REJECTED: "Совпадение не подтверждено",
    QUALITY_FAIL: "Кадр слабый для сравнения",
    LIVENESS_FAIL: "Кадр не прошёл проверку фото",
    PAD_ERROR: "Проверка фото не завершилась",
  };
  return m[status] ?? status;
}

export function humanizeVerifyReasonCode(code: string): string {
  const r: Record<string, string> = {
    PROBE_QUALITY_LOW: "кадр слабый для уверенного сравнения",
    SCORE_BELOW_WEAK_GALLERY_THRESHOLD:
      "сходство ниже порога для слабой галереи",
    WEAK_ENROLLMENT: "в галерее мало независимых эталонов",
    SCORE_BELOW_VERIFIED_THRESHOLD: "сходство ниже обычного порога",
    SCORE_BELOW_COLD_START_THRESHOLD:
      "сходство ниже порога для режима без собранной галереи",
    COLD_START_QUALITY_INSUFFICIENT:
      "для режима без собранной галереи нужен более уверенный кадр",
    LIVENESS_FAILED: "проверка фото не подтверждена",
    PAD_PIPELINE_FAILED: "проверка фото не завершилась",
  };
  return r[code] ?? humanizeSnakeOrEnglishFragment(code);
}

export function humanizeUnknownFaceStatus(status: string): string {
  const m: Record<string, string> = {
    unknown: "совпадение в галерее не найдено",
    below_threshold: "сходство ниже текущего порога",
  };
  return m[status] ?? humanizeSnakeOrEnglishFragment(status);
}

export function humanizeApiTokenString(value: string): string {
  const t = value.trim();
  if (!t) return t;
  if (/^[a-z][a-z0-9_]*$/i.test(t) && (t.includes("_") || t.length < 24)) {
    return humanizeSnakeOrEnglishFragment(t);
  }
  return t;
}

export function humanizeResponseFieldKey(key: string): string {
  const labels: Record<string, string> = {
    error: "Сообщение",
    detail: "Подробности",
    message: "Сообщение",
    status: "Статус",
    score: "Сходство (0–1)",
    max_cosine: "Лучшая схожесть",
    threshold_used: "Порог",
    matched: "Совпадение",
    final_decision: "Итог",
    summary: "Пояснение",
    gallery_strength: "Надёжность галереи",
    threshold_applied: "Применённый порог",
    threshold_verified_strong: "Порог (сильная галерея)",
    threshold_verified_weak: "Порог (слабая галерея)",
    diagnostics: "Диагностика",
    recognized_staff: "Найденные сотрудники",
    unknown_faces: "Неизвестные лица",
    model_version: "Версия модели",
    elapsed_ms: "Время обработки на сервере",
    trust_confirmed: "Кадр принят",
    risk_score: "Риск подмены",
    tags: "Метки",
    deepface_score: "Подлинность лица",
    device_score: "Признаки экрана",
    frame_score: "Рамка кадра",
    quality_penalty: "Оценка чёткости лица",
    quality: "Качество",
    blur: "Размытие",
    sharpness: "Резкость",
    noise: "Шум",
    confidence: "Уверенность",
    similarity: "Сходство",
    bbox: "Область лица",
    width: "Ширина",
    height: "Высота",
    liveness: "Проверка фото",
    pad: "Проверка фото",
  };
  return labels[key] ?? humanizeSnakeOrEnglishFragment(key);
}

export function humanizePadFailureReason(raw: string): FriendlyError {
  const n = norm(raw);
  if (n.includes("timeout") || n.includes("timed out")) {
    return {
      title: "Проверка фото не успела завершиться",
      detail: "Попробуйте уменьшить размер фото или повторить запрос.",
    };
  }
  if (n.includes("500") || n.includes("internal")) {
    return {
      title: "Ошибка на сервере при проверке фото",
      detail:
        "Попробуйте позже. Распознавание ниже могло всё равно выполниться.",
    };
  }
  return humanizeApiError(raw);
}
