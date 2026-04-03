import type { Aspect } from "./types";

export function vibrate(pattern: number | number[]): void {
  try {
    if (navigator.vibrate) {
      navigator.vibrate(pattern);
    }
  } catch {
    /* ignore */
  }
}

export function playShutterSound(): void {
  try {
    const AudioCtx = window.AudioContext || (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    if (!AudioCtx) return;

    const ctx = new AudioCtx();

    const createTone = (frequency: number, startTime: number): void => {
      const oscillator = ctx.createOscillator();
      const gainNode = ctx.createGain();

      oscillator.connect(gainNode);
      gainNode.connect(ctx.destination);

      oscillator.frequency.value = frequency;
      gainNode.gain.setValueAtTime(0.0001, startTime);
      gainNode.gain.exponentialRampToValueAtTime(0.3, startTime + 0.005);
      gainNode.gain.exponentialRampToValueAtTime(0.0001, startTime + 0.06);

      oscillator.start(startTime);
      oscillator.stop(startTime + 0.07);
    };

    createTone(1400, ctx.currentTime);
    createTone(1100, ctx.currentTime + 0.04);

    vibrate([35]);
  } catch {
    /* ignore */
  }
}

export function getAspectRatio(aspect: Aspect): number {
  switch (aspect) {
    case "1:1":
      return 1;
    case "9:16":
      return 9 / 16;
    case "4:3":
      return 4 / 3;
    case "16:9":
      return 16 / 9;
    case "3:4":
    default:
      return 3 / 4;
  }
}
