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
    def body_of(raw, code):
        # Панель на неизвестный путь отдаёт HTML своей веб-морды —
        # разбирать его как JSON нельзя, иначе клиент падает на ровном месте.
        try:
            return code, json.loads(raw)
        except ValueError:
            return code, {}
    try:
        with urllib.request.urlopen(req, timeout=25) as res:
            return body_of(res.read(), res.status)
    except urllib.error.HTTPError as e:
        return body_of(e.read(), e.code)
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

    # Версии панели расходятся: в одних пользователь адресуется uuid
    # и отдаёт subLastOpenedAt, в других — числовым id, а признаки
    # подключения лежат внутри userTraffic. Поддерживаем обе.
    tr = data.get('userTraffic') or {}
    return {
        'id': data.get('id'),
        'uuid': data.get('uuid'),
        'ref': data.get('id') if data.get('id') is not None else data.get('uuid'),
        'short_uuid': data.get('shortUuid'),
        'username': data.get('username'),
        'status': data.get('status'),
        'subscription_url': data.get('subscriptionUrl'),
        'expire_at': dt(data.get('expireAt')),
        'device_limit': data.get('hwidDeviceLimit'),
        # «подписку забрали» — есть не везде
        'sub_last_opened_at': dt(data.get('subLastOpenedAt')),
        'sub_last_user_agent': data.get('subLastUserAgent'),
        # «человек подключился» — надёжнее, потому что означает живой VPN
        'online_at': dt(data.get('onlineAt') or tr.get('onlineAt')),
        'first_connected_at': dt(tr.get('firstConnectedAt')),
        'used_traffic': tr.get('usedTrafficBytes') or 0,
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


def devices(cfg, user):
    """Сколько устройств зарегистрировано за пользователем."""
    if user.get('id') is None:
        return 0
    status, body = _request(cfg, 'GET', '/api/hwid/devices/%s' % user['id'])
    if status >= 400:
        return 0
    return ((body.get('response') or body) or {}).get('total') or 0


def is_connected(cfg, user):
    """
    Подключился ли человек на самом деле. В разных версиях панели
    признак разный, поэтому смотрим все и берём любой сработавший:

      · subLastOpenedAt — приложение забрало конфиг по ссылке подписки;
      · firstConnectedAt / onlineAt — было живое соединение;
      · зарегистрированное устройство или израсходованный трафик.
    """
    if user.get('sub_last_opened_at') or user.get('first_connected_at') \
            or user.get('online_at') or (user.get('used_traffic') or 0) > 0:
        return True
    return devices(cfg, user) > 0


def set_expiry(cfg, user, until):
    """Продление. Пользователь адресуется тем, что отдала панель."""
    body = {'expireAt': until.isoformat()}
    body['id' if user.get('id') is not None else 'uuid'] = user['ref']
    status, payload = _request(cfg, 'PATCH', '/api/users', body)
    if status >= 400:
        raise RemnawaveError('продление: HTTP %s %s' % (status, payload.get('message', '')))
    return parse_user(payload)


def delete_user(cfg, user):
    status, _ = _request(cfg, 'DELETE', '/api/users/%s' % user['ref'])
    if status >= 400:
        raise RemnawaveError('удаление: HTTP %s' % status)
    return True


def ping(cfg):
    """Проверка доступа: панель отвечает и токен принят."""
    status, _ = _request(cfg, 'GET', '/api/users?size=1&start=0')
    if status == 401 or status == 403:
        raise RemnawaveError('токен не принят (HTTP %s)' % status)
    if status >= 400:
        raise RemnawaveError('HTTP %s' % status)
    return True


def selfcheck(cfg):
    """
    Полная проверка связки: панель отвечает, токен принят, поля называются
    так, как ждёт мини-аппа. Ничего не создаёт и не меняет.
    """
    print('панель:       %s' % cfg['base_url'])
    print('префикс имён: %s' % cfg['user_prefix'])
    status, body = _request(cfg, 'GET', '/api/users?size=1&start=0')
    if status in (401, 403):
        raise RemnawaveError('токен не принят (HTTP %s). Проверьте, что это токен '
                             'с ролью API и он не отозван.' % status)
    if status >= 400:
        raise RemnawaveError('панель ответила HTTP %s' % status)
    print('доступ:       токен принят')

    resp = body.get('response', body)
    users = resp.get('users') if isinstance(resp, dict) else None
    total = resp.get('total') if isinstance(resp, dict) else None
    if total is not None:
        print('пользователей в панели: %s' % total)

    # Мастер подключения в мини-аппе держится на двух полях. Если панель
    # их не отдаёт, «Подключено» никогда не наступит — лучше узнать сразу.
    if users:
        have = set(users[0].keys())
        tr = set((users[0].get('userTraffic') or {}).keys())
        need = [f for f in ('subscriptionUrl', 'expireAt', 'hwidDeviceLimit') if f not in have]
        print('поля пользователя: %s' % ('основные на месте' if not need
                                         else 'НЕ ХВАТАЕТ ' + ', '.join(need)))
        signal = [n for n in ('subLastOpenedAt',) if n in have] + \
                 [n for n in ('firstConnectedAt', 'onlineAt') if n in tr]
        print('признак подключения: %s' % (', '.join(signal) if signal
                                           else 'только регистрация устройств (hwid)'))
    else:
        print('поля пользователя: в панели пока нет ни одного — проверим после '
              'первой выдачи триала')

    status, body = _request(cfg, 'GET', '/api/internal-squads')
    if status < 400:
        squads = (body.get('response') or body).get('internalSquads') or []
        if squads:
            print('внутренние отряды (для internal_squads в конфиге):')
            for sq in squads:
                print('   %s  %s' % (sq.get('uuid'), sq.get('name')))
        else:
            print('внутренние отряды: ни одного — пользователю не к чему '
                  'подключиться, создайте отряд в панели')
    return True


if __name__ == '__main__':
    # Проверка доступа: python3 bot/remnawave.py
    try:
        cfg = load_config()
    except NotConfigured as e:
        raise SystemExit('Remnawave не настроен: %s' % e)
    try:
        selfcheck(cfg)
    except RemnawaveError as e:
        raise SystemExit('ошибка: %s' % e)
