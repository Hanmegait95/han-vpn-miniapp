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


def banner_of(screen, profile):
    b = screen['banner']
    return b(profile) if callable(b) else b


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

def parse_dt(v):
    try:
        return datetime.fromisoformat(v) if v else None
    except ValueError:
        return None


def load_profile(user):
    """
    Состояние подписки. Источник правды в прототипе — store.py; в бою
    его место займёт ваша база платежей, а Remnawave останется источником
    правды про доступ: срок и факт подключения.

      kind   — new | trial | paid
      phase  — active | expiring (< суток) | expired | None (для new)
      until  — конец текущего периода
      connected — забирали ли конфиг (Remnawave) или отметка демо
    """
    now = datetime.now(timezone.utc)
    rec = store.get(user['id'])
    p = {
        'name': user.get('first_name') or user.get('username') or 'без имени',
        'telegram_id': user['id'],
        'now': now,
        'referral_link': 'https://t.me/%s?start=ref%s' % (BOT_USERNAME, user['id']),
        'kind': 'new', 'phase': None, 'until': None, 'left': None,
        'connected': bool(rec.get('connected')),
        'sub_last_opened_at': None, 'online_at': None,
        'plan': S.tariff(rec.get('plan')) if rec.get('plan') else None,
    }

    paid_until = parse_dt(rec.get('paid_until'))
    trial_until = parse_dt(rec.get('trial_until'))
    if paid_until:
        p['kind'], p['until'] = 'paid', paid_until
    elif trial_until:
        p['kind'], p['until'] = 'trial', trial_until

    # Remnawave знает срок и факт подключения точнее, чем локальная запись
    try:
        cfg = rw.load_config()
        found = rw.find_user(cfg, user['id'])
    except rw.NotConfigured:
        found = None
    except rw.RemnawaveError as e:
        print('  ! Remnawave: %s' % e)
        found = None
    if found:
        if found['expire_at']:
            p['until'] = found['expire_at']
            if p['kind'] == 'new':
                p['kind'] = 'trial'
        p['sub_last_opened_at'] = found['sub_last_opened_at']
        p['online_at'] = found['online_at']
        p['connected'] = p['connected'] or bool(found['sub_last_opened_at'])

    if p['until']:
        p['left'] = p['until'] - now
        if p['left'] <= timedelta(0):
            p['phase'] = 'expired'
        elif p['left'] <= timedelta(hours=24):
            p['phase'] = 'expiring'
        else:
            p['phase'] = 'active'
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
    # Домой — с любого экрана в одно нажатие. «Назад» показываем только
    # когда он ведёт не домой, иначе две кнопки делали бы одно и то же.
    if screen.get('back'):
        home = S.home(profile)
        back = home if screen['back'] == 'home' else screen['back']
        nav = []
        if back != home:
            nav.append({'text': S.BACK, 'callback_data': 'n:' + back})
        nav.append({'text': S.HOME, 'callback_data': 'n:home'})
        rows.append(nav)
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
    banner = banner_of(screen, profile)

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
        rec = store.get(user['id'])
        if rec.get('card_message_id'):
            call(token, 'unpinChatMessage',
                 {'chat_id': chat_id, 'message_id': rec['card_message_id']}, quiet=True)
        store.update(user['id'], chat_id=chat_id, card_message_id=res['message_id'],
                     name=user.get('first_name') or '')
        # Карточка закреплена — кабинет всегда наверху чата, под напоминаниями не тонет
        call(token, 'pinChatMessage',
             {'chat_id': chat_id, 'message_id': res['message_id'], 'disable_notification': True},
             quiet=True)
        ensure_keyboard(token, chat_id, user)
    return res


def ensure_keyboard(token, chat_id, user):
    """Постоянная клавиатура — один раз на версию, чтобы не спамить."""
    if store.get(user['id']).get('kb_version') == S.KEYBOARD_VERSION:
        return
    call(token, 'sendMessage', {
        'chat_id': chat_id,
        'text': '👇 Три кнопки внизу — они всегда под рукой. '
                'А если что-то непонятно, просто напишите сюда: ответит человек.',
        'reply_markup': S.reply_keyboard(),
    })
    store.update(user['id'], kb_version=S.KEYBOARD_VERSION)


