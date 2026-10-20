import test from "node:test";
import assert from "node:assert/strict";
import {
  formatCalendarDate,
  inclusiveDays,
  localDate,
  presetRange,
  shiftDate,
  validRange,
} from "../src/utils/reportDates.ts";

test("calendar dates always use Asia/Almaty, not the browser timezone", () => {
  assert.equal(localDate(new Date("2026-10-20T18:59:59Z")), "2026-10-20");
  assert.equal(localDate(new Date("2026-10-20T19:00:00Z")), "2026-10-21");
  assert.equal(localDate(new Date("2024-02-29T19:30:00Z")), "2024-03-01");
});

test("report presets use Almaty calendar boundaries", () => {
  const now = new Date("2026-03-01T19:30:00Z");
  assert.deepEqual(presetRange("week", now), {
    startDate: "2026-02-23",
    endDate: "2026-03-01",
  });
  assert.deepEqual(presetRange("month", now), {
    startDate: "2026-02-01",
    endDate: "2026-02-28",
  });
});

test("calendar parsing is timezone-free and validates real dates", () => {
  assert.equal(shiftDate("2024-02-29", 1), "2024-03-01");
  assert.equal(inclusiveDays("2024-02-28", "2024-03-01"), 3);
  assert.equal(
    formatCalendarDate("2026-10-20", { dateStyle: "short" }),
    "20.10.2026",
  );
  assert.equal(
    validRange({ startDate: "2024-02-29", endDate: "2024-03-01" }),
    true,
  );
  assert.equal(
    validRange({ startDate: "2026-02-29", endDate: "2026-03-01" }),
    false,
  );
});
