#!/usr/bin/env python3
"""
Тонкий клиент Remnawave для прототипа бота. Без зависимостей.

Логика повторяет hanvpn_core/remnawave.py и trials.py из вашего бэкенда,
чтобы прототип не разошёлся с продакшеном:

  · имя пользователя в панели — «<префикс><telegram_id>». Telegram ID
    общий для всех ботов, префикс изолирует наш от чужих;
  · перед созданием ищем по имени, а 409 при создании считаем успехом —
    двойной клик не создаёт вторую учётку;
  · триал по умолчанию 3 дня, лимит 1 устройство (как TRIAL_DAYS
    и TRIAL_DEVICE_LIMIT в .env).

Доступы читаются из ~/.config/hanvpn/remnawave.json:

    {
      "base_url": "https://panel.example.com",
      "token": "...",
      "user_prefix": "han_",
      "internal_squads": [],
      "trial_days": 3,
      "trial_device_limit": 1
    }
"""

import json
import os
import stat
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

CONFIG_FILE = os.path.expanduser('~/.config/hanvpn/remnawave.json')


class NotConfigured(RuntimeError):
    pass


class RemnawaveError(RuntimeError):
    pass


def load_config(path=CONFIG_FILE):
    if not os.path.exists(path):
        raise NotConfigured('нет файла %s' % path)
    if stat.S_IMODE(os.stat(path).st_mode) & 0o077:
        raise NotConfigured('файл с токеном открыт другим пользователям: chmod 600 %s' % path)

    cfg = json.load(open(path, encoding='utf-8'))
    for key in ('base_url', 'token'):
        if not cfg.get(key):
            raise NotConfigured('в %s не задан %s' % (path, key))

    cfg.setdefault('user_prefix', 'han_')
    cfg.setdefault('internal_squads', [])
    cfg.setdefault('trial_days', 3)
    cfg.setdefault('trial_device_limit', 1)
    cfg['base_url'] = cfg['base_url'].rstrip('/')
    return cfg


def _request(cfg, method, path, body=None):
    req = urllib.request.Request(
        cfg['base_url'] + path,
        data=json.dumps(body).encode('utf-8') if body is not None else None,
        method=method,
        headers={
            'Authorization': 'Bearer %s' % cfg['token'],
            'Content-Type': 'application/json',
            'Accept': 'application/json',
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=25) as res:
            return res.status, json.load(res)
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw)
        except ValueError:
            return e.code, {}
    except urllib.error.URLError as e:
        raise RemnawaveError('панель недоступна: %s' % e.reason)


def parse_user(payload):
    """Плоский вид пользователя. Имена полей — как в API Remnawave."""
    data = payload.get('response', payload)
    if isinstance(data.get('user'), dict):
        data = data['user']

    def dt(value):
        if not value:
            return None
        try:
            return datetime.fromisoformat(value.replace('Z', '+00:00'))
        except ValueError:
            return None

    return {
        'uuid': data.get('uuid'),
        'username': data.get('username'),
        'status': data.get('status'),
        'subscription_url': data.get('subscriptionUrl'),
        'expire_at': dt(data.get('expireAt')),
        'device_limit': data.get('hwidDeviceLimit'),
        # на этих двух держится мастер подключения в мини-аппе
        'sub_last_opened_at': dt(data.get('subLastOpenedAt')),
        'sub_last_user_agent': data.get('subLastUserAgent'),
        'online_at': dt(data.get('onlineAt')),
    }


def username_for(cfg, telegram_id):
    return '%s%s' % (cfg['user_prefix'], telegram_id)


def find_user(cfg, telegram_id):
    """Возвращает пользователя или None. 404 — это «нет», а не ошибка."""
    status, body = _request(cfg, 'GET', '/api/users/by-username/%s' % username_for(cfg, telegram_id))
    if status == 404:
        return None
    if status >= 400:
        raise RemnawaveError('поиск пользователя: HTTP %s' % status)
    return parse_user(body)


def create_trial(cfg, telegram_id, days=None, device_limit=None):
    """Создаёт триал. Повторный вызов не плодит учётки: 409 → берём готовую."""
    existing = find_user(cfg, telegram_id)
    if existing:
        return existing, False

    days = days or cfg['trial_days']
    expire_at = datetime.now(timezone.utc) + timedelta(days=days)
    body = {
        'username': username_for(cfg, telegram_id),
        'telegramId': telegram_id,
        'expireAt': expire_at.isoformat(),
        'description': 'Telegram trial: %s' % telegram_id,
        'status': 'ACTIVE',
        'hwidDeviceLimit': device_limit or cfg['trial_device_limit'],
    }
    if cfg['internal_squads']:
        body['activeInternalSquads'] = cfg['internal_squads']

    status, payload = _request(cfg, 'POST', '/api/users', body)
    if status == 409:                      # успели создать параллельно
        user = find_user(cfg, telegram_id)
        if user:
            return user, False
        raise RemnawaveError('конфликт при создании, но пользователь не найден')
    if status >= 400:
        raise RemnawaveError('создание пользователя: HTTP %s %s'
                             % (status, payload.get('message', '')))
    return parse_user(payload), True


def ping(cfg):
    """Проверка доступа: панель отвечает и токен принят."""
    status, _ = _request(cfg, 'GET', '/api/users?size=1&start=0')
    if status == 401 or status == 403:
        raise RemnawaveError('токен не принят (HTTP %s)' % status)
    if status >= 400:
        raise RemnawaveError('HTTP %s' % status)
    return True


if __name__ == '__main__':
    # Проверка доступа: python3 bot/remnawave.py
    try:
        cfg = load_config()
    except NotConfigured as e:
        raise SystemExit('Remnawave не настроен: %s' % e)
    print('панель: %s' % cfg['base_url'])
    print('префикс имён: %s' % cfg['user_prefix'])
    try:
        ping(cfg)
        print('доступ: ок')
    except RemnawaveError as e:
        raise SystemExit('доступ: %s' % e)
