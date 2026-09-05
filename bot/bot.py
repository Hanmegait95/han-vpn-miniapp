#!/usr/bin/env python3
"""
Прототип бота Han VPN. Long polling, без зависимостей и без вебхуков —
запускается на любой машине одной командой.

    python3 -u bot/bot.py

Токен читается из ~/.config/hanvpn/bot_token (см. bot-setup.py).
Содержимое экранов — в screens.py, здесь только механика.
"""

import json
import mimetypes
import os
import stat
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import remnawave as rw
import screens as S
import store

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(HERE, '..', 'assets')
TOKEN_FILE = os.path.expanduser('~/.config/hanvpn/bot_token')
CACHE_FILE = os.path.expanduser('~/.config/hanvpn/file_ids.json')

BOT_USERNAME = None      # заполняется на старте, нужен для реферальной ссылки


# ── Bot API ────────────────────────────────────────────────────────

def read_token(path=TOKEN_FILE):
    if not os.path.exists(path):
        sys.exit('нет файла с токеном: %s' % path)
    if stat.S_IMODE(os.stat(path).st_mode) & 0o077:
        sys.exit('файл с токеном открыт другим пользователям: chmod 600 %s' % path)
    token = open(path, encoding='utf-8').read().strip()
    if ':' not in token:
        sys.exit('в файле не похоже на токен бота')
    return token


