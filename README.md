# Бот: привычки, цели, книги (Telegram)

Python 3.11+, aiogram 3, SQLite (WAL), APScheduler.

## Запуск
```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
cp .env.example .env      # впишите BOT_TOKEN от @BotFather
.venv/bin/python main.py
.venv/bin/python -m pytest
```

## Возможности
- **Привычки:** дни недели + время, напоминание с кнопками «Выполнил / Пропустить», таблица за 7/14 дней, серия и процент. Прошедший день без отметки считается пропуском.
- **Цели:** добавить, переименовать, отметить выполненной, фильтр «Активные / Выполненные / Все».
- **Книги:** отправьте `.txt` (UTF-8/CP1251 и др.), `.docx` или `.pdf` с текстовым слоем (сканы без OCR не читаются); страницы по 1500 символов без разрыва слов; прогресс сохраняется при каждом листании.
- **Настройки:** часовой пояс (по умолчанию Europe/Moscow).
- Данные каждого пользователя изолированы (`user_id` во всех запросах).

## Docker (рекомендуется для VPS)
```bash
cp .env.example .env          # впишите BOT_TOKEN
mkdir -p data && sudo chown 10001 data   # база хранится в ./data (volume)
docker compose up -d --build
docker compose logs -f bot
```
- Обновление: `git pull && docker compose up -d --build`
- Бэкап: `docker compose run --rm backup` (14 копий в `data/backups`); для ежедневного запуска добавьте в cron
  `0 4 * * * cd /path/to/bot_habits && docker compose run --rm backup`
- Данные лежат в `./data`, при пересборке образа не теряются.

## VPS без Docker (systemd)
1. Скопировать проект в `/opt/bot_habits`, создать venv, `.env` (права `600`), пользователя `botuser`.
2. `sudo cp deploy/habits-bot.service /etc/systemd/system/ && sudo systemctl enable --now habits-bot`
3. Логи: `journalctl -u habits-bot -f`
4. Бэкап (нужен пакет `sqlite3`): cron `0 4 * * * /opt/bot_habits/deploy/backup.sh`
