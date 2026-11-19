export type StatTone = "good" | "neutral" | "warn" | "bad";

export interface ReportStat {
  label: string;
  value: number;
  tone: StatTone;
  hint: string;
  change?: boolean;
}

export interface ReportIssue {
  where: string;
  text: string;
}

export interface ImportReport {
  target: string;
  stats: ReportStat[];
  issues: ReportIssue[];
  issuesTotal: number;
  notes: string[];
  rowsRead?: number;
  changed: number;
  attention: boolean;
}

type Detail = Record<string, unknown>;

const num = (v: unknown): number => (typeof v === "number" ? v : 0);
const obj = (v: unknown): Detail =>
  v && typeof v === "object" ? (v as Detail) : {};
const strings = (v: unknown): string[] =>
  Array.isArray(v) ? v.map(String) : [];

const SOURCES: Record<string, string> = { dep: "Отделы", hum: "Сотрудники" };

export const parseIssue = (line: string): ReportIssue => {
  const staff = /^(dep|hum):\s*(?:(\d+):)?\s*(.*)$/s.exec(line);
  if (staff) {
    const where = SOURCES[staff[1]] + (staff[2] ? `, запись №${staff[2]}` : "");
    return { where, text: staff[3] };
  }
  const row = /^Строка (\d+):\s*(.*)$/s.exec(line);
  if (row) return { where: `Запись №${row[1]}`, text: row[2] };
  const named = /^([^:\s][^:]{0,79}):\s(.+)$/s.exec(line);
  if (named) return { where: named[1], text: named[2] };
  return { where: "", text: line };
};

const optional = (stats: ReportStat[]) =>
  stats.filter((s) => s.value > 0 || s.tone === "good" || s.change);

const departmentStats = (d: Detail): ReportStat[] => [
  {
    label: "Создано",
    value: num(d.created),
    tone: "good",
    hint: "Новые отделы, которых не было в базе",
    change: true,
  },
  {
    label: "Переименовано",
    value: num(d.renamed),
    tone: "neutral",
    hint: "Тот же номер отдела, новое название",
    change: true,
  },
  {
    label: "Перенесено",
    value: num(d.reparented),
    tone: "neutral",
    hint: "Отдел переехал под другого родителя",
    change: true,
  },
  {
    label: "Без изменений",
    value: num(d.untouched),
    tone: "neutral",
    hint: "Уже совпадали с файлом",
  },
];

const stubStat = (d: Detail): ReportStat => ({
  label: "Отделы-заглушки",
  value: num(d.stubs_created),
  tone: "warn",
  hint: "Отдела из файла не было в базе, создан пустой. Проверьте название",
  change: false,
});

