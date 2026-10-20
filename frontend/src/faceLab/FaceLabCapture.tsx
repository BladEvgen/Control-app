import { useDropzone } from "react-dropzone";
import { FaCamera, FaFolderOpen, FaRedo } from "react-icons/fa";
import { PoseGuide } from "./liveness";

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} Б`;
  if (bytes < 1024 * 1024)
    return `${(bytes / 1024).toFixed(bytes < 10240 ? 1 : 0)} КБ`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} МБ`;
}

type Props = {
  file: File | null;
  previewUrl: string | null;
  onOpenCamera: () => void;
  onPickFile: () => void;
  onDropFile: (file: File) => void;
  submit?: {
    label: string;
    busyLabel: string;
    busy: boolean;
    onClick: () => void;
  };
};

export function FaceLabCapture({
  file,
  previewUrl,
  onOpenCamera,
  onPickFile,
  onDropFile,
  submit,
}: Props) {
  const { getRootProps, isDragActive } = useDropzone({
    onDrop: (files) => {
      if (files[0]) onDropFile(files[0]);
    },
    multiple: false,
    noClick: true,
    noKeyboard: true,
    accept: { "image/jpeg": [".jpg", ".jpeg"], "image/png": [".png"] },
  });

  if (!previewUrl) {
    return (
      <div
        {...getRootProps({
          className: "facelab-drop",
          "data-active": isDragActive || undefined,
        })}
      >
        <span className="facelab-drop-art">
          <PoseGuide pose="front" size={72} />
        </span>
        <p className="facelab-drop-title">
          {isDragActive ? "Отпустите фото здесь" : "Снимите лицо камерой"}
        </p>
        <p className="facelab-drop-hint">
          <span className="facelab-drop-dnd">
            Или перетащите сюда фото JPG или PNG.{" "}
          </span>
          Лицо прямо, свет ровный.
        </p>
        <div className="facelab-drop-actions">
          <button
            type="button"
            className="ws-btn-primary facelab-btn-lg"
            onClick={onOpenCamera}
          >
            <FaCamera aria-hidden />
            Открыть камеру
          </button>
          <button
            type="button"
            className="ws-btn-ghost facelab-btn-lg"
            onClick={onPickFile}
          >
            <FaFolderOpen aria-hidden />
            Выбрать файл
          </button>
        </div>
      </div>
    );
  }

  return (
    <div
      className="facelab-preview"
      {...getRootProps({ "data-active": isDragActive || undefined })}
    >
      <figure className="facelab-preview-frame">
        <img src={previewUrl} alt="Снимок для проверки" />
        <figcaption>
          <span className="facelab-preview-name">{file?.name ?? "снимок"}</span>
          {file ? <span>{formatFileSize(file.size)}</span> : null}
        </figcaption>
      </figure>
      <div className="facelab-preview-actions">
        <button type="button" className="ws-btn-ghost" onClick={onOpenCamera}>
          <FaRedo aria-hidden />
          Переснять
        </button>
        <button type="button" className="ws-btn-ghost" onClick={onPickFile}>
          <FaFolderOpen aria-hidden />
          Другой файл
        </button>
        {submit ? (
          <button
            type="button"
            className="ws-btn-primary facelab-preview-submit"
            disabled={submit.busy}
            onClick={submit.onClick}
          >
            {submit.busy ? submit.busyLabel : submit.label}
          </button>
        ) : null}
      </div>
    </div>
  );
}
