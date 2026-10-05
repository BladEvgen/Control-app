import { useEffect, useId, useRef, type ReactNode } from "react";

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
  const dialogRef = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  useEffect(() => {
    const dialog = dialogRef.current;
    if (!open) {
      dialog?.close();
      return;
    }
    const opener =
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;
    dialog?.showModal();
    return () => {
      dialog?.close();
      opener?.focus();
    };
  }, [open]);

  return (
    <dialog
      ref={dialogRef}
      className="absence-dialog"
      aria-labelledby={titleId}
      onCancel={(event) => {
        event.preventDefault();
        onCancel();
      }}
    >
      <div className="rounded-2xl border border-slate-200 bg-white p-5 dark:border-slate-600 dark:bg-slate-900">
        <h2
          id={titleId}
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
            className="btn-secondary min-h-11"
            onClick={onCancel}
          >
            {cancelLabel}
          </button>
          <button
            type="button"
            className="btn-primary min-h-11"
            onClick={onConfirm}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </dialog>
  );
}
