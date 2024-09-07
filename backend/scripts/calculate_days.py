from datetime import datetime

def parse_date(date_str: str) -> datetime:
    """
    Parses a date string and returns a datetime object. The function handles
    multiple date formats and normalizes them to a standard format.

    Args:
        date_str (str): A string representing a date in any of the supported formats.

    Returns:
        datetime: A datetime object parsed from the input string.

    Raises:
        ValueError: If the provided date string is not in a recognized format.
    """
    date_formats = ["%Y-%m-%d", "%m/%d/%Y", "%d.%m.%Y"]
    
    parsed_date = next(
        (datetime.strptime(date_str, fmt) for fmt in date_formats if _valid_date_format(date_str, fmt)),
        None
    )
    
    if parsed_date is None:
        raise ValueError("Неверный формат даты. Используйте один из следующих форматов: YYYY-MM-DD, MM/DD/YYYY, DD.MM.YYYY.")
    
    return parsed_date

def _valid_date_format(date_str: str, fmt: str) -> bool:
    """
    Helper function to check if a date string matches a given format.

    Args:
        date_str (str): The date string to check.
        fmt (str): The format to check against.

    Returns:
        bool: True if the date string matches the format, False otherwise.
    """
    try:
        datetime.strptime(date_str, fmt)
        return True
    except ValueError:
        return False

def calculate_date_range(start_date_str: str = "", end_date_str: str = "") -> int:
    """
    Calculates the number of days between two dates.
    If the start date is not provided, the current date is used as the start date.
    If the end date is not provided, the current date is used as the end date.

    Args:
        start_date_str (str): A string representing the start date. If not provided,
                              the current date is used.
        end_date_str (str): A string representing the end date. If not provided,
                            the current date is used.

    Returns:
        int: The number of days between the start date and the end date.

    Raises:
        ValueError: If either date string is not in a recognized format.
    """
    today = datetime.today()
    start_date = parse_date(start_date_str) if start_date_str else today
    end_date = parse_date(end_date_str) if end_date_str else today
    
    delta = end_date - start_date
    return abs(delta.days)

start_date_input = input("Введите дату начала (YYYY-MM-DD, MM/DD/YYYY, или DD.MM.YYYY, нажмите Enter для текущей даты): ")
end_date_input = input("Введите дату конца (YYYY-MM-DD, MM/DD/YYYY, или DD.MM.YYYY, нажмите Enter для текущей даты): ")

try:
    days = calculate_date_range(start_date_input, end_date_input)
    print(f"Количество дней = {days}")
except ValueError as e:
    print(e)