# whatsapp.py
import webbrowser
from urllib.parse import quote
import phonenumbers

def format_e164(phone_raw: str):
    if not phone_raw:
        return None
    try:
        num = phonenumbers.parse(phone_raw, "IN")
        if phonenumbers.is_possible_number(num) and phonenumbers.is_valid_number(num):
            return phonenumbers.format_number(num, phonenumbers.PhoneNumberFormat.E164).replace("+", "")
    except Exception:
        return None
    return None

def open_whatsapp_chat(phone: str, text: str):
    phone_digits = format_e164(phone)
    url = f"https://wa.me/{phone_digits}?text={quote(text)}" if phone_digits else f"https://wa.me/?text={quote(text)}"
    webbrowser.open(url)
