import test from "node:test";
import assert from "node:assert/strict";
import {
  createLivenessEngine,
  LIVENESS_CHALLENGES,
  makeLivenessPlan,
  measureFace,
  type FaceSignals,
  type LivenessStep,
} from "../../src/faceLab/liveness/livenessEngine.ts";

type Pose = {
  yaw?: number;
  blink?: number;
  smile?: number;
  jaw?: number;
  x?: number;
};

function face({
  yaw = 0,
  blink = 0.05,
  smile = 0.05,
  jaw = 0.05,
  x = 0.5,
}: Pose = {}): FaceSignals {
  const landmarks = Array.from({ length: 300 }, (_, i) => ({
    x: x - 0.15 + (i % 10) * (0.3 / 9),
    y: 0.35 + Math.floor(i / 30) * (0.3 / 9),
  }));
  landmarks[33] = { x: x - 0.05, y: 0.45 };
  landmarks[263] = { x: x + 0.05, y: 0.45 };
  landmarks[1] = { x: x + yaw * 0.1, y: 0.52 };
  return {
    landmarks,
    blendshapes: {
      eyeBlinkLeft: blink,
      eyeBlinkRight: blink,
      mouthSmileLeft: smile,
      mouthSmileRight: smile,
      jawOpen: jaw,
    },
  };
}

function runner(random = () => 0.1) {
  const engine = createLivenessEngine(random);
  let now = 0;
  const feed = (f: FaceSignals | null, ms = 100) => {
    now += ms;
    return engine.update(f, now);
  };
  return { engine, feed };
}

function perform(step: LivenessStep, feed: ReturnType<typeof runner>["feed"]) {
  if (step === "face" || step === "hold")
    for (let i = 0; i < 8; i++) feed(face());
  if (step === "blink")
    [0.05, 0.8, 0.05].forEach((b) => feed(face({ blink: b })));
  if (step === "smile") [0.7, 0.7].forEach((s) => feed(face({ smile: s })));
  if (step === "mouth_open") [0.7, 0.7].forEach((j) => feed(face({ jaw: j })));
  if (step === "turn_left" || step === "turn_right") {
    const y = step === "turn_left" ? 0.4 : -0.4;
    feed(face({ yaw: y }));
    feed(face({ yaw: y }));
    feed(face());
  }
}

test("yaw is measured relative to the eyes, so sliding the head is not a turn", () => {
  assert.equal(measureFace(face({ x: 0.4 }))!.yaw, 0);
  assert.ok(measureFace(face({ yaw: 0.4 }))!.yaw > 0.3);
});

test("plan: face first, three random distinct actions, always ends on hold", () => {
  const seen = new Set<string>();
  for (const r of [0, 0.2, 0.45, 0.7, 0.99]) {
    const plan = makeLivenessPlan(() => r);
    assert.equal(plan[0], "face");
    assert.equal(plan.at(-1), "hold");
    const actions = plan.slice(1, -1);
    assert.equal(actions.length, 3);
    assert.equal(new Set(actions).size, 3);
    for (const a of actions)
      assert.ok(LIVENESS_CHALLENGES.includes(a as never));
    actions.forEach((a) => seen.add(a));
  }
  assert.ok(seen.size >= 4, "different seeds pick different actions");
});

test("a live person following every step passes, whatever actions were drawn", () => {
  for (const r of [0, 0.2, 0.45, 0.7, 0.99]) {
    const { engine, feed } = runner(() => r);
    for (const step of engine.plan) perform(step, feed);
    assert.equal(feed(face()).phase, "passed", engine.plan.join(","));
  }
});

test("turning the wrong way does not count and says which way to turn", () => {
  const seed = [0.1, 0.3, 0.5, 0.7, 0.9].find((r) =>
    makeLivenessPlan(() => r).some((s) => s.startsWith("turn_")),
  )!;
  const { engine, feed } = runner(() => seed);
  const plan = engine.plan;
  for (const step of plan.slice(
    0,
    plan.findIndex((s) => s.startsWith("turn_")),
  )) {
    perform(step, feed);
  }
  const turn = plan.find((s) => s.startsWith("turn_"))!;
  const wrong = turn === "turn_left" ? -0.4 : 0.4;
  const f = feed(face({ yaw: wrong }));
  assert.equal(f.phase, turn);
  assert.match(f.hint, /Не в ту сторону/);
});

test("losing the face mid-check restarts from the first step", () => {
  const { feed } = runner();
  perform("face", feed);
  assert.notEqual(feed(face()).phase, "face");
  assert.notEqual(
    feed(null, 500).phase,
    "face",
    "a short glitch keeps progress",
  );
  assert.equal(feed(null, 1000).phase, "face");
});

test("blink threshold adapts to a person whose open eyes already score high", () => {
  const { engine, feed } = runner(() => 0.99);
  assert.equal(engine.plan[1], "blink");
  for (let i = 0; i < 8; i++) feed(face({ blink: 0.3 }));
  feed(face({ blink: 0.5 }));
  assert.equal(
    feed(face({ blink: 0.3 })).phase,
    "blink",
    "0.5 is not a blink for this baseline",
  );
});
