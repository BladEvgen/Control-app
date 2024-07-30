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
    "со",
  ];

  const stringWithSpaces = string.replace(/_/g, " ");

  return stringWithSpaces
    .split(" ")
    .map((word, index) => {
      if (word.length === 3 || word.length === 4) {
        return word.toUpperCase();
      } else if (index === 0 || !exceptions.includes(word.toLowerCase())) {
        return word.charAt(0).toUpperCase() + word.slice(1).toLowerCase();
      } else {
        return word.toLowerCase();
      }
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

export const formatDate = (dateString: string | null) => {
  if (!dateString) return "Нет данных";
  const date = new Date(dateString);
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
};

export const formatMinutes = (totalMinutes: number) => {
  const hours = Math.floor(totalMinutes / 60);
  const minutes = Math.ceil(totalMinutes % 60);
  return `${hours}:${minutes < 10 ? "0" : ""}${minutes}`;
};
