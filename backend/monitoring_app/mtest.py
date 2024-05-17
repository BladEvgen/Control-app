import requests
import pandas as pd
from openpyxl import Workbook
from datetime import datetime
from openpyxl.styles import Font, Alignment
from openpyxl.utils.dataframe import dataframe_to_rows

url = "http://localhost:8000/api/department/stats/10028/?end_date=2024-04-23&start_date=2024-04-21"
response = requests.get(url)
data = response.json()

rows = []

for attendance in data["attendance"]:
    for date, records in attendance.items():
        for record in records:
            department_name = data["department_name"]
            staff_fio = record.get("staff_fio")
            date_obj = datetime.strptime(date, "%Y-%m-%d")
            date_str = date_obj.strftime("%d.%m.%Y")

            if record["first_in"] is None and record["last_out"] is None:
                if date_obj.weekday() < 5:
                    attendance_info = "Отсутствие"
                else:
                    attendance_info = "Выходной"
            else:
                if date_obj.weekday() < 5:
                    first_in = (
                        datetime.strptime(
                            record["first_in"], "%Y-%m-%dT%H:%M:%S+05:00"
                        ).strftime("%H:%M:%S")
                        if record["first_in"]
                        else None
                    )
                    last_out = (
                        datetime.strptime(
                            record["last_out"], "%Y-%m-%dT%H:%M:%S+05:00"
                        ).strftime("%H:%M:%S")
                        if record["last_out"]
                        else None
                    )
                    attendance_info = (
                        f"{first_in} - {last_out}"
                        if first_in and last_out
                        else "Отсутствие"
                    )
                else:
                    attendance_info = "Отсутствие"

            rows.append([staff_fio, date_str, attendance_info])

df = pd.DataFrame(rows, columns=["ФИО", "Дата", "Посещаемость"])

df_pivot = df.pivot_table(
    index=["ФИО"],
    columns="Дата",
    values="Посещаемость",
    aggfunc="first",
    fill_value="Отсутствие",
)

wb = Workbook()
ws = wb.active

# desing for all cells
data_font = Font(name="Roboto", size=10)
data_alignment = Alignment(horizontal="center", vertical="center")

for r_idx, r in enumerate(dataframe_to_rows(df_pivot, index=True, header=True), 1):
    for c_idx, value in enumerate(r, 1):
        cell = ws.cell(row=r_idx, column=c_idx, value=value)
        cell.font = data_font
        cell.alignment = data_alignment

# design for header cells
header_font = Font(name="Roboto", size=12, bold=True)
for cell in ws[1]:
    cell.font = header_font

wb.save("Посещаемость.xlsx")
