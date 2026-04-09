import { type ReactNode, useMemo, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import {
  buildPadDevDetailRows,
  buildPadEvidenceChips,
  buildPadHumanizedHints,
  localizePadDiagnostics,
  padVerdictBadgeLabel,
  padVerdictBadgeTone,
  verdictSourceLineRu,
} from "./faceLabPadLocale";
import type { PadDiagnosticsPayload } from "./faceLabPadTypes";

function mergeDistinctLines(
  ...groups: (string | null | undefined)[][]
): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const g of groups) {
    for (const raw of g) {
      if (raw == null) continue;
      const t = raw.replace(/\s+/g, " ").trim();
      if (!t || seen.has(t)) continue;
      seen.add(t);
      out.push(t);
    }
  }
  return out;
}

function Panel({
  title,
  subtitle,
  variant = "default",
  children,
}: {
  title: string;
  subtitle?: string;
  variant?: "default" | "warn";
  children: ReactNode;
}) {
  const shell =
    variant === "warn"
      ? "border-amber-200/90 bg-amber-50/90 dark:border-amber-800/50 dark:bg-amber-950/25"
      : "border-slate-200/80 bg-white/70 dark:border-slate-600/50 dark:bg-slate-950/40";
  return (
    <motion.section
      className={`rounded-xl border ${shell} p-4 shadow-sm backdrop-blur-sm transition-shadow duration-200 hover:shadow-md`}
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
    >
      <h3 className="text-sm font-semibold tracking-tight text-slate-900 dark:text-slate-100">
        {title}
      </h3>
      {subtitle ? (
        <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">
          {subtitle}
        </p>
      ) : null}
      <div className="mt-3 text-sm leading-relaxed text-slate-700 dark:text-slate-300">
        {children}
      </div>
    </motion.section>
  );
}

function BulletList({ items }: { items: string[] }) {
  if (items.length === 0) return null;
  return (
    <ul className="list-disc space-y-1.5 pl-4 marker:text-slate-400">
      {items.map((line, i) => (
        <li key={i}>{line}</li>
      ))}
    </ul>
  );
}

function verdictBadgeClass(
  tone: ReturnType<typeof padVerdictBadgeTone>,
): string {
  if (tone === "success") {
    return "border-emerald-200/80 bg-emerald-500/15 text-emerald-900 dark:border-emerald-800/40 dark:bg-emerald-500/15 dark:text-emerald-100";
  }
  if (tone === "danger") {
    return "border-rose-200/80 bg-rose-500/15 text-rose-900 dark:border-rose-800/40 dark:bg-rose-500/15 dark:text-rose-100";
  }
  if (tone === "warning") {
    return "border-amber-200/80 bg-amber-500/15 text-amber-950 dark:border-amber-800/40 dark:bg-amber-500/15 dark:text-amber-50";
  }
  return "border-slate-200/80 bg-slate-100 text-slate-800 dark:border-slate-600/60 dark:bg-slate-800/80 dark:text-slate-100";
}

function Disclosure({
  id,
  title,
  muted,
  defaultOpen = false,
  children,
}: {
  id: string;
  title: string;
  muted?: boolean;
  defaultOpen?: boolean;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div
      className={
        muted
          ? "rounded-lg border border-transparent"
          : "rounded-lg border border-slate-200/60 dark:border-slate-600/40"
      }
    >
      <button
        type="button"
        id={`${id}-btn`}
        aria-expanded={open}
        className="flex w-full items-center justify-between gap-2 rounded-lg px-1 py-2 text-left text-xs font-medium text-slate-600 transition-colors hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-100"
        onClick={() => setOpen((v) => !v)}
      >
        <span>{title}</span>
        <motion.span
          animate={{ rotate: open ? 180 : 0 }}
          transition={{ duration: 0.18 }}
          className="text-slate-400"
          aria-hidden
        >
          ▾
        </motion.span>
      </button>
      <AnimatePresence initial={false}>
        {open ? (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2, ease: [0.22, 1, 0.36, 1] }}
            className="overflow-hidden"
          >
            <div className="pb-3 pt-0">{children}</div>
          </motion.div>
        ) : null}
      </AnimatePresence>
    </div>
  );
}

