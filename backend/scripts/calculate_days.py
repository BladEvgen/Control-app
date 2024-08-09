from datetime import datetime

def days_since_date(input_date: str) -> int:
    """
    Calculates the number of days that have passed since the given date.

    This function takes a date string in the format 'YYYY-MM-DD' and calculates
    the number of days from that date to the current date. It returns the number
    of days as an integer. If the input date is in an incorrect format, an error
    message is returned instead.

    Args:
        input_date (str): A string representing a date in the format 'YYYY-MM-DD'.

    Returns:
        int: The number of days since the input date.
        
    Raises:
        ValueError: If the provided date string is not in the correct 'YYYY-MM-DD' format.
    """
    date_format = "%Y-%m-%d"
    try:
        past_date = datetime.strptime(input_date, date_format)
        today = datetime.today()
        delta = today - past_date
        return delta.days
    except ValueError:
        return "Неверный формат даты. Используйте формат ГГГГ-ММ-ДД."

input_date = input("Введите дату (ГГГГ-ММ-ДД): ")
days = days_since_date(input_date)
print(f"DAYS = {days}")