def edit_screen(token, chat_id, message_id, name, user):
    """
    Переход — правка того же сообщения, а не новое. Меняются картинка,
    подпись и кнопки, поэтому editMessageMedia.
    """
    screen = S.SCREENS[name]
    profile = load_profile(user)
    fid = banner_id(token, chat_id, banner_of(screen, profile))
    if not fid:
        return None
    return call(token, 'editMessageMedia', {
        'chat_id': chat_id, 'message_id': message_id,
        'media': {'type': 'photo', 'media': fid,
                  'caption': screen['caption'](profile), 'parse_mode': 'HTML'},
        'reply_markup': keyboard(screen, profile),
    }, quiet=True)


def show_home(token, chat_id, user):
    profile = load_profile(user)
    return send_screen(token, chat_id, S.home(profile), user, replace_card=True)


# ── Действия ───────────────────────────────────────────────────────

def answer(token, cq, text=None, alert=False):
    payload = {'callback_query_id': cq['id']}
    if text:
        payload['text'] = text
        payload['show_alert'] = alert
    call(token, 'answerCallbackQuery', payload)


def act_trial(token, cq):
    """Явная активация бесплатных дней. Второй раз не выдаём."""
    user, msg = cq['from'], cq['message']
    p = load_profile(user)
    if p['kind'] != 'new':
        answer(token, cq, 'Бесплатные дни уже были. Дальше — подписка.', alert=True)
        edit_screen(token, msg['chat']['id'], msg['message_id'], S.home(p), user)
        return
    now = datetime.now(timezone.utc)
    until = now + timedelta(days=S.TRIAL_DAYS)
    store.update(user['id'], trial_at=now.isoformat(), trial_until=until.isoformat())
    # В бою здесь же — rw.create_trial(); прототип без панели работает на store.
    try:
        cfg = rw.load_config()
        rw.create_trial(cfg, user['id'])
    except (rw.NotConfigured, rw.RemnawaveError):
        pass
    answer(token, cq, 'Готово — %d дня бесплатно включены.' % S.TRIAL_DAYS)
    edit_screen(token, msg['chat']['id'], msg['message_id'], 'activated', user)


def act_buy(token, cq, plan_id):
    if not S.tariff(plan_id):
        answer(token, cq, 'Такого тарифа нет'); return
    answer(token, cq)
    msg = cq['message']
    edit_screen(token, msg['chat']['id'], msg['message_id'], 'pay:' + plan_id, cq['from'])


def act_pay(token, cq, plan_id):
    """
    ДЕМО. В бою: sendInvoice → pre_checkout_query → successful_payment,
    и только после successful_payment — то, что ниже.
    Продление прибавляется к остатку, а не съедает его.
    """
    t = S.tariff(plan_id)
    if not t:
        answer(token, cq, 'Такого тарифа нет'); return
    user, msg = cq['from'], cq['message']
    p = load_profile(user)
    base = p['until'] if p['until'] and p['until'] > p['now'] else p['now']
    until = base + timedelta(days=t['days'])
    store.update(user['id'], paid_until=until.isoformat(), plan=plan_id,
                 paid_at=p['now'].isoformat())
    try:
        cfg = rw.load_config()
        found = rw.find_user(cfg, user['id'])
        if found and found['uuid']:
            rw._request(cfg, 'PATCH', '/api/users', {'uuid': found['uuid'], 'expireAt': until.isoformat()})
    except (rw.NotConfigured, rw.RemnawaveError):
        pass
    answer(token, cq, 'Оплачено (демо). Работает до %s.' % S.human_date(until))
    edit_screen(token, msg['chat']['id'], msg['message_id'], 'activated', user)


