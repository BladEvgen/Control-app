export const formatDepartmentName = (string: string) => {
  const exceptions = [
    "и",
    "в",
    "на",
    "под",
    "с",
    "у",
    "о",
    "за",
    "до",
    "от",
    "к",
    "по",
    "из",
    "об",
    "без",
    "про",
    "для",
    "при",
    "через",
    "над",
    "во",
    "со",
  ];

  const abbreviations = ["крму", "ппс", "ауп"].map((abbr) =>
    abbr.toLowerCase()
  );

  const stringWithSpaces = string.replace(/_/g, " ");

  return stringWithSpaces
    .split(" ")
    .map((word, index, words) => {
      const lowerWord = word.toLowerCase();

      if (abbreviations.includes(lowerWord)) {
        return word.toUpperCase();
      }

      if (index === 0 || !exceptions.includes(lowerWord)) {
        if (lowerWord.includes("им.")) {
          const [prefix, rest] = word.split("им.");
          return (
            prefix.charAt(0).toUpperCase() +
            prefix.slice(1).toLowerCase() +
            " им. " +
            rest.charAt(0).toUpperCase() +
            ". " +
            rest.slice(1).toLowerCase()
          );
        }

        if (index > 0 && words[index - 1].toLowerCase().includes("им.")) {
          return word.charAt(0).toUpperCase() + word.slice(1).toLowerCase();
        }

        return word.charAt(0).toUpperCase() + word.slice(1).toLowerCase();
      }

      return word.toLowerCase();
    })
    .join(" ");
};

export const formatDateRu = (dateString: string) => {
  const date = new Date(dateString);
  const day = date.getDate().toString().padStart(2, "0");
  const month = (date.getMonth() + 1).toString().padStart(2, "0");
  const year = date.getFullYear();
  return `${day}.${month}.${year}`;
};

export const formatDateFromKeyRu = (dateString: string | null) => {
  if (!dateString) return "Нет данных";

  const [day, month, year] = dateString.split("-");

  return `${day}.${month}.${year}`;
};

export const formatNumber = (value: number | undefined | null): string => {
  if (value === undefined || value === null) return "Не установлена";

  const src = value.toString();
  const [out, rnd = "0"] = src.includes(".") ? src.split(".") : [src];

  const chunks = [];
  let i = out.length;
  while (i > 0) {
    chunks.unshift(out.substring(Math.max(i - 3, 0), i));
    i -= 3;
  }

  const formattedOut = chunks.join(" ");
  return `${formattedOut}.${rnd} ₸`;
};

export const declensionDays = (daysCount: number) => {
  if (daysCount % 10 === 1 && daysCount % 100 !== 11) {
    return "день";
  } else if (
    daysCount % 10 >= 2 &&
    daysCount % 10 <= 4 &&
    (daysCount % 100 < 10 || daysCount % 100 >= 20)
  ) {
    return "дня";
  } else {
    return "дней";
  }
};

/**
 * Извлекает временную зону из ISO строки
 * @param isoString ISO строка с датой
 * @returns Строка с временной зоной в формате +HH:MM или -HH:MM
 */
export const extractTimezone = (isoString: string | null): string => {
  if (!isoString) return "+00:00";
  const timezoneMatch = isoString.match(/[+-]\d{2}:\d{2}$/);
  return timezoneMatch ? timezoneMatch[0] : "+00:00"; 
};

/**
 * Парсит ISO строку с учетом временной зоны
 * @param isoString ISO строка с датой и временной зоной
 * @returns Объект Date
 */
export const parseISOWithTimezone = (isoString: string | null): Date => {
  if (!isoString) return new Date();
  return new Date(isoString);
};

/**
 * Форматирует время из ISO строки, сохраняя временную зону
 * @param dateString ISO строка с датой
 * @returns Строка с отформатированным временем (HH:MM)
 */
export const formatTime = (dateString: string | null): string => {
  if (!dateString) return "Нет данных";

  const timezone = extractTimezone(dateString);
  const date = parseISOWithTimezone(dateString);

  return date.toLocaleTimeString("ru-RU", {
    hour: "2-digit",
    minute: "2-digit",
    timeZone: convertTimezoneFormat(timezone),
  });
};

/**
 * Форматирует время из ISO строки, включая секунды, с сохранением временной зоны
 * @param dateString ISO строка с датой
 * @returns Строка с отформатированным временем (HH:MM:SS)
 */
export const formatTimeWithSeconds = (dateString: string | null): string => {
  if (!dateString) return "Нет данных";

  const timezone = extractTimezone(dateString);
  const date = parseISOWithTimezone(dateString);

  return date.toLocaleTimeString("ru-RU", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    timeZone: convertTimezoneFormat(timezone),
  });
};

/**
 * Алиас для обратной совместимости с предыдущим API
 */
export const formatDate = formatTime;

/**
 * Форматирует количество минут в строку (HH:MM)
 * @param totalMinutes Общее количество минут
 * @returns Строка в формате HH:MM
 */
export const formatMinutes = (totalMinutes: number) => {
  let hours = Math.floor(totalMinutes / 60);
  let minutes = Math.round(totalMinutes % 60);

  if (minutes === 60) {
    hours += 1;
    minutes = 0;
  }

  return `${hours}:${minutes < 10 ? "0" : ""}${minutes}`;
};

/**
 * Форматирует ISO дату с учетом временной зоны
 * @param isoString ISO строка с датой
 * @param format Формат вывода: time, date или datetime
 * @returns Форматированная строка
 */
export const formatISOWithTimezone = (
  isoString: string | null,
  format: "time" | "date" | "datetime" = "time"
): string => {
  if (!isoString) return "Нет данных";

  const timezone = extractTimezone(isoString);
  const date = parseISOWithTimezone(isoString);
  const timeZoneOption = convertTimezoneFormat(timezone);

  // Определяем формат вывода
  if (format === "time") {
    return date.toLocaleTimeString("ru-RU", {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      timeZone: timeZoneOption,
    });
  } else if (format === "date") {
    return date.toLocaleDateString("ru-RU", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
      timeZone: timeZoneOption,
    });
  } else {
    return date.toLocaleString("ru-RU", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      timeZone: timeZoneOption,
    });
  }
};

/**
 * Конвертирует формат временной зоны из ISO (+05:00) в формат Etc/GMT
 * @param timezone Строка с временной зоной в формате +HH:MM или -HH:MM
 * @returns Строка с временной зоной в формате для использования в опциях toLocaleString
 */
export const convertTimezoneFormat = (timezone: string): string => {
  if (timezone === "+00:00" || timezone === "-00:00") return "UTC";

  const invertedSign = timezone.startsWith("+") ? "-" : "+";
  const hours = parseInt(timezone.substr(1, 2), 10);

  return `Etc/GMT${invertedSign}${hours}`;
};

/**
 * Форматирует диапазон времени с сохранением временной зоны
 * @param firstInISO ISO строка с начальным временем
 * @param lastOutISO ISO строка с конечным временем
 * @returns Строка в формате "HH:MM - HH:MM"
 */
export const formatTimeRange = (
  firstInISO: string | null,
  lastOutISO: string | null
): string => {
  if (!firstInISO || !lastOutISO) return "Нет данных";

  const firstIn = formatTimeWithSeconds(firstInISO);
  const lastOut = formatTimeWithSeconds(lastOutISO);

  return `${firstIn} - ${lastOut}`;
};