def call(token, method, payload=None, timeout=40, quiet=False):
    url = 'https://api.telegram.org/bot%s/%s' % (token, method)
    data = json.dumps(payload).encode('utf-8') if payload is not None else None
    headers = {'Content-Type': 'application/json'} if data else {}
    req = urllib.request.Request(url, data=data, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            body = json.load(res)
    except urllib.error.HTTPError as e:
        body = json.load(e)
    except (urllib.error.URLError, TimeoutError):
        return None
    if not body.get('ok'):
        if not quiet:
            print('  ! %s: %s' % (method, body.get('description')))
        return None
    return body['result']


def upload(token, method, fields, file_field, file_path):
    """multipart/form-data вручную — чтобы обойтись без зависимостей."""
    boundary = '----hanvpn%d' % int(time.time() * 1000)
    body = b''
    for k, v in fields.items():
        body += ('--%s\r\nContent-Disposition: form-data; name="%s"\r\n\r\n%s\r\n'
                 % (boundary, k, v)).encode('utf-8')
    ctype = mimetypes.guess_type(file_path)[0] or 'application/octet-stream'
    body += ('--%s\r\nContent-Disposition: form-data; name="%s"; filename="%s"\r\n'
             'Content-Type: %s\r\n\r\n'
             % (boundary, file_field, os.path.basename(file_path), ctype)).encode('utf-8')
    body += open(file_path, 'rb').read() + b'\r\n'
    body += ('--%s--\r\n' % boundary).encode('utf-8')

    req = urllib.request.Request(
        'https://api.telegram.org/bot%s/%s' % (token, method), data=body,
        headers={'Content-Type': 'multipart/form-data; boundary=%s' % boundary})
    try:
        with urllib.request.urlopen(req, timeout=90) as res:
            out = json.load(res)
    except urllib.error.HTTPError as e:
        out = json.load(e)
    except (urllib.error.URLError, TimeoutError) as e:
        print('  ! загрузка не удалась: %r' % e)
        return None
    if not out.get('ok'):
        print('  ! %s: %s' % (method, out.get('description')))
        return None
    return out['result']


# ── Баннеры ────────────────────────────────────────────────────────
# Серверы Telegram не достают до российского хостинга, поэтому картинки
# грузим файлом. После первой загрузки живём на file_id.

def _cache():
    try:
        return json.load(open(CACHE_FILE, encoding='utf-8'))
    except Exception:
        return {}


def _remember(name, file_id):
    data = _cache()
    data[name] = file_id
    try:
        os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
        json.dump(data, open(CACHE_FILE, 'w', encoding='utf-8'))
    except Exception:
        pass


def banner_path(name):
    return os.path.join(ASSETS, name)


def banner_id(token, chat_id, name):
    """file_id баннера. Первый раз заливаем черновиком и убираем его."""
    fid = _cache().get(name)
    if fid:
        return fid
    tmp = upload(token, 'sendPhoto', {'chat_id': str(chat_id), 'caption': '…'},
                 'photo', banner_path(name))
    if not (tmp and tmp.get('photo')):
        return None
    fid = tmp['photo'][-1]['file_id']
    _remember(name, fid)
    call(token, 'deleteMessage',
         {'chat_id': chat_id, 'message_id': tmp['message_id']}, quiet=True)
    return fid


# ── Профиль ────────────────────────────────────────────────────────

def load_profile(user):
    """
    Подписка — из Remnawave. Баланса там нет: это ваша база платежей.
    Если панель не настроена, кабинет всё равно открывается — просто
    без данных о подписке.
    """
    p = {
        'name': user.get('first_name') or user.get('username') or 'без имени',
        'telegram_id': user['id'],
        'balance': 0,
        'subscriptions': 0,
        'expire_at': None,
        'sub_last_opened_at': None,
        'online_at': None,
        'now': datetime.now(timezone.utc),
        'referral_link': 'https://t.me/%s?start=ref%s' % (BOT_USERNAME, user['id']),
    }
    try:
        cfg = rw.load_config()
    except rw.NotConfigured:
        return p
    try:
        found = rw.find_user(cfg, user['id'])
    except rw.RemnawaveError as e:
        print('  ! Remnawave: %s' % e)
        return p
    if found and found['status'] == 'ACTIVE':
        p['subscriptions'] = 1
        p['expire_at'] = found['expire_at']
        p['sub_last_opened_at'] = found['sub_last_opened_at']
        p['online_at'] = found['online_at']
    return p


# ── Отрисовка экрана ───────────────────────────────────────────────

def keyboard(screen, profile):
    rows = []
    for row in screen['buttons'](profile):
        out = []
        for b in row:
            btn = {'text': b['text']}
            if 'nav' in b:
                btn['callback_data'] = 'n:' + b['nav']
            elif 'act' in b:
                btn['callback_data'] = 'a:' + b['act']
            elif 'web_app' in b:
                btn['web_app'] = {'url': b['web_app']}
            elif 'url' in b:
                btn['url'] = b['url']
            out.append(btn)
        rows.append(out)
    if screen.get('back'):
        back = screen['back']
        if back == 'home':
            back = S.home(profile)
        rows.append([{'text': S.BACK, 'callback_data': 'n:' + back}])
    return {'inline_keyboard': rows}


def send_screen(token, chat_id, name, user, replace_card=False):
    """
    Отправка новым сообщением. replace_card убирает предыдущую карточку:
    иначе в чате копятся «живые» кабинеты, и человек жмёт кнопки на старом.
    """
    if replace_card:
        old = store.get(user['id']).get('card_message_id')
        if old:
            call(token, 'deleteMessage',
                 {'chat_id': chat_id, 'message_id': old}, quiet=True)
    screen = S.SCREENS[name]
    profile = load_profile(user)
    caption = screen['caption'](profile)
    markup = keyboard(screen, profile)
    banner = screen['banner']

    fid = _cache().get(banner)
    res = None
    if fid:
        res = call(token, 'sendPhoto', {
            'chat_id': chat_id, 'photo': fid, 'caption': caption,
            'parse_mode': 'HTML', 'reply_markup': markup}, quiet=True)
    if res is None:
        res = upload(token, 'sendPhoto', {
            'chat_id': str(chat_id), 'caption': caption,
            'parse_mode': 'HTML', 'reply_markup': json.dumps(markup)},
            'photo', banner_path(banner))
    if res and res.get('photo'):
        _remember(banner, res['photo'][-1]['file_id'])
    if res and replace_card:
        store.update(user['id'], chat_id=chat_id, card_message_id=res['message_id'],
                     name=user.get('first_name') or '')
    return res


def edit_screen(token, chat_id, message_id, name, user):
    """
    Переход — правка того же сообщения, а не новое. Меняются картинка,
    подпись и кнопки, поэтому editMessageMedia.
    """
    screen = S.SCREENS[name]
    profile = load_profile(user)
    fid = banner_id(token, chat_id, screen['banner'])
    if not fid:
        return None
    return call(token, 'editMessageMedia', {
        'chat_id': chat_id, 'message_id': message_id,
        'media': {'type': 'photo', 'media': fid,
                  'caption': screen['caption'](profile), 'parse_mode': 'HTML'},
        'reply_markup': keyboard(screen, profile),
    }, quiet=True)


# ── Молчаливый триал ───────────────────────────────────────────────
# Человек пришёл за VPN — незачем спрашивать, хочет ли он попробовать.
# Выдаём на /start. Повторный /start найдёт существующую учётку,
# Remnawave привязывает её к telegram id — накрутить не выйдет.

def ensure_trial(user):
    try:
        cfg = rw.load_config()
    except rw.NotConfigured:
        return None
    try:
        found, created = rw.create_trial(cfg, user['id'])
    except rw.RemnawaveError as e:
        print('  ! триал: %s' % e)
        return None
    if created:
        store.update(user['id'], trial_at=datetime.now(timezone.utc).isoformat())
        print('    выдан пробный период')
    return found


def show_home(token, chat_id, user):
    ensure_trial(user)
    profile = load_profile(user)
    return send_screen(token, chat_id, S.home(profile), user, replace_card=True)


# ── Действия ───────────────────────────────────────────────────────

def answer(token, cq, text=None, alert=False):
    payload = {'callback_query_id': cq['id']}
    if text:
        payload['text'] = text
        payload['show_alert'] = alert
    call(token, 'answerCallbackQuery', payload)


ACTIONS = {
    # TODO: оплата. Внутри мини-аппы это tg.openInvoice, ссылку выдаёт бэк.
    'buy': 'Оплата ещё не подключена.',
    'refstats': 'Статистика приглашений появится вместе с базой платежей.',
}


def on_callback(token, cq):
    data = cq.get('data') or ''
    user = cq['from']
    msg = cq.get('message') or {}

    if data.startswith('n:'):
        name = data[2:]
        if name == 'home':
            name = S.home(load_profile(user))
        if name not in S.SCREENS:
            answer(token, cq, 'Экран не найден')
            return
        answer(token, cq)
        edit_screen(token, msg['chat']['id'], msg['message_id'], name, user)
        return

    key = data[2:].split(':')[0]
    answer(token, cq, ACTIONS.get(key, 'Раздел ещё не подключён.'), alert=True)


def on_message(token, msg):
    text = msg.get('text') or ''
    parts = text.split()
    cmd = parts[0].split('@')[0].lower() if parts else ''
    args = parts[1:]

    if cmd == '/start':
        if args and args[0].startswith('ref'):
            # TODO: сохранить пригласившего, когда появится база
            print('    пришёл по ссылке %s' % args[0])
        show_home(token, msg['chat']['id'], msg['from'])
        return True

    if cmd == '/help':
        send_screen(token, msg['chat']['id'], 'howto', msg['from'])
        return True

    # Молчание выглядит как поломка. На любое слово отвечаем экраном,
    # а по нескольким приметам — сразу нужным разделом.
    low = text.lower()
    if any(w in low for w in ('не работает', 'не подключ', 'не открыв', 'ошибк', 'помог')):
        target = 'support'
    elif any(w in low for w in ('оплат', 'продл', 'куп', 'тариф', 'цена', 'стоим')):
        target = 'tariffs'
    elif any(w in low for w in ('инструк', 'настро', 'как подключ')):
        target = 'howto'
    else:
        show_home(token, msg['chat']['id'], msg['from'])
        return True
    send_screen(token, msg['chat']['id'], target, msg['from'])
    return True


def handle(token, update):
    if 'callback_query' in update:
        cq = update['callback_query']
        who = cq['from'].get('username') or cq['from']['id']
        print('  %s от %s' % (cq.get('data'), who))
        on_callback(token, cq)
        return

    msg = update.get('message')
    if not msg or 'text' not in msg:
        return
    who = msg['from'].get('username') or msg['from'].get('first_name') or msg['from']['id']
    done = on_message(token, msg)
    print('  %s от %s → %s' % (msg['text'].split()[0], who,
                               'экран отправлен' if done else 'обработчика нет'))


# ── Бот пишет первым ───────────────────────────────────────────────
# Три повода, у каждого свой ключ. Ключ привязан к дате окончания
# подписки, поэтому на новом периоде напоминание придёт снова,
# а внутри одного — ровно один раз.

CHECK_EVERY = 15 * 60          # как часто обходим пользователей
SILENT_AFTER_TRIAL = timedelta(hours=1)


def notify(token, chat_id, banner, text, buttons):
    fid = banner_id(token, chat_id, banner)
    if not fid:
        return None
    return call(token, 'sendPhoto', {
        'chat_id': chat_id, 'photo': fid, 'caption': text,
        'parse_mode': 'HTML',
        'reply_markup': {'inline_keyboard': buttons},
    })


def due_notifications(uid, rec, p, now):
    """Что нужно отправить этому человеку прямо сейчас. Может быть пусто."""
    out = []
    exp = p.get('expire_at')
    stamp = exp.isoformat() if exp else 'none'

    # 1. Взял подписку, но так и не настроил устройство
    trial_at = rec.get('trial_at')
    if (p['subscriptions'] and not p.get('sub_last_opened_at') and trial_at
            and now - datetime.fromisoformat(trial_at) > SILENT_AFTER_TRIAL
            and not store.was_notified(uid, 'connect', stamp)):
        out.append(('connect', stamp, 'howto-banner.png',
                    '🔌 <b>Остался один шаг</b>\n\n'
                    'Подписка у вас есть, но устройство ещё не настроено — '
                    'VPN пока не работает.\n\n'
                    '<blockquote><i>Это одна минута: приложение поставится само, '
                    'ключ подставится тоже.</i></blockquote>',
                    [[{'text': '🔌 Подключить', 'web_app': S.MINIAPP_URL}],
                     [{'text': '📘 Инструкция', 'callback_data': 'n:howto'}]]))

    if not exp:
        return out

    left = exp - now

    # 2. Подписка кончается
    if timedelta(0) < left <= timedelta(hours=24) and not store.was_notified(uid, 'expiring', stamp):
        hours = max(1, int(left.total_seconds() // 3600))
        out.append(('expiring', stamp, 'expiring-banner.png',
                    '⏳ <b>Осталось %d ч</b>\n\n'
                    'Подписка закончится %s. Продлите заранее, '
                    'чтобы не остаться без связи.'
                    % (hours, exp.strftime('%d.%m в %H:%M')),
                    [[{'text': '🛒 Продлить', 'callback_data': 'n:tariffs'}]]))

    # 3. Кончилась
    if left <= timedelta(0) and not store.was_notified(uid, 'expired', stamp):
        out.append(('expired', stamp, 'expired-banner.png',
                    '🔴 <b>VPN отключен</b>\n\n'
                    'Подписка закончилась %s. Восстановить доступ — минута.'
                    % exp.strftime('%d.%m.%Y'),
                    [[{'text': '🛒 Продлить подписку', 'callback_data': 'n:tariffs'}]]))
    return out


def notifier(token):
    """Фоновый обход. Без Remnawave данных нет — тогда просто ничего не шлём."""
    while True:
        time.sleep(CHECK_EVERY)
        try:
            now = datetime.now(timezone.utc)
            for uid, rec in store.all_users().items():
                chat_id = rec.get('chat_id')
                if not chat_id:
                    continue
                p = load_profile({'id': int(uid), 'first_name': rec.get('name')})
                for key, stamp, banner, text, buttons in due_notifications(uid, rec, p, now):
                    if notify(token, chat_id, banner, text, buttons):
                        store.mark_notified(uid, key, stamp)
                        print('  → напоминание «%s» для %s' % (key, uid))
        except Exception as e:
            print('  ! обход уведомлений: %r' % e)


def main():
    global BOT_USERNAME
    token = read_token()
    me = call(token, 'getMe')
    if not me:
        sys.exit('не удалось подключиться к Bot API')
    BOT_USERNAME = me['username']

    missing = sorted({s['banner'] for s in S.SCREENS.values()
                      if not os.path.exists(banner_path(s['banner']))})
    if missing:
        sys.exit('нет баннеров в assets/: %s' % ', '.join(missing))

    print('бот @%s слушает, экранов: %d. Ctrl+C — остановить'
          % (BOT_USERNAME, len(S.SCREENS)))

    threading.Thread(target=notifier, args=(token,), daemon=True).start()

    offset = None
    while True:
        updates = call(token, 'getUpdates', {
            'offset': offset, 'timeout': 30,
            'allowed_updates': ['message', 'callback_query'],
        })
        if updates is None:
            time.sleep(3)
            continue
        for u in updates:
            offset = u['update_id'] + 1
            try:
                handle(token, u)
            except Exception as e:      # один сбойный апдейт не роняет бота
                print('  ! ошибка обработки: %r' % e)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('\nостановлен')
