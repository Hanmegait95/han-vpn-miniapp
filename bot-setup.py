#!/usr/bin/env python3
"""
Привязывает мини-аппу к боту через Bot API.

Токен читается из файла и никогда не передаётся аргументом — в списке
процессов аргументы видны другим пользователям машины, а в истории
шелла остаются навсегда.

    mkdir -p ~/.config/hanvpn && chmod 700 ~/.config/hanvpn
    printf '%s' 'ТОКЕН' > ~/.config/hanvpn/bot_token
    chmod 600 ~/.config/hanvpn/bot_token

Посмотреть, что настроено сейчас (ничего не меняет):

    python3 bot-setup.py

Применить:

    python3 bot-setup.py --apply
"""

import argparse
import json
import os
import stat
import sys
import urllib.error
import urllib.request

TOKEN_FILE = os.path.expanduser('~/.config/hanvpn/bot_token')
MINIAPP_URL = 'https://hanproject.ru/vpn/'
BUTTON_TEXT = 'Подключить VPN'

COMMANDS = [
    ('start',   'Кабинет'),
    ('connect', 'Подключить VPN'),
    ('help',    'Помощь — ответит человек'),
    ('pay',     'Купить или продлить'),
]

DESCRIPTION = 'Безлимитный VPN: обход блокировок, 15+ стран, без ограничений скорости.'
SHORT_DESCRIPTION = 'Безлимитный VPN в один шаг.'


def read_token(path):
    if not os.path.exists(path):
        sys.exit('нет файла с токеном: %s\nсм. подсказку вверху скрипта' % path)

    mode = stat.S_IMODE(os.stat(path).st_mode)
    if mode & 0o077:
        sys.exit('файл с токеном открыт другим пользователям (права %o).\n'
                 'закройте: chmod 600 %s' % (mode, path))

    token = open(path, encoding='utf-8').read().strip()
    if not token or ':' not in token:
        sys.exit('в файле не похоже на токен бота')
    return token


def call(token, method, payload=None):
    url = 'https://api.telegram.org/bot%s/%s' % (token, method)
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode('utf-8')
        headers['Content-Type'] = 'application/json'
    req = urllib.request.Request(url, data=data, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=20) as res:
            body = json.load(res)
    except urllib.error.HTTPError as e:
        body = json.load(e)
    except urllib.error.URLError as e:
        sys.exit('сеть недоступна: %s' % e.reason)

    if not body.get('ok'):
        # описание ошибки не содержит токена — печатать безопасно
        sys.exit('%s: %s' % (method, body.get('description', 'неизвестная ошибка')))
    return body['result']


def show(token):
    me = call(token, 'getMe')
    print('бот:      @%s (%s)' % (me.get('username'), me.get('first_name')))
    print('id:       %s' % me.get('id'))

    btn = call(token, 'getChatMenuButton')
    if btn.get('type') == 'web_app':
        print('кнопка:   «%s» → %s' % (btn.get('text'), btn.get('web_app', {}).get('url')))
    else:
        print('кнопка:   %s (мини-аппа не привязана)' % btn.get('type'))

    cmds = call(token, 'getMyCommands')
    print('команды:  %s' % (', '.join('/' + c['command'] for c in cmds) or 'нет'))


def apply(token):
    call(token, 'setChatMenuButton', {
        'menu_button': {
            'type': 'web_app',
            'text': BUTTON_TEXT,
            'web_app': {'url': MINIAPP_URL},
        }
    })
    # API отвечает ok, но значение не всегда сохраняется: кнопку с мини-аппой
    # Telegram надёжно принимает только из @BotFather. Проверяем честно.
    back = call(token, 'getChatMenuButton')
    same = (back.get('type') == 'web_app'
            and back.get('text') == BUTTON_TEXT
            and back.get('web_app', {}).get('url') == MINIAPP_URL)
    if same:
        print('кнопка меню → «%s» %s' % (BUTTON_TEXT, MINIAPP_URL))
    else:
        print('кнопка меню: API принял запрос, но сохранилось не то:')
        print('             сейчас «%s» → %s' % (back.get('text'), back.get('web_app', {}).get('url')))
        print('             поставьте вручную: @BotFather → /mybots → бот →')
        print('             Bot Settings → Menu Button → %s, подпись «%s»' % (MINIAPP_URL, BUTTON_TEXT))

    call(token, 'setMyCommands', {
        'commands': [{'command': c, 'description': d} for c, d in COMMANDS]
    })
    print('команды: %s' % ', '.join('/' + c for c, _ in COMMANDS))

    call(token, 'setMyDescription', {'description': DESCRIPTION})
    call(token, 'setMyShortDescription', {'short_description': SHORT_DESCRIPTION})
    print('описание обновлено')


def main():
    p = argparse.ArgumentParser(description='Привязка мини-аппы к боту')
    p.add_argument('--apply', action='store_true', help='применить настройки (без флага только показывает)')
    p.add_argument('--token-file', default=TOKEN_FILE)
    args = p.parse_args()

    token = read_token(args.token_file)

    print('— сейчас —')
    show(token)

    if not args.apply:
        print('\nничего не изменено. чтобы применить: python3 bot-setup.py --apply')
        return

    print('\n— применяю —')
    apply(token)
    print('\n— стало —')
    show(token)


if __name__ == '__main__':
    main()
