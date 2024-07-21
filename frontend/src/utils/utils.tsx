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
