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


def _pdf_text(data: bytes) -> str:
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted and not reader.decrypt(""):
            raise ExtractError("PDF защищён паролем.")
        parts: list[str] = []
        total = 0
        for page in reader.pages:
            t = _reflow_pdf(page.extract_text() or "")
            total += len(t)
            if total > MAX_CHARS:
                raise ExtractError("Слишком много текста в файле.")
            parts.append(t)
    except ExtractError:
        raise
    except (PdfReadError, ValueError, KeyError, OSError, RecursionError) as e:
        raise ExtractError("Не удалось прочитать PDF — файл повреждён.") from e
    text = "\n\n".join(parts)
    if not text.strip():
        raise ExtractError("В PDF нет текстового слоя (похоже, это скан). Нужен PDF с выделяемым текстом.")
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