const build = (
  category: string,
  detail: Detail,
): Omit<ImportReport, "changed" | "attention"> => {
  const errors = strings(detail.errors);
  const simpleIssues = errors.map(parseIssue);
  switch (category) {
    case "departments":
    case "staff": {
      const deps = obj(detail.departments);
      const staff = obj(detail.staff);
      const invariants = obj(detail.invariants);
      const notes: string[] = [];
      const merged = strings(deps.merged);
      if (merged.length) notes.push(`Объединены отделы: ${merged.join(", ")}`);
      const orphans = num(invariants.staff_without_department_after);
      if (orphans > 0)
        notes.push(
          `Сотрудников без отдела в базе: ${orphans} (было ${num(invariants.staff_without_department_before)})`,
        );
      if (detail.dry_run)
        notes.push("Пробный запуск: в базу ничего не записано.");
      const skipped = strings(detail.rows_skipped);
      const stats =
        category === "departments"
          ? [...departmentStats(deps), stubStat(deps)]
          : [
              {
                label: "Новых",
                value: num(staff.created),
                tone: "good" as const,
                hint: "Добавлены в базу",
                change: true,
              },
              {
                label: "Обновлено",
                value: num(staff.updated),
                tone: "neutral" as const,
                hint: "Изменились ФИО, отдел или должность",
                change: true,
              },
              {
                label: "Без изменений",
                value: num(staff.unchanged),
                tone: "neutral" as const,
                hint: "Данные уже совпадали с файлом",
              },
              {
                label: "Должности выставлены",
                value: num(staff.positions_assigned),
                tone: "neutral" as const,
                hint: "Сотрудникам привязана должность из файла",
              },
              {
                label: "В архив",
                value: num(staff.archived),
                tone: "warn" as const,
                hint: "Их не было в файле. Скрыты из отчётов, записи сохранены",
                change: num(staff.archived) > 0,
              },
              {
                label: "Архивные пропущены",
                value: num(staff.skipped_archived),
                tone: "neutral" as const,
                hint: "Есть в файле, но уже в архиве, поэтому не меняются",
              },
              stubStat(deps),
            ];
      return {
        target:
          category === "departments" ? "Дерево отделов" : "Список сотрудников",
        stats: optional(stats),
        issues: skipped.map(parseIssue),
        issuesTotal: Math.max(num(detail.rows_skipped_total), skipped.length),
        notes,
        rowsRead: num(detail.rows_read) || undefined,
      };
    }
    case "photo": {
      const rejected =
        num(detail.skipped_bad_member) + num(detail.skipped_too_large);
      return {
        target: "Фото сотрудников (аватары)",
        stats: optional([
          {
            label: "Фото обновлено",
            value: num(detail.updated),
            tone: "good",
            hint: "Аватар заменён на фото из архива",
            change: true,
          },
          {
            label: "PIN не найден",
            value: num(detail.skipped_unknown_pin),
            tone: "warn",
            hint: "Имя файла не совпало ни с одним PIN сотрудника",
          },
          {
            label: "Нет лица анфас",
            value: num(detail.skipped_bad_face),
            tone: "warn",
            hint: "Лицо не найдено или снято не прямо, аватар не заменён",
          },
          {
            label: "Файлы отклонены",
            value: rejected,
            tone: "bad",
            hint: "Не картинка, плохое имя или больше допустимого размера",
          },
        ]),
        issues: simpleIssues,
        issuesTotal: errors.length,
        notes: [],
      };
    }
    case "public_holidays":
    case "load_geo":
      return {
        target:
          category === "load_geo"
            ? "Точки занятий для геоотметок"
            : "Календарь праздников",
        stats: [
          {
            label: "Добавлено",
            value: num(detail.created),
            tone: "good",
            hint: category === "load_geo" ? "Новые точки" : "Новые даты",
            change: true,
          },
          {
            label: "Обновлено",
            value: num(detail.updated),
            tone: "neutral",
            hint:
              category === "load_geo"
                ? "Совпали название и адрес, обновлены координаты и радиус"
                : "Дата уже была, обновлены название и признак рабочего дня",
            change: true,
          },
        ],
        issues: simpleIssues,
        issuesTotal: errors.length,
        notes: [],
      };
    case "delete_staff":
      return {
        target: detail.parent
          ? `Сотрудники подразделения «${String(detail.parent)}»`
          : "Сотрудники подразделения",
        stats: [
          {
            label: "Удалено записей",
            value: num(detail.deleted),
            tone: "bad",
            hint: "Сотрудники и связанные с ними записи, которых не было в списке",
            change: true,
          },
          {
            label: "PIN в файле",
            value: num(detail.kept_pins),
            tone: "neutral",
            hint: "Эти сотрудники оставлены",
          },
          {
            label: "Подотделов",
            value: num(detail.child_departments),
            tone: "neutral",
            hint: "Где искали сотрудников",
          },
        ],
        issues: [],
        issuesTotal: 0,
        notes: [],
      };
    default:
      return {
        target: "",
        stats: [],
        issues: simpleIssues,
        issuesTotal: errors.length,
        notes: [],
      };
  }
};

export const buildImportReport = (
  category: string,
  detail: Detail | null | undefined,
): ImportReport => {
  const report = build(category, detail ?? {});
  const changed = report.stats.reduce(
    (sum, s) => sum + (s.change ? s.value : 0),
    0,
  );
  const attention =
    report.issuesTotal > 0 ||
    report.stats.some(
      (s) =>
        !s.change && s.value > 0 && (s.tone === "warn" || s.tone === "bad"),
    );
  return { ...report, changed, attention };
};

export const failureNote = (category: string): string =>
  category === "photo"
    ? "Фото, обработанные до ошибки, уже сохранены. Остальные не тронуты."
    : category === "delete_staff"
      ? "Удаление не выполнено."
      : "Изменения откатены, в базе всё как до импорта.";
