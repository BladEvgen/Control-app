import React, { useCallback, useEffect, useId, useState } from "react";
import { useDropzone } from "react-dropzone";
import type { IconType } from "react-icons";
import {
  FaCalendarAlt,
  FaCheck,
  FaCheckCircle,
  FaCloudUploadAlt,
  FaDownload,
  FaExclamationTriangle,
  FaFileAlt,
  FaImages,
  FaMapMarkerAlt,
  FaSitemap,
  FaTimes,
  FaUserMinus,
  FaUsers,
} from "react-icons/fa";
import apiClient from "../api";
import { apiUrl } from "../../apiConfig";

interface ImportOptions {
  categories: { slug: string; name: string }[];
  parentDepartments: { id: number; name: string }[];
  maxUploadMb: number;
  allowedExtensions: Record<string, string[]>;
}

interface ImportStatus {
  state: "PENDING" | "STARTED" | "PROGRESS" | "SUCCESS" | "FAILURE" | string;
  processed: number;
  total: number;
  message: string;
  summary: string[];
  ready: boolean;
}

const POLL_MS = 1500;

const TEMPLATE_INFO: Record<
  string,
  { icon: IconType; hint: string; danger?: boolean }
> = {
  departments: { icon: FaSitemap, hint: "Структура отделов и подразделений" },
  staff: {
    icon: FaUsers,
    hint: "Сотрудники с PIN, должностью и отделом",
  },
  photo: { icon: FaImages, hint: "ZIP с фото, имя файла — PIN сотрудника" },
  public_holidays: {
    icon: FaCalendarAlt,
    hint: "Дата, название и рабочий ли день",
  },
  load_geo: {
    icon: FaMapMarkerAlt,
    hint: "Локации клинических баз для геоотметок",
  },
  delete_staff: {
    icon: FaUserMinus,
    hint: "Убрать перечисленных сотрудников из подразделения",
    danger: true,
  },
};
const TEMPLATE_ORDER = Object.keys(TEMPLATE_INFO);

const STATE_LABEL: Record<string, string> = {
  SUCCESS: "Готово",
  FAILURE: "Ошибка обработки",
  PROGRESS: "Обработка",
};

const errorText = (error: unknown, fallback: string): string => {
  const data = (
    error as { response?: { data?: { error?: string; detail?: string } } }
  ).response?.data;
  return data?.error ?? data?.detail ?? fallback;
};

const formatSize = (bytes: number): string =>
  bytes < 1024 * 1024
    ? `${Math.max(1, Math.round(bytes / 1024))} КБ`
    : `${(bytes / 1024 / 1024).toFixed(1)} МБ`;

