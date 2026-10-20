import { FaVolumeMute } from "react-icons/fa";
import type { FaceLabVoiceLang } from "./faceLabCameraVoice";

const OPTIONS: { value: FaceLabVoiceLang; label: string; title: string }[] = [
  { value: "off", label: "", title: "Без голоса" },
  { value: "ru", label: "RU", title: "Голос на русском" },
  { value: "kk", label: "KZ", title: "Голос на казахском" },
  { value: "en", label: "EN", title: "Голос на английском" },
];

export function FaceLabVoiceSwitch({
  value,
  onChange,
}: {
  value: FaceLabVoiceLang;
  onChange: (v: FaceLabVoiceLang) => void;
}) {
  return (
    <div className="facelab-voice">
      <span className="facelab-voice-label" id="facelab-voice-label">
        Голосовые подсказки
      </span>
      <div
        className="facelab-seg"
        role="group"
        aria-labelledby="facelab-voice-label"
      >
        {OPTIONS.map((o) => (
          <button
            key={o.value}
            type="button"
            aria-pressed={value === o.value}
            aria-label={o.title}
            title={o.title}
            onClick={() => onChange(o.value)}
          >
            {o.label || <FaVolumeMute aria-hidden />}
          </button>
        ))}
      </div>
    </div>
  );
}
