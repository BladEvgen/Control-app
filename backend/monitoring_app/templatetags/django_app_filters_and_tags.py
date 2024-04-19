from django import template
from django.utils import timezone
from django.utils.timesince import timesince


register = template.Library()


@register.simple_tag
def digit_beautify(value) -> str:
    """
    Formats a number by adding spaces every 3 digits for better readability.

    Args:
        value: The number to be formatted.

    Returns:
        The formatted number with spaces separating every 3 digits.
    """
    src = str(value)
    if "." in src:
        out, rnd = src.split(".")
    else:
        out, rnd = src, "0"
    chunks = [out[max(i - 3, 0) : i] for i in range(len(out), 0, -3)][::-1]
    formatted_out = " ".join(chunks)

    return f"{formatted_out}.{rnd}"


@register.simple_tag
def relative_time(datetime_value) -> str:
    """
    Formats a datetime value to display relative time (e.g., "2 hours ago")
    or absolute time (e.g., "14:30 19.04.2024") depending on the difference
    between the datetime value and current time.

    Args:
        datetime_value: The datetime object to be formatted.

    Returns:
        A string representing the relative or absolute time.
    """
    delta = timezone.now() - datetime_value

    if delta.days == 0 and delta.seconds < 86400:
        return timesince(datetime_value, timezone.now())
    else:
        return datetime_value.strftime("%H:%M %d.%m.%Y")


@register.filter(name="custom_cut")
def cutstom_cut(text: any, length: int) -> str:
    """
    Truncates a string to a specified length and adds an ellipsis (...)
    if the string is longer than the provided length.

    Args:
        text: The string to be truncated.
        length: The maximum length of the returned string.

    Returns:
        The truncated string with an ellipsis if it was longer than the
        specified length, otherwise the original string.
    """
    if len(str(text)) > length:
        return str(text)[:length] + "..."
    return str(text)
