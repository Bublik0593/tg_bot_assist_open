import html
from datetime import date, timedelta

WEEKDAYS_SHORT = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]
DONE, MISSED, OFF, PENDING = "✅", "❌", "➖", "⬜"


def parse_weekdays(s: str) -> set[int]:
    return {int(x) for x in s.split(",") if x != ""}


def cell(habit, day: date, today: date, logs: dict) -> str:
    """Символ для ячейки таблицы. habit — Row/dict с weekdays, created_date."""
    if day.isoformat() < habit["created_date"] or day.weekday() not in parse_weekdays(habit["weekdays"]):
        return OFF
    status = logs.get((habit["id"], day.isoformat()))
    if status == "done":
        return DONE
    if status == "skipped":
        return MISSED
    return PENDING if day >= today else MISSED  # прошедший день без отметки = пропуск


def streak(habit, today: date, logs: dict) -> int:
    """Серия подряд выполненных запланированных дней (сегодняшний день без отметки серию не рвёт)."""
    count = 0
    day = today
    for _ in range(366):
        if day.isoformat() < habit["created_date"]:
            break
        c = cell(habit, day, today, logs)
        if c == DONE:
            count += 1
        elif c == MISSED or (c == PENDING and day != today):
            break
        day -= timedelta(days=1)
    return count


def build_table(habits, logs: dict, today: date, days: int = 7) -> str:
    """HTML-текст с таблицей в <pre> и сводкой по каждой привычке."""
    if not habits:
        return "Привычек пока нет."
    dates = [today - timedelta(days=i) for i in range(days - 1, -1, -1)]
    name_w = 10
    header = " " * name_w + " " + " ".join(WEEKDAYS_SHORT[d.weekday()] for d in dates)
    nums = " " * name_w + " " + " ".join(f"{d.day:>2}" for d in dates)
    lines = [header, nums]
    summary = []
    for h in habits:
        name = h["name"] if len(h["name"]) <= name_w else h["name"][: name_w - 1] + "…"
        cells = [cell(h, d, today, logs) for d in dates]
        lines.append(f"{name:<{name_w}} " + " ".join(cells))
        scheduled = [c for c in cells if c != OFF and c != PENDING]
        pct = round(100 * cells.count(DONE) / len(scheduled)) if scheduled else 0
        summary.append(f"• {html.escape(h['name'])}: серия {streak(h, today, logs)}, выполнено {pct}%")
    table = html.escape("\n".join(lines))
    legend = f"{DONE} выполнено  {MISSED} пропущено  {PENDING} ждёт  {OFF} не по расписанию"
    return f"<pre>{table}</pre>\n{legend}\n\n" + "\n".join(summary)