ACTIONS = {
    'refstats': 'Скоро здесь будет список тех, кто пришёл по вашей ссылке.',
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
        chat_id, mid = msg['chat']['id'], msg['message_id']
        is_root = name in S.ROOTS
        card = store.get(user['id']).get('card_message_id')
        if is_root and card and mid != card:
            # Домой нажали не в карточке, а, например, в напоминании.
            # Не плодим второй кабинет: это сообщение убираем, карточку обновляем.
            call(token, 'deleteMessage', {'chat_id': chat_id, 'message_id': mid}, quiet=True)
            if not edit_screen(token, chat_id, card, name, user):
                send_screen(token, chat_id, name, user, replace_card=True)
            return
        edit_screen(token, chat_id, mid, name, user)
        return

    parts = data[2:].split(':')
    key, arg = parts[0], (parts[1] if len(parts) > 1 else None)
    if key == 'trial':
        act_trial(token, cq); return
    if key == 'buy':
        act_buy(token, cq, arg); return
    if key == 'pay':
        act_pay(token, cq, arg); return
    answer(token, cq, ACTIONS.get(key, 'Этот раздел ещё в работе.'), alert=True)


def on_web_app_data(token, msg):
    """Мини-аппа рассказала, чем кончилось подключение."""
    try:
        data = json.loads(msg['web_app_data']['data'])
    except (KeyError, ValueError):
        return
    user, chat_id = msg['from'], msg['chat']['id']
    ev = data.get('event')
    print('  мини-аппа: %s от %s' % (ev, user.get('username') or user['id']))
    if ev == 'connected':
        store.update(user['id'], connected=True)
        send_screen(token, chat_id, 'ready', user, replace_card=True)
    elif ev == 'failed':
        print('    не подключилось: %s, шаг %s' % (data.get('device', '?'), data.get('phase', '?')))
        call(token, 'sendMessage', {'chat_id': chat_id,
             'text': 'Вижу, что подключить не получилось. Вот что можно сделать 👇'})
        send_screen(token, chat_id, 'help', user)


def on_message(token, msg):
    if 'web_app_data' in msg:
        on_web_app_data(token, msg); return True

    text = msg.get('text') or ''
    parts = text.split()
    cmd = parts[0].split('@')[0].lower() if parts else ''
    args = parts[1:]

    # кнопки постоянной клавиатуры приходят обычным текстом
    if text == S.KB_HOME:
        show_home(token, msg['chat']['id'], msg['from']); return True
    if text == S.KB_HELP:
        send_screen(token, msg['chat']['id'], 'help', msg['from']); return True

    if cmd == '/connect':
        call(token, 'sendMessage', {'chat_id': msg['chat']['id'], 'text': '👇 Нажмите, чтобы подключить VPN',
             'reply_markup': {'inline_keyboard': [[{'text': S.CONNECT, 'web_app': {'url': S.miniapp()}}]]}})
        return True

    if cmd == '/start':
        if args and args[0].startswith('ref'):
            # TODO: сохранить пригласившего, когда появится база
            print('    пришёл по ссылке %s' % args[0])
        show_home(token, msg['chat']['id'], msg['from'])
        return True

    if cmd in ('/help', '/support'):
        send_screen(token, msg['chat']['id'], 'help', msg['from'])
        return True
    if cmd == '/pay':
        send_screen(token, msg['chat']['id'], 'tariffs', msg['from'])
        return True

    # Прототип: /demo new|trial|expiring|expired|paid|connected|reset
    # переводит вашу запись в нужное состояние. В продакшене удалить.
    if cmd == '/demo':
        now = datetime.now(timezone.utc)
        iso = lambda d: (now + d).isoformat()
        presets = {
            'new':       dict(trial_until=None, paid_until=None, plan=None, connected=False, trial_at=None),
            'trial':     dict(trial_until=iso(timedelta(days=3)), paid_until=None, plan=None, trial_at=now.isoformat()),
            'expiring':  dict(trial_until=iso(timedelta(hours=9)), paid_until=None, plan=None),
            'expired':   dict(trial_until=iso(-timedelta(days=1)), paid_until=None, plan=None),
            'paid':      dict(paid_until=iso(timedelta(days=90)), plan='m3'),
            'connected': dict(connected=True),
            'reset':     dict(trial_until=None, paid_until=None, plan=None, connected=False, trial_at=None, notified={}),
        }
        want = args[0].lower() if args else ''
        if want not in presets:
            call(token, 'sendMessage', {'chat_id': msg['chat']['id'],
                 'text': 'Состояния: ' + ' · '.join(presets)})
            return True
        store.update(msg['from']['id'], **presets[want])
        show_home(token, msg['chat']['id'], msg['from'])
        return True

    if cmd.startswith('/'):
        show_home(token, msg['chat']['id'], msg['from'])
        return True

    # Молчание выглядит как поломка. На любой текст отвечаем экраном,
    # а по приметам — сразу нужным разделом. Поддержка — отдельный бот.
    low = text.lower()
    if any(w in low for w in ('оплат', 'продл', 'куп', 'тариф', 'цен', 'стои', 'скольк')):
        target = 'tariffs'
    elif any(w in low for w in ('инструк', 'настро', 'как подключ')):
        target = 'howto'
    elif any(w in low for w in ('не работает', 'не подключ', 'ошибк', 'помог', 'поддерж')):
        target = 'help'
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

# Часовой пояс Telegram не отдаёт. Аудитория российская — считаем по Москве:
# ночью не пишем, а время называем относительно («через 9 часов»),
# чтобы не врать про часы.
MSK = timezone(timedelta(hours=3))
QUIET_FROM, QUIET_TO = 23, 9


def quiet_now():
    h = datetime.now(MSK).hour
    return h >= QUIET_FROM or h < QUIET_TO


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
    if p['kind'] == 'new' or not p['until']:
        return out
    stamp = p['until'].isoformat()
    trial = p['kind'] == 'trial'

    # 1. Включил бесплатные дни, но за час так и не настроил устройство
    trial_at = parse_dt(rec.get('trial_at'))
    if (not p['connected'] and trial_at and now - trial_at > SILENT_AFTER_TRIAL
            and p['phase'] == 'active' and not store.was_notified(uid, 'connect', stamp)):
        out.append(('connect', stamp, 'howto-banner.png',
                    '🔌 <b>Остался один шаг</b>\n\n'
                    'Бесплатные дни уже идут, а VPN ещё не включён. '
                    'Давайте настроим — это одна минута.\n\n'
                    '<blockquote>👇 Нажмите кнопку, дальше подскажем, что делать.</blockquote>',
                    [[{'text': S.CONNECT, 'web_app': S.MINIAPP_URL}],
                     [{'text': S.HELP, 'callback_data': 'n:help'}]]))

    # 2. Меньше суток
    if p['phase'] == 'expiring' and not store.was_notified(uid, 'expiring', stamp):
        out.append(('expiring', stamp, 'expiring-banner.png',
                    '⏳ <b>VPN отключится через %s</b>\n\n%s. Оплатите сейчас — '
                    'и ничего не прервётся, настраивать заново не придётся.'
                    % (S.span(p['left']),
                       'Бесплатные дни заканчиваются' if trial else 'Подписка заканчивается'),
                    [[{'text': '💳 Купить подписку' if trial else '🛒 Продлить подписку',
                       'callback_data': 'n:tariffs'}]]))

    # 3. Кончилось
    if p['phase'] == 'expired' and not store.was_notified(uid, 'expired', stamp):
        out.append(('expired', stamp, 'expired-banner.png',
                    '🔴 <b>VPN отключён</b>\n\n%s. Оплатите — и всё заработает снова, '
                    'настраивать заново не нужно.'
                    % ('Бесплатные дни закончились' if trial
                       else 'Подписка закончилась ' + S.human_date(p['until'])),
                    [[{'text': '💳 Купить подписку' if trial else '🛒 Продлить подписку',
                       'callback_data': 'n:tariffs'}]]))
    return out


def notifier(token):
    """Фоновый обход. Без Remnawave данных нет — тогда просто ничего не шлём."""
    while True:
        time.sleep(CHECK_EVERY)
        if quiet_now():
            continue      # ночью молчим; отметок не ставим — отправим утром
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

    names = set()
    for sc in S.SCREENS.values():
        b = sc['banner']
        names.update([b] if isinstance(b, str) else
                     [b({'connected': c}) for c in (True, False)])
    missing = sorted(n for n in names if not os.path.exists(banner_path(n)))
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
