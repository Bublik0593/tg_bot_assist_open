import random
import re

from bot.services.pagination import decode_text, paginate


def squash(s: str) -> str:
    return re.sub(r"\s+", "", s)


def make_text(seed=1, words=4000):
    rnd = random.Random(seed)
    alphabet = "абвгдеёжзийклмнопрстуфхцчшщъыьэюя"
    out = []
    for i in range(words):
        out.append("".join(rnd.choice(alphabet) for _ in range(rnd.randint(1, 14))))
        out.append(rnd.choice([" "] * 12 + ["\n", "\n\n", ", "]))
    return "".join(out)


def test_pages_within_limit_and_lossless():
    text = make_text()
    pages = paginate(text, 1500)
    assert pages and all(0 < len(p) <= 1500 for p in pages)
    assert squash("".join(pages)) == squash(text)


def test_no_word_is_split():
    text = make_text(seed=7)
    pages = paginate(text, 1500)
    words = re.findall(r"\S+", text)
    got = [w for p in pages for w in re.findall(r"\S+", p)]
    assert got == words  # слова целы и в исходном порядке


def test_many_sizes_and_seeds():
    for seed in range(5):
        for size in (50, 333, 1500):
            text = make_text(seed, 800)
            pages = paginate(text, size)
            assert all(len(p) <= size for p in pages)
            assert re.findall(r"\S+", text) == [w for p in pages for w in re.findall(r"\S+", p)]


def test_boundary_exact_fit():
    text = ("a" * 9 + " ") * 3 + "b" * 9  # 39 символов
    assert paginate(text, 10) == ["a" * 9, "a" * 9, "a" * 9, "b" * 9]


def test_prefers_paragraph_break():
    text = ("слово " * 150).strip() + "\n\n" + "второй абзац " * 100
    pages = paginate(text, 1500)
    assert pages[0].endswith("слово") and pages[1].startswith("второй")


def test_giant_word_hard_split():
    pages = paginate("x" * 3200, 1500)
    assert [len(p) for p in pages] == [1500, 1500, 200]


def test_empty_and_whitespace():
    assert paginate("") == []
    assert paginate(" \n\n \r\n ") == []


def test_short_text_single_page():
    assert paginate("Привет, мир") == ["Привет, мир"]


def test_decode_cp1251_and_utf8():
    s = "Привет, это тестовая книга. " * 20
    assert decode_text(s.encode("cp1251")) == s
    assert decode_text(s.encode("utf-8")) == s
    assert decode_text(b"\xef\xbb\xbf" + s.encode("utf-8")) == s
