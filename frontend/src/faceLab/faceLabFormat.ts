export function formatServerElapsed(ms: number): string {
  if (!Number.isFinite(ms) || ms < 0) {
    return "—";
  }
  if (ms < 500) {
    return `менее полсекунды (${Math.round(ms)} мс)`;
  }
  if (ms < 1000) {
    return `около секунды (${Math.round(ms)} мс)`;
  }
  const sec = ms / 1000;
  if (sec < 10) {
    const s = Math.round(sec * 10) / 10;
    const tail = s === Math.floor(s) ? `${Math.floor(s)}` : `${s}`.replace(".", ",");
    return `около ${tail} с`;
  }
  if (sec < 60) {
    return `около ${Math.round(sec)} с`;
  }
  const min = Math.floor(sec / 60);
  const restSec = Math.round(sec - min * 60);
  if (restSec === 0) {
    return min === 1 ? "около 1 мин" : `около ${min} мин`;
  }
  return `${min} мин ${restSec} с`;
}
