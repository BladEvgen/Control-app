import test from "node:test";
import assert from "node:assert/strict";
import {
  ovalInFrame,
  screenBoxToVideo,
} from "../../src/faceLab/camera/ovalGeometry.ts";
import {
  createLivenessEngine,
  type FaceSignals,
  type FaceView,
} from "../../src/faceLab/liveness/livenessEngine.ts";

const close = (a: number, b: number) =>
  assert.ok(Math.abs(a - b) < 0.005, `${a} vs ${b}`);

test("portrait phone shows only the middle quarter of a landscape stream", () => {
  const box = screenBoxToVideo(
    { left: 0, top: 0, w: 390, h: 844 },
    { w: 390, h: 844 },
    { w: 1920, h: 1080 },
    false,
  );
  close(box.x, 0.37);
  close(box.w, 0.26);
  close(box.y, 0);
  close(box.h, 1);
});

test("mirroring flips the box around the frame centre", () => {
  const left = { left: 0, top: 0, w: 100, h: 100 };
  const size = { w: 400, h: 400 };
  const raw = screenBoxToVideo(left, size, size, false);
  const mir = screenBoxToVideo(left, size, size, true);
  close(raw.x, 0);
  close(mir.x, 0.75);
});

test("oval is larger on portrait than before and unchanged on landscape", () => {
  assert.ok(ovalInFrame({ w: 360, h: 480 }).rx > 360 * 0.3);
  close(ovalInFrame({ w: 1000, h: 750 }).rx / 750, 0.27);
});

function face(cx: number, cy: number, w: number): FaceSignals {
  const h = w * 1.3;
  const landmarks = Array.from({ length: 300 }, (_, i) => ({
    x: cx - w / 2 + (i % 10) * (w / 9),
    y: cy - h / 2 + Math.floor(i / 30) * (h / 9),
  }));
  landmarks[33] = { x: cx - w / 6, y: cy };
  landmarks[263] = { x: cx + w / 6, y: cy };
  landmarks[1] = { x: cx, y: cy + h / 10 };
  return { landmarks, blendshapes: {} };
}

test("a face filling the on-screen oval of a cropped phone view passes the face step", () => {
  const frame = { w: 390, h: 520 };
  const o = ovalInFrame(frame);
  const view: FaceView = screenBoxToVideo(
    {
      left: o.cx - o.rx,
      top: (844 - 520) / 2 + o.cy - o.ry,
      w: o.rx * 2,
      h: o.ry * 2,
    },
    { w: 390, h: 844 },
    { w: 1920, h: 1080 },
    true,
  );
  const f = face(view.x + view.w / 2, view.y + view.h / 2, view.w * 0.8);
  assert.ok(view.w * 0.8 < 0.2);
  const engine = createLivenessEngine(() => 0.99);
  let t = 0;
  for (let i = 0; i < 8; i++) engine.update(f, (t += 100), view);
  assert.notEqual(engine.update(f, (t += 100), view).phase, "face");
});

test("hysteresis: a half-off face cannot enter the oval but does not fall out once inside", () => {
  const off = face(0.5 + 0.18 * 0.55, 0.5, 0.3); // centre at 0.55 of the oval radius
  const fresh = createLivenessEngine(() => 0.99);
  assert.match(fresh.update(off, 100).hint, /центр овала/);

  const inside = createLivenessEngine(() => 0.99);
  inside.update(face(0.5, 0.5, 0.3), 100);
  assert.doesNotMatch(inside.update(off, 200).hint, /центр овала/);
});
