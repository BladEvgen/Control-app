import { formatCalendarDate, parseDate, REPORT_TIME_ZONE } from "./reportDates";

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
    abbr.toLowerCase(),
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

export const formatDateRu = (dateString: string | null | undefined) => {
  if (!dateString) return "—";
  if (parseDate(dateString))
    return formatCalendarDate(dateString, {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
    });
  const date = new Date(dateString);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleDateString("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    timeZone: REPORT_TIME_ZONE,
  });
};

export const formatDateFromKeyRu = (dateString: string | null) => {
  if (!dateString) return "Нет данных";

  const [day, month, year] = dateString.split("-");

  return `${day}.${month}.${year}`;
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

export const extractTimezone = (isoString: string | null): string => {
  if (!isoString) return "+00:00";
  const timezoneMatch = isoString.match(/[+-]\d{2}:\d{2}$/);
  return timezoneMatch ? timezoneMatch[0] : "+00:00";
};

export const parseISOWithTimezone = (isoString: string | null): Date => {
  if (!isoString) return new Date();
  return new Date(isoString);
};

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

export const formatDate = formatTime;

export const formatMinutes = (totalMinutes: number) => {
  let hours = Math.floor(totalMinutes / 60);
  let minutes = Math.round(totalMinutes % 60);

  if (minutes === 60) {
    hours += 1;
    minutes = 0;
  }

  return `${hours}:${minutes < 10 ? "0" : ""}${minutes}`;
};

export const convertTimezoneFormat = (timezone: string): string => {
  if (timezone === "+00:00" || timezone === "-00:00") return "UTC";

  const invertedSign = timezone.startsWith("+") ? "-" : "+";
  const hours = parseInt(timezone.substr(1, 2), 10);

  return `Etc/GMT${invertedSign}${hours}`;
};

export const formatTimeRange = (
  firstInISO: string | null,
  lastOutISO: string | null,
): string => {
  if (!firstInISO || !lastOutISO) return "Нет данных";

  const firstIn = formatTimeWithSeconds(firstInISO);
  const lastOut = formatTimeWithSeconds(lastOutISO);

  return `${firstIn} - ${lastOut}`;
};