export function PadDiagnosticsReadout({
  diagnostics,
}: {
  diagnostics: PadDiagnosticsPayload | null;
}) {
  const L = diagnostics ? localizePadDiagnostics(diagnostics) : null;
  const tone = diagnostics ? padVerdictBadgeTone(diagnostics) : "muted";
  const badgeLabel = diagnostics ? padVerdictBadgeLabel(diagnostics) : "—";
  const sourceLine = diagnostics ? verdictSourceLineRu(diagnostics) : null;

  const chips = useMemo(
    () => (diagnostics ? buildPadEvidenceChips(diagnostics) : []),
    [diagnostics],
  );
  const devRows = useMemo(
    () => (diagnostics ? buildPadDevDetailRows(diagnostics) : []),
    [diagnostics],
  );

  const opTags = useMemo(() => {
    if (!diagnostics || !Array.isArray(diagnostics.operator_tags)) return [];
    return diagnostics.operator_tags.filter(
      (s): s is string => typeof s === "string" && s.trim().length > 0,
    );
  }, [diagnostics]);
  const hintLines = useMemo(() => buildPadHumanizedHints(opTags), [opTags]);

  const whyLines = useMemo(() => {
    if (!L) return [];
    return mergeDistinctLines(
      [L.branchExplanation],
      L.reviewReasonLines,
      L.cleanReasonLines,
      L.interpretabilityLines,
    );
  }, [L]);

  const metricLines = useMemo(() => {
    if (!L) return [];
    return [...L.presentationLines, ...L.qualityLines];
  }, [L]);

  if (!diagnostics || !L) {
    return null;
  }

  const hasExtra =
    L.supportLines.length > 0 ||
    metricLines.length > 0 ||
    hintLines.length > 0 ||
    L.backgroundLines.length > 0;

  return (
    <div className="space-y-4 text-sm">
      <motion.div
        className="relative overflow-hidden rounded-2xl border border-slate-200/80 bg-gradient-to-br from-slate-50/95 via-white to-slate-50/80 p-4 shadow-sm dark:border-slate-600/50 dark:from-slate-950/90 dark:via-slate-900/80 dark:to-slate-950/90"
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.25, ease: [0.22, 1, 0.36, 1] }}
      >
        <div className="flex flex-wrap items-start gap-3">
          <span
            className={`inline-flex shrink-0 rounded-full border px-3 py-1 text-xs font-semibold uppercase tracking-wide ${verdictBadgeClass(tone)}`}
          >
            {badgeLabel}
          </span>
          <div className="min-w-0 flex-1 space-y-1">
            {sourceLine ? (
              <p className="text-xs font-medium text-slate-500 dark:text-slate-400">
                {sourceLine}
              </p>
            ) : null}
            <p className="text-base font-semibold leading-snug text-slate-900 dark:text-slate-50">
              {L.headline}
            </p>
            <p className="text-xs text-slate-600 dark:text-slate-400">
              {L.trustLine}
            </p>
          </div>
        </div>
      </motion.div>

      {whyLines.length > 0 ? (
        <Panel title="Причина" subtitle="Коротко по этому кадру.">
          <BulletList items={whyLines} />
        </Panel>
      ) : null}

      {chips.length > 0 ? (
        <Panel title="Основания" subtitle="Главные сигналы по лицу.">
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {chips.map((c) => (
              <div
                key={c.key}
                className="flex flex-col rounded-lg border border-slate-200/70 bg-slate-50/80 px-3 py-2 dark:border-slate-600/50 dark:bg-slate-900/50"
              >
                <span className="text-[11px] font-medium uppercase tracking-wide text-slate-500 dark:text-slate-400">
                  {c.label}
                </span>
                <span className="mt-0.5 text-lg font-semibold tabular-nums text-slate-900 dark:text-slate-100">
                  {c.value}
                </span>
              </div>
            ))}
          </div>
        </Panel>
      ) : null}

      {L.uncertaintyLines.length > 0 ? (
        <Panel
          title="Неопределённость"
          variant="warn"
          subtitle="При визуальной проверке."
        >
          <BulletList items={L.uncertaintyLines} />
        </Panel>
      ) : null}

      {L.confidenceLine ? (
        <p className="px-1 text-xs text-slate-500 dark:text-slate-400">
          {L.confidenceLine}
        </p>
      ) : null}

      {hasExtra || devRows.length > 0 ? (
        <div className="space-y-1 rounded-xl border border-dashed border-slate-200/90 bg-slate-50/50 p-3 dark:border-slate-600/50 dark:bg-slate-950/30">
          <p className="px-1 text-[11px] font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
            Дополнительно
          </p>
          {L.supportLines.length > 0 ? (
            <Disclosure id="pad-support" title="Согласованность">
              <BulletList items={L.supportLines} />
            </Disclosure>
          ) : null}
          {metricLines.length > 0 ? (
            <Disclosure id="pad-metrics" title="Метрики подробнее">
              <ul className="space-y-1.5 text-xs text-slate-600 dark:text-slate-400">
                {metricLines.map((line, i) => (
                  <li key={i}>{line}</li>
                ))}
              </ul>
            </Disclosure>
          ) : null}
          {hintLines.length > 0 ? (
            <Disclosure id="pad-hints" title="Подсказки">
              <ul className="flex flex-wrap gap-2">
                {hintLines.map((h) => (
                  <li
                    key={h}
                    className="rounded-full border border-slate-200/80 bg-white px-2.5 py-1 text-xs text-slate-700 dark:border-slate-600/60 dark:bg-slate-900/60 dark:text-slate-200"
                  >
                    {h}
                  </li>
                ))}
              </ul>
            </Disclosure>
          ) : null}
          {L.backgroundLines.length > 0 ? (
            <Disclosure id="pad-bg" title="Контекст кадра">
              <BulletList items={L.backgroundLines} />
            </Disclosure>
          ) : null}
          {devRows.length > 0 ? (
            <Disclosure id="pad-dev" title="Технические детали" muted>
              <dl className="space-y-2 text-xs">
                {devRows.map((row, idx) => (
                  <div
                    key={`${row.label}-${idx}`}
                    className="rounded-md border border-slate-200/60 bg-white/80 px-2.5 py-2 dark:border-slate-600/50 dark:bg-slate-900/50"
                  >
                    <dt className="font-medium text-slate-600 dark:text-slate-400">
                      {row.label}
                    </dt>
                    <dd className="mt-1 text-slate-800 dark:text-slate-200">
                      {row.value}
                    </dd>
                  </div>
                ))}
              </dl>
            </Disclosure>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
