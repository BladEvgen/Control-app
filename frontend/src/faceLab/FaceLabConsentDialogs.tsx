import type { ReactNode } from "react";

type ConsentDialogProps = {
  open: boolean;
  title: string;
  children: ReactNode;
  onCancel: () => void;
  onConfirm: () => void;
  confirmLabel?: string;
  cancelLabel?: string;
};

export function FaceLabConsentDialog({
  open,
  title,
  children,
  onCancel,
  onConfirm,
  confirmLabel = "Продолжить",
  cancelLabel = "Отмена",
}: ConsentDialogProps) {
  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-[10001] flex items-end justify-center bg-slate-900/55 p-4 backdrop-blur-sm dark:bg-black/70 sm:items-center"
      role="dialog"
      aria-modal="true"
      aria-labelledby="face-lab-consent-title"
    >
      <div className="max-h-[min(90vh,520px)] w-full max-w-lg overflow-y-auto rounded-2xl border border-slate-200 bg-white p-5 shadow-xl dark:border-slate-600 dark:bg-slate-900">
        <h2
          id="face-lab-consent-title"
          className="text-lg font-semibold text-slate-900 dark:text-slate-100"
        >
          {title}
        </h2>
        <div className="mt-3 space-y-2 text-sm leading-relaxed text-slate-600 dark:text-slate-300">
          {children}
        </div>
        <div className="mt-5 flex flex-wrap justify-end gap-2">
          <button
            type="button"
            className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 transition hover:border-blue-300 hover:bg-blue-50 hover:text-blue-800 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500/70 dark:border-slate-600 dark:text-slate-200 dark:hover:border-blue-500/60 dark:hover:bg-blue-500/10 dark:hover:text-blue-200"
            onClick={onCancel}
          >
            {cancelLabel}
          </button>
          <button
            type="button"
            className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-blue-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500/70 focus-visible:ring-offset-2 focus-visible:ring-offset-white dark:bg-blue-500 dark:hover:bg-blue-600 dark:focus-visible:ring-blue-300/80 dark:focus-visible:ring-offset-slate-900"
            onClick={onConfirm}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
