import test from "node:test";
import assert from "node:assert/strict";
import { buildImportReport, parseIssue } from "../src/utils/importReport.ts";

test("staff skip lines name the source file and record", () => {
  assert.deepEqual(parseIssue("hum:12: дубль pin 7 в файле"), {
    where: "Сотрудники, запись №12",
    text: "дубль pin 7 в файле",
  });
  assert.deepEqual(parseIssue("dep: отдел 5: родитель 9 не найден"), {
    where: "Отделы",
    text: "отдел 5: родитель 9 не найден",
  });
  assert.deepEqual(parseIssue("Строка 3: Неверный формат даты."), {
    where: "Запись №3",
    text: "Неверный формат даты.",
  });
  assert.deepEqual(parseIssue("1234.jpg: лицо не найдено"), {
    where: "1234.jpg",
    text: "лицо не найдено",
  });
});

test("staff report hides empty optional stats and counts changes", () => {
  const r = buildImportReport("staff", {
    departments: { stubs_created: 0 },
    staff: {
      created: 2,
      updated: 3,
      unchanged: 0,
      archived: 0,
      positions_assigned: 1,
    },
    rows_skipped: ["hum:4: пустой ID сотрудника"],
    rows_skipped_total: 9,
  });
  assert.deepEqual(
    r.stats.map((s) => [s.label, s.value]),
    [
      ["Новых", 2],
      ["Обновлено", 3],
      ["Должности выставлены", 1],
    ],
  );
  assert.equal(r.changed, 5);
  assert.equal(r.issuesTotal, 9);
  assert.equal(r.issues[0].where, "Сотрудники, запись №4");
});

test("photo report sums rejected files and keeps errors", () => {
  const r = buildImportReport("photo", {
    updated: 0,
    skipped_unknown_pin: 4,
    skipped_bad_member: 1,
    skipped_too_large: 2,
    skipped_bad_face: 0,
    errors: ["9.jpg: нет лица"],
  });
  assert.deepEqual(
    r.stats.map((s) => [s.label, s.value]),
    [
      ["Фото обновлено", 0],
      ["PIN не найден", 4],
      ["Файлы отклонены", 3],
    ],
  );
  assert.equal(r.changed, 0);
  assert.equal(r.issuesTotal, 1);
});

test("delete, holidays and geo keep their own keys", () => {
  assert.equal(
    buildImportReport("delete_staff", { deleted: 7, parent: "Мед" }).changed,
    7,
  );
  assert.equal(
    buildImportReport("delete_staff", { parent: "Мед" }).target,
    "Сотрудники подразделения «Мед»",
  );
  assert.equal(
    buildImportReport("load_geo", { created: 1, updated: 2 }).changed,
    3,
  );
  assert.equal(buildImportReport("public_holidays", null).changed, 0);
});

test("expected deletions are not flagged, skipped rows are", () => {
  assert.equal(
    buildImportReport("delete_staff", { deleted: 7 }).attention,
    false,
  );
  assert.equal(
    buildImportReport("photo", { skipped_unknown_pin: 1 }).attention,
    true,
  );
  assert.equal(
    buildImportReport("load_geo", { errors: ["Строка 1: x"] }).attention,
    true,
  );
  assert.equal(
    buildImportReport("staff", { staff: { archived: 3 } }).attention,
    false,
  );
});

test("rows read goes to the subtitle, not to the notes", () => {
  const r = buildImportReport("staff", {
    rows_read: 8175,
    staff: { created: 1 },
  });
  assert.equal(r.rowsRead, 8175);
  assert.deepEqual(r.notes, []);
});
