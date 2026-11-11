from __future__ import annotations

import base64
import io
import json
import re

from PIL import Image

from .. import experiential_client


def ocr_image_to_text(image_bytes: bytes, sheet_type: str = "attendance") -> str:
    try:
        import pytesseract

        img = Image.open(io.BytesIO(image_bytes))
        text = pytesseract.image_to_string(img)
        if len(text.strip()) > 20:
            return text
    except Exception as exc:  # pragma: no cover - OCR fallback is best effort
        print("tesseract failed", exc)

    key = experiential_client.api_key()
    if key:
        try:
            b64 = base64.b64encode(image_bytes).decode()
            prompt = {
                "attendance": (
                    'OCR this attendance sheet. Return ONLY JSON array: '
                    '[{"name": "Ahmad Raza", "reg_id": "", "status": "PRESENT" or "ABSENT"}]. '
                    "Map tick/P/A to status."
                ),
                "marks": (
                    'OCR this marks sheet. Return ONLY JSON array: '
                    '[{"name": "Ahmad Raza", "reg_id": "CS-001", "obtained_marks": 8.5}]. '
                    "Extract name and marks number only."
                ),
            }[sheet_type]
            return experiential_client.vision(prompt, b64, max_tokens=2048)
        except Exception as exc:  # pragma: no cover - vision fallback is best effort
            print("experiential vision failed", exc)
    return ""


def _extract_json_array(ocr_text: str):
    start = ocr_text.find("[")
    end = ocr_text.rfind("]")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        return json.loads(ocr_text[start : end + 1])
    except Exception:
        return None


def parse_ocr_to_attendance(ocr_text: str):
    arr = _extract_json_array(ocr_text)
    if arr is not None:
        try:
            absent = [x["name"] for x in arr if x.get("status", "").upper().startswith("A")]
            return absent, ocr_text
        except Exception:
            pass

    absent = []
    for line in ocr_text.splitlines():
        if re.search(r"\bA\b|absent|X", line, re.I) and len(line.strip()) > 3:
            name = re.split(r"\s{2,}|,|\bA\b|\bP\b", line)[0].strip()
            if name and len(name) > 2:
                absent.append(name)
    return absent, ocr_text


def parse_ocr_to_marks(ocr_text: str):
    arr = _extract_json_array(ocr_text)
    if arr is not None:
        try:
            return arr
        except Exception:
            pass

    rows = []
    for line in ocr_text.splitlines():
        match = re.search(r"([A-Za-z ]{3,})\s+(\d+(?:\.\d+)?)", line)
        if match:
            rows.append({"name": match.group(1).strip(), "obtained_marks": float(match.group(2))})
    return rows