const ImportPage: React.FC = () => {
  const formId = useId();
  const [options, setOptions] = useState<ImportOptions | null>(null);
  const [category, setCategory] = useState("");
  const [parentDepartment, setParentDepartment] = useState("");
  const [archiveMissing, setArchiveMissing] = useState(false);
  const [forceArchive, setForceArchive] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [taskId, setTaskId] = useState<string | null>(null);
  const [status, setStatus] = useState<ImportStatus | null>(null);

  useEffect(() => {
    apiClient
      .get<ImportOptions>("/import/")
      .then((r) => setOptions(r.data))
      .catch((e: unknown) =>
        setError(errorText(e, "Не удалось загрузить шаблоны.")),
      );
  }, []);

  useEffect(() => {
    if (!taskId) return;
    let timer = 0;
    let alive = true;
    const poll = () => {
      apiClient
        .get<ImportStatus>(`/import/status/${encodeURIComponent(taskId)}/`)
        .then((r) => {
          if (!alive) return;
          setStatus(r.data);
          if (!r.data.ready) timer = window.setTimeout(poll, POLL_MS);
        })
        .catch(
          (e: unknown) =>
            alive && setError(errorText(e, "Не удалось получить статус.")),
        );
    };
    poll();
    return () => {
      alive = false;
      window.clearTimeout(timer);
    };
  }, [taskId]);

  const templates = [...(options?.categories ?? [])].sort(
    (a, b) =>
      (TEMPLATE_ORDER.indexOf(a.slug) + 1 || 99) -
      (TEMPLATE_ORDER.indexOf(b.slug) + 1 || 99),
  );
  const accepted = (category && options?.allowedExtensions[category]) || [
    ".csv",
    ".xlsx",
    ".zip",
  ];
  const running = taskId != null && !status?.ready;
  const busy = submitting || running;

  const onDrop = useCallback((files: File[]) => {
    setFile(files[0] ?? null);
    setError("");
  }, []);
  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    onDropRejected: () =>
      setError(`Для этого шаблона подходят файлы ${accepted.join(", ")}.`),
    multiple: false,
    disabled: !category || busy,
    accept: { "application/octet-stream": accepted },
  });

  const pickTemplate = (slug: string) => {
    setCategory(slug);
    setFile(null);
    setError("");
  };

  const reset = () => {
    setTaskId(null);
    setStatus(null);
    setFile(null);
    setError("");
  };

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!category || !file) return;
    if (category === "delete_staff" && !parentDepartment) {
      setError("Выберите подразделение, из которого удалить сотрудников.");
      return;
    }
    if (
      category === "delete_staff" &&
      !window.confirm(`Удалить сотрудников из файла «${file.name}»?`)
    )
      return;
    const body = new FormData();
    body.append("category", category);
    body.append("file", file);
    if (category === "delete_staff")
      body.append("parentDepartment", parentDepartment);
    if (category === "staff") {
      body.append("archiveMissing", String(archiveMissing));
      body.append("forceArchive", String(forceArchive));
    }
    setSubmitting(true);
    setError("");
    setStatus(null);
    try {
      const { data } = await apiClient.post<{ taskId: string }>(
        "/import/",
        body,
      );
      setTaskId(data.taskId);
      setStatus({
        state: "PENDING",
        processed: 0,
        total: 0,
        message: "Задача в очереди.",
        summary: [],
        ready: false,
      });
    } catch (e) {
      setError(errorText(e, "Не удалось отправить файл."));
    } finally {
      setSubmitting(false);
    }
  };

  const percent =
    status?.state === "SUCCESS"
      ? 100
      : status?.total
        ? Math.min(100, Math.round((status.processed / status.total) * 100))
        : 0;
  const chosen = templates.find((t) => t.slug === category);

  return (
    <section className="import-page">
      <header className="detail-head">
        <div className="ws-page-head">
          <h1>Импорт данных</h1>
          <p className="detail-meta">
            Выберите шаблон, приложите файл — обработка идёт в фоне, страницу
            можно не закрывать.
          </p>
        </div>
        <div className="detail-actions">
          <a className="ws-btn-ghost" href={`${apiUrl}/download/examples/`}>
            <FaDownload aria-hidden />
            Примеры файлов
          </a>
        </div>
      </header>

      <div className="import-layout">
        <fieldset className="import-step" disabled={busy}>
          <legend>
            <span
              className="import-step-no"
              data-done={!!category || undefined}
            >
              {category ? <FaCheck aria-hidden /> : "1"}
            </span>
            Что загружаем
          </legend>
          <div className="import-templates">
            {options
              ? templates.map((t, i) => {
                  const info = TEMPLATE_INFO[t.slug];
                  const Icon = info?.icon ?? FaFileAlt;
                  return (
                    <label
                      key={t.slug}
                      className="import-template"
                      data-danger={info?.danger || undefined}
                      style={{ "--i": i } as React.CSSProperties}
                    >
                      <input
                        type="radio"
                        name={`${formId}-template`}
                        value={t.slug}
                        checked={category === t.slug}
                        onChange={() => pickTemplate(t.slug)}
                        className="sr-only"
                      />
                      <span className="import-template-icon">
                        <Icon aria-hidden />
                      </span>
                      <span className="import-template-text">
                        <strong>{t.name}</strong>
                        {info && <span>{info.hint}</span>}
                      </span>
                      <span className="import-template-ext">
                        {(options.allowedExtensions[t.slug] ?? []).join(" ")}
                      </span>
                      <span className="import-template-check" aria-hidden>
                        <FaCheck />
                      </span>
                    </label>
                  );
                })
              : Array.from({ length: 6 }, (_, i) => (
                  <span key={i} className="import-template-skeleton" />
                ))}
          </div>
        </fieldset>

        <form className="import-panel" onSubmit={submit} noValidate>
          <div className="import-step-title">
            <span className="import-step-no" data-done={!!file || undefined}>
              {file ? <FaCheck aria-hidden /> : "2"}
            </span>
            {chosen ? `Файл: ${chosen.name.toLowerCase()}` : "Файл"}
          </div>

          {file && !running && !status ? (
            <div className="import-file">
              <FaFileAlt aria-hidden />
              <span>
                <strong>{file.name}</strong>
                <small>{formatSize(file.size)}</small>
              </span>
              <button
                type="button"
                className="ws-input-action"
                onClick={() => setFile(null)}
                aria-label="Убрать файл"
              >
                <FaTimes aria-hidden />
              </button>
            </div>
          ) : (
            !status && (
              <div
                {...getRootProps({
                  className: "import-drop",
                  "data-active": isDragActive || undefined,
                  "aria-disabled": !category || undefined,
                })}
              >
                <input {...getInputProps()} aria-label="Файл для импорта" />
                <span className="import-drop-icon">
                  <FaCloudUploadAlt aria-hidden />
                </span>
                <strong>
                  {!category
                    ? "Сначала выберите шаблон слева"
                    : isDragActive
                      ? "Отпустите, чтобы приложить"
                      : "Перетащите файл или нажмите"}
                </strong>
                <span className="import-drop-hint">
                  {accepted.join(", ")} · до {options?.maxUploadMb ?? "—"} МБ
                </span>
              </div>
            )
          )}

          {category === "delete_staff" && !status && (
            <div className="ws-field import-reveal">
              <label htmlFor={`${formId}-parent`}>
                Из какого подразделения
              </label>
              <div className="ws-input">
                <select
                  id={`${formId}-parent`}
                  value={parentDepartment}
                  onChange={(e) => setParentDepartment(e.target.value)}
                >
                  <option value="" disabled>
                    Выберите подразделение
                  </option>
                  {options?.parentDepartments.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          )}

          {category === "staff" && !status && (
            <div className="import-switches import-reveal">
              <label className="import-switch">
                <input
                  type="checkbox"
                  role="switch"
                  checked={archiveMissing}
                  onChange={(e) => {
                    setArchiveMissing(e.target.checked);
                    if (!e.target.checked) setForceArchive(false);
                  }}
                />
                <span>
                  <strong>Архивировать отсутствующих</strong>
                  Кого нет в файле — пропадут из отчётов и посещаемости. Записи
                  сохраняются.
                </span>
              </label>
              {archiveMissing && (
                <label className="import-switch import-reveal" data-warn>
                  <input
                    type="checkbox"
                    role="switch"
                    checked={forceArchive}
                    onChange={(e) => setForceArchive(e.target.checked)}
                  />
                  <span>
                    <strong>Даже если затронута больше половины</strong>
                    Без этого импорт остановится, чтобы неполная выгрузка не
                    скрыла весь штат.
                  </span>
                </label>
              )}
            </div>
          )}

          {error && (
            <p className="import-alert" role="alert">
              <FaExclamationTriangle aria-hidden />
              {error}
            </p>
          )}

          {status ? (
            <div
              className="import-progress"
              role="status"
              aria-live="polite"
              data-state={status.state}
            >
              <div className="import-progress-head">
                <span
                  className="import-step-no"
                  data-done={status.ready || undefined}
                >
                  {status.state === "SUCCESS" ? (
                    <FaCheckCircle aria-hidden />
                  ) : status.state === "FAILURE" ? (
                    <FaTimes aria-hidden />
                  ) : (
                    "3"
                  )}
                </span>
                <strong>{STATE_LABEL[status.state] ?? "В очереди"}</strong>
                {status.state !== "FAILURE" && (
                  <span className="import-progress-pct">{percent}%</span>
                )}
              </div>
              <div
                className="import-progress-bar"
                data-running={running || undefined}
              >
                <div style={{ transform: `scaleX(${percent / 100})` }} />
              </div>
              {status.message && <p>{status.message}</p>}
              {status.summary.length > 0 && (
                <ul>
                  {status.summary.map((line) => (
                    <li key={line}>{line}</li>
                  ))}
                </ul>
              )}
              {status.ready && (
                <button type="button" className="ws-btn-ghost" onClick={reset}>
                  Загрузить ещё файл
                </button>
              )}
            </div>
          ) : (
            <button
              type="submit"
              className="ws-btn-primary import-submit"
              data-danger={category === "delete_staff" || undefined}
              disabled={busy || !category || !file}
            >
              {busy ? (
                <span className="ws-spinner" aria-hidden />
              ) : (
                <FaCloudUploadAlt aria-hidden />
              )}
              {busy
                ? "Отправляем…"
                : category === "delete_staff"
                  ? "Удалить по списку"
                  : "Загрузить"}
            </button>
          )}
        </form>
      </div>
    </section>
  );
};

export default ImportPage;
