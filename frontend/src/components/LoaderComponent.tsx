type LoaderComponentProps = {
  message?: string;
  fullscreen?: boolean;
  compact?: boolean;
  inline?: boolean;
  variant?: "spinner" | "bars";
  className?: string;
  showGlow?: boolean;
  messageClassName?: string;
};

const LoaderComponent = ({
  message = "Загрузка…",
  fullscreen = true,
  compact = false,
  inline = false,
  className = "",
  messageClassName,
}: LoaderComponentProps) => (
  <div
    role="status"
    className={`ws-loader ${inline ? "is-inline" : ""} ${fullscreen ? "is-fullscreen" : ""} ${compact ? "is-compact" : ""} ${className}`}
  >
    <span className="ws-loader-ring" aria-hidden />
    {message ? (
      <p className={messageClassName ?? "ws-loader-text"}>{message}</p>
    ) : (
      <span className="sr-only">Загрузка</span>
    )}
  </div>
);

export default LoaderComponent;
