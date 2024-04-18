import re


def password_check(password: str) -> bool:
    """
    Checks if a password meets the system's complexity requirements.

    This function validates a password string based on the following criteria:

    - Minimum length of 8 characters
    - Contains at least one uppercase letter (A-Z)
    - Contains at least one lowercase letter (a-z)
    - Contains at least one digit (0-9)
    - Contains at least one special character from the following set: #?!@$%^&*-

    Args:
        password (str): The password string to be validated.

    Returns:
        bool: True if the password meets all complexity requirements, False otherwise.
    """
    return bool(
        re.match(
            r"^(?=.*?[A-Z])(?=.*?[a-z])(?=.*?[0-9])(?=.*?[#?!@$%^&*-]).{8,}$", password
        )
    )
