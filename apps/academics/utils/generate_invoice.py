import secrets

from django.utils import timezone


def generate_secure_invoice_number():
    """
    Example: INV-20260502-9F3A7C2B
    """
    date_part = timezone.now().strftime("%y%m%d")  # 6 chars
    random_part = secrets.token_hex(4).upper()  # 8 chars

    return f"INV-{date_part}-{random_part}"
