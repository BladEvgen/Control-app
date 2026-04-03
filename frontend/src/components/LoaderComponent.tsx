type LoaderComponentProps = {
  message?: string;
  fullscreen?: boolean;
  compact?: boolean;
  inline?: boolean;
  variant?: "spinner" | "bars";
  className?: string;
  showGlow?: boolean;
};

const BAR_HEIGHTS_NORMAL = [14, 22, 28, 22, 14, 20];
const BAR_HEIGHTS_COMPACT = [9, 14, 18, 14, 9, 13];

const LoaderComponent = ({
  message = "Данные загружаются, пожалуйста, подождите...",
  fullscreen = true,
  compact = false,
  inline = false,
  variant = "spinner",
  className = "",
  showGlow = true,
}: LoaderComponentProps) => {
  const wrapperClassName = fullscreen ? "min-h-screen" : "min-h-0";
  const layoutClassName = inline
    ? "flex-row justify-start gap-3"
    : "flex-col justify-center items-center";
  const textToneClassName =
    variant === "bars" ? "text-current" : "dark:text-text-light text-text-dark";
  const textClassName = inline
    ? compact
      ? "text-xs sm:text-sm leading-snug"
      : "text-sm sm:text-base leading-snug"
    : compact
      ? "mt-2.5 text-sm text-center"
      : "mt-5 text-base sm:text-lg text-center";

  const barHeights = compact ? BAR_HEIGHTS_COMPACT : BAR_HEIGHTS_NORMAL;

  const loaderVisual =
    variant === "bars" ? (
      <div
        className="flex items-end"
        style={{ gap: compact ? "3px" : "4px" }}
        aria-hidden
      >
        {barHeights.map((h, i) => (
          <span
            key={i}
            className={`loader-bar ${
              i % 2 === 0
                ? "bg-gradient-to-t from-primary-600 via-primary-400 to-sky-300"
                : "bg-gradient-to-t from-secondary-600 via-secondary-400 to-fuchsia-300"
            }`}
            style={{
              width: compact ? "4px" : "5px",
              height: `${h}px`,
              animationDelay: `${i * 105}ms`,
              boxShadow: showGlow
                ? i % 2 === 0
                  ? "0 0 8px rgba(59,130,246,0.55)"
                  : "0 0 8px rgba(139,92,246,0.55)"
                : "none",
            }}
          />
        ))}
      </div>
    ) : (
      <div
        className="relative flex items-center justify-center"
        style={{ width: compact ? 48 : 64, height: compact ? 48 : 64 }}
        aria-hidden
      >
        {showGlow ? (
          <div
            className="loader-glow absolute inset-0 -m-4"
            style={{
              width: compact ? 72 : 96,
              height: compact ? 72 : 96,
              margin: "auto",
              top: 0,
              left: 0,
              right: 0,
              bottom: 0,
            }}
          />
        ) : null}
        <div className={compact ? "loader scale-75" : "loader"} />
      </div>
    );

  return (
    <div
      className={`flex items-center ${layoutClassName} ${wrapperClassName} ${className}`.trim()}
    >
      {loaderVisual}
      {message && (
        <p className={`${textClassName} ${textToneClassName} opacity-80`}>
          {message}
        </p>
      )}
    </div>
  );
};

export default LoaderComponent;
