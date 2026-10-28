import re

import chardet


def decode_text(data: bytes) -> str:
    """Декодирует .txt: UTF-8 (с BOM или без) -> автоопределение -> CP1251."""
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        pass
    guess = chardet.detect(data[:200_000])
    enc = guess.get("encoding")
    if enc and (guess.get("confidence") or 0) >= 0.6:
        try:
            return data.decode(enc)
        except (UnicodeDecodeError, LookupError):
            pass
    return data.decode("cp1251", errors="replace")


def normalize(text: str) -> str:
    text = text.replace("\x00", "").replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def paginate(text: str, size: int = 1500) -> list[str]:
    """Делит текст на страницы длиной <= size символов, не разрывая слова.

    Граница выбирается по возможности на конце абзаца, затем на конце строки,
    затем на пробеле. Слово длиннее size (без пробелов) режется жёстко.
    """
    text = normalize(text)
    n = len(text)
    pages: list[str] = []
    pos = 0
    min_cut = size * 6 // 10  # не делаем страницу короче 60%, если есть альтернатива
    while pos < n:
        if n - pos <= size:
            end = n
        elif text[pos + size].isspace():
            end = pos + size  # граница уже между словами
        else:
            window_end = pos + size
            end = -1
            for sep in ("\n\n", "\n"):
                i = text.rfind(sep, pos, window_end)
                if i - pos >= min_cut:
                    end = i
                    break
            if end == -1:
                i = window_end - 1
                while i > pos and not text[i].isspace():
                    i -= 1
                end = i if i > pos else window_end  # нет пробелов: жёсткий разрез
        page = text[pos:end].strip()
        if page:
            pages.append(page)
        pos = end
        while pos < n and text[pos].isspace():
            pos += 1
    return pages
