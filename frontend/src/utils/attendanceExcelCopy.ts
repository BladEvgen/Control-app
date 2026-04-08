function excelFileWord(n: number): "файл" | "файла" | "файлов" {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod100 >= 11 && mod100 <= 14) return "файлов";
  if (mod10 === 1) return "файл";
  if (mod10 >= 2 && mod10 <= 4) return "файла";
  return "файлов";
}

export function attendanceExcelInProgressTitle(active: number): string {
  if (active <= 0) return "";
  const n = active;
  const w = excelFileWord(n);
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod10 === 1 && (mod100 < 11 || mod100 > 14)) {
    return `Готовится ${n} ${w} Excel`;
  }
  return `Готовятся ${n} ${w} Excel`;
}

export function attendanceExcelInProgressDetail(active: number): string {
  if (active <= 0) return "";
  if (active === 1) {
    return "Подготовка на сервере может занять время. Не закрывайте вкладку.";
  }
  const n = active;
  const w = excelFileWord(n);
  return `Одновременно формируются ${n} ${w}. Окно сохранения откроется для каждого по готовности. Не закрывайте вкладку.`;
}
