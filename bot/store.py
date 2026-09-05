#!/usr/bin/env python3
"""
Память бота. Для прототипа — один JSON-файл под замком процесса.

Хранится ровно то, без чего нельзя писать первым и держать одну живую
карточку: чат пользователя, id последнего сообщения-кабинета и отметки
об уже отправленных напоминаниях.

В бою это место занимает та же таблица, что и в вашем бэкенде
(VpnUser + журнал уведомлений). Здесь важен не способ хранения,
а правило: у каждого напоминания есть ключ, и дважды одно и то же
мы не шлём.
"""

import json
import os
import threading

STATE_FILE = os.path.expanduser('~/.config/hanvpn/state.json')
_lock = threading.Lock()


def _read():
    try:
        return json.load(open(STATE_FILE, encoding='utf-8'))
    except Exception:
        return {'users': {}}


def _write(data):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    tmp = STATE_FILE + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, STATE_FILE)      # чтобы не оставить обрезанный файл


def get(telegram_id):
    return _read()['users'].get(str(telegram_id), {})


def all_users():
    return _read()['users']


def update(telegram_id, **fields):
    with _lock:
        data = _read()
        u = data['users'].setdefault(str(telegram_id), {})
        u.update(fields)
        _write(data)
        return u


def mark_notified(telegram_id, key, stamp):
    """
    Отметка «это напоминание уже отправлено». stamp привязан к поводу
    (например, к дате окончания подписки), поэтому на новом периоде
    напоминание отправится снова, а внутри одного — только раз.
    """
    with _lock:
        data = _read()
        u = data['users'].setdefault(str(telegram_id), {})
        u.setdefault('notified', {})[key] = stamp
        _write(data)


def was_notified(telegram_id, key, stamp):
    return get(telegram_id).get('notified', {}).get(key) == stamp
