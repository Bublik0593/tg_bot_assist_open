"""Извлечение текста из загруженных книг: .txt, .docx, .pdf."""
import io
import re
import zipfile

from .pagination import decode_text

SUPPORTED = (".txt", ".docx", ".pdf")
MAX_CHARS = 5_000_000  # защита от «раздутых» файлов


class ExtractError(Exception):
    """Файл нельзя прочитать; message безопасно показывать пользователю."""


def _docx_text(data: bytes) -> str:
    from docx import Document
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    try:
        doc = Document(io.BytesIO(data))
    except (zipfile.BadZipFile, KeyError, ValueError) as e:
        raise ExtractError("Не удалось открыть .docx — файл повреждён или это старый формат .doc.") from e
    parts: list[str] = []
    # обход тела документа по порядку: абзацы и таблицы вперемешку
    for el in doc.element.body.iterchildren():
        if el.tag.endswith("}p"):
            parts.append(Paragraph(el, doc).text)
        elif el.tag.endswith("}tbl"):
            for row in Table(el, doc).rows:
                cells = [c.text.strip() for c in row.cells]
                parts.append(" | ".join(c for c in cells if c))
        if sum(map(len, parts)) > MAX_CHARS:
            raise ExtractError("Слишком много текста в файле.")
    return "\n\n".join(parts)


def _reflow_pdf(page: str) -> str:
    """В PDF строки переносятся по ширине листа: склеиваем строки внутри абзаца."""
    page = re.sub(r"(\w)-\n(\w)", r"\1\2", page)  # перенос слова
    return re.sub(r"(?<![.!?…:;»\"\n])\n(?!\n)", " ", page)


def garbled_ratio(text: str) -> float:
    """Доля «мусорных» символов: Latin-1 Supplement, U+FFFD, private use, (cid:N)."""
    text = re.sub(r"\(cid:\d+\)", "\ufffd", text)
    letters = bad = 0
    for ch in text:
        o = ord(ch)
        if 0x80 <= o <= 0xFF or o == 0xFFFD or 0xE000 <= o <= 0xF8FF:
            bad += 1
        elif ch.isalpha():
            letters += 1
    total = letters + bad
    return bad / total if total else 0.0


def _is_garbled(text: str) -> bool:
    return garbled_ratio(text) > 0.3


def _cyr(text: str) -> int:
    return sum("\u0400" <= ch <= "\u04ff" for ch in text)


def fix_mojibake(text: str) -> str | None:
    """Кириллица CP1251, прочитанная как Latin-1/CP1252 («Ïðèâåò»). None, если починить не вышло."""
    for enc in ("latin-1", "cp1252"):
        try:
            fixed = text.encode(enc).decode("cp1251")
        except (UnicodeEncodeError, UnicodeDecodeError):
            continue
        if _cyr(fixed) > len(fixed) * 0.3 and not _is_garbled(fixed):
            return fixed
    return None


def _pypdf_pages(data: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    if reader.is_encrypted and not reader.decrypt(""):
        raise ExtractError("PDF защищён паролем.")
    parts: list[str] = []
    total = 0
    for page in reader.pages:
        t = page.extract_text() or ""
        total += len(t)
        if total > MAX_CHARS:
            raise ExtractError("Слишком много текста в файле.")
        parts.append(t)
    return "\n\n".join(parts)


def _pdfminer_pages(data: bytes) -> str:
    from pdfminer.high_level import extract_text as pm_extract

    return pm_extract(io.BytesIO(data))[:MAX_CHARS]


def _pdf_text(data: bytes) -> str:
    from pypdf.errors import PdfReadError

    try:
        text = _pypdf_pages(data)
    except ExtractError:
        raise
    except (PdfReadError, ValueError, KeyError, OSError, RecursionError) as e:
        text = ""
        pypdf_error = e
    else:
        pypdf_error = None

    if text.strip() and _is_garbled(text):
        # 1) типичная «кракозябра» CP1251 -> 2) другой разборщик (pdfminer читает больше кодировок шрифтов)
        text = fix_mojibake(text) or _try_pdfminer(data) or text
        if _is_garbled(text):
            raise ExtractError(
                "Не удалось корректно извлечь текст из PDF: в файле нестандартная кодировка шрифтов. "
                "Откройте его в читалке и сохраните/экспортируйте как .txt или .docx, либо пришлите другой экземпляр."
            )
    elif not text.strip():
        text = _try_pdfminer(data) or ""
        if not text.strip():
            if pypdf_error:
                raise ExtractError("Не удалось прочитать PDF — файл повреждён.") from pypdf_error
            raise ExtractError("В PDF нет текстового слоя (похоже, это скан). Нужен PDF с выделяемым текстом.")
    return _reflow_pdf(text)


def _try_pdfminer(data: bytes) -> str | None:
    try:
        text = _pdfminer_pages(data)
    except Exception:  # pdfminer кидает много разных исключений на битых файлах
        return None
    if not text.strip():
        return None
    if _is_garbled(text):
        return fix_mojibake(text)
    return text


def extract_text(name: str, data: bytes) -> str:
    ext = name.lower().rsplit(".", 1)[-1] if "." in name else ""
    if ext == "txt":
        return decode_text(data)
    if ext == "docx":
        return _docx_text(data)
    if ext == "pdf":
        return _pdf_text(data)
    raise ExtractError("Поддерживаются форматы .txt, .docx и .pdf")
