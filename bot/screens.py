#!/usr/bin/env python3
"""
Экраны бота: содержимое отдельно от механики.

Аудитория — люди, которые не знают слов «ключ», «соединение» и «Android».
Правила текста: говорим, что человек увидит и что нажать; одно действие
на экран — крупно; кнопка называет результат; ничего похожего на кнопку,
что не нажимается; ни одного тупика.

Жизненный цикл подписки (profile['kind'] + profile['phase']):

    new ──активировал──▶ trial ──3 дня──▶ expiring ──▶ expired
                                                          │
                              ┌────── купил ◀─────────────┘
                              ▼
                             paid ──срок──▶ expiring ──▶ expired ──продлил──▶ paid

Корневой экран и баннер выбираются по состоянию, см. home() внизу.

Кнопка — один из четырёх видов:
    {'text': …, 'nav': 'screen'}   переход на другой экран
    {'text': …, 'act': 'buy:m3'}   действие
    {'text': …, 'web_app': url}    открыть мини-аппу
    {'text': …, 'url': url}        внешняя ссылка
"""

from datetime import datetime, timedelta, timezone

HOUR = timedelta(hours=1)
TRIAL_DAYS = 3

MINIAPP_URL = 'https://hanproject.ru/vpnminiapp/'
CHANNEL_URL = 'https://t.me/hanvpn'          # TODO: настоящий канал
SUPPORT_URL = 'https://t.me/hanvpn_support'  # TODO: настоящая поддержка
TERMS_URL = 'https://hanproject.ru/terms'    # TODO: документы

# TODO: цены. На баннере «актуальные цены в боте» — значит правда живёт здесь.
TARIFFS = [
    {'id': 'm1', 'title': '1 месяц',  'price': '199 ₽',  'days': 30,  'note': 'попробовать'},
    {'id': 'm3', 'title': '3 месяца', 'price': '449 ₽',  'days': 90,  'note': 'выгодно'},
    {'id': 'y1', 'title': 'Год',      'price': '1490 ₽', 'days': 365, 'note': 'ещё выгоднее'},
]
CHEAPEST = TARIFFS[0]

# TODO: реальная сумма за приглашённого.
REFERRAL_REWARD = '300 ₽'

# Человек знает марку телефона, а не название системы. Подсказываем.
PLATFORMS = [
    ('ios',     '📱 iPhone или iPad'),
    ('android', '🤖 Android — Samsung, Xiaomi, Huawei и др.'),
    ('windows', '💻 Ноутбук или компьютер с Windows'),
    ('macos',   '🍎 MacBook или iMac'),
    ('tv',      '📺 Телевизор'),
]

BACK = '‹ Назад'
HOME = '🏠 Кабинет'
CONNECT = '🔌 Подключить VPN'
HELP = '❓ Не понятно — помогите'

MONTHS = ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня',
          'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря']


def esc(s):
    return str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def human_date(d):
    # Экран не должен падать из-за пустой даты — лучше прочерк, чем ошибка.
    if not d:
        return '—'
    text = '%d %s' % (d.day, MONTHS[d.month - 1])
    # «до 7 декабря» через год выглядит как ошибка — уточняем год, если он не текущий
    if d.year != datetime.now(timezone.utc).year:
        text += ' %d' % d.year
    return text


def plural(n, one, few, many):
    a = abs(n) % 100
    b = a % 10
    if 10 < a < 20:
        return many
    if 1 < b < 5:
        return few
    return one if b == 1 else many


def span(delta):
    """«через 9 часов», «через 2 дня» — без часов по UTC, которые врут."""
    if delta is None:
        return '—'
    h = int(delta.total_seconds() // 3600)
    if h < 1:
        m = max(1, int(delta.total_seconds() // 60))
        return '%d %s' % (m, plural(m, 'минуту', 'минуты', 'минут'))
    if h < 48:
        return '%d %s' % (h, plural(h, 'час', 'часа', 'часов'))
    d = h // 24
    return '%d %s' % (d, plural(d, 'день', 'дня', 'дней'))


def ago(delta):
    return span(delta) + ' назад'


def miniapp(platform=None):
    return MINIAPP_URL + ('?platform=' + platform if platform else '')


def tariff(pid):
    return next((t for t in TARIFFS if t['id'] == pid), None)


# ── Новичок: VPN ещё не активирован ────────────────────────────────

def welcome_caption(p):
    return (
        '<b>Han VPN</b>\n\n'
        'Открывает сайты и приложения, которые без VPN не работают. '
        'Без ограничений по скорости и объёму.\n\n'
        '<blockquote>🎁 <b>Первые %d дня — бесплатно.</b>\n'
        'Карта не нужна. Потом — от %s в месяц, если понравится.</blockquote>\n'
        '👇 Нажмите кнопку, чтобы включить бесплатные дни.'
    ) % (TRIAL_DAYS, CHEAPEST['price'])


def welcome_buttons(p):
    return [
        [{'text': '🎁 Включить %d дня бесплатно' % TRIAL_DAYS, 'act': 'trial'}],
        [{'text': '💳 Сколько стоит потом', 'nav': 'tariffs'},
         {'text': HELP, 'nav': 'support'}],
    ]


# ── Только что активировали или оплатили ───────────────────────────

def activated_caption(p):
    if p['kind'] == 'trial':
        head = ('🎉 <b>Бесплатные %d дня включены</b>\n'
                'Работают до %s. Платить не нужно.' % (TRIAL_DAYS, human_date(p['until'])))
    else:
        head = ('🎉 <b>Подписка оплачена</b>\n'
                'Работает до %s.' % human_date(p['until']))
    step = ('Остался один шаг — включить VPN на телефоне. '
            'Нажмите кнопку: покажем, что скачать, и всё настроим. Одна минута.'
            if not p['connected'] else
            'VPN уже настроен — ничего делать не нужно, всё продолжает работать.')
    return '%s\n\n<blockquote>👇 %s</blockquote>' % (head, step)


def activated_buttons(p):
    if not p['connected']:
        return [[{'text': CONNECT, 'web_app': miniapp()}],
                [{'text': HELP, 'nav': 'support'}]]
    return [[{'text': '🏠 В кабинет', 'nav': 'home'}]]


# ── Кабинет: подписка действует ────────────────────────────────────

def connection_line(p):
    if not p['connected']:
        return ('🔴 VPN на этом устройстве ещё не включён',
                'Нажмите «Подключить VPN» — займёт одну минуту.')
    if p.get('online_at') and p['online_at'] > p['now'] - HOUR:
        return ('🟢 VPN работает', 'Всё в порядке, ничего делать не нужно.')
    if p.get('online_at'):
        return ('🟡 VPN не включён уже %s' % span(p['now'] - p['online_at']),
                'Откройте приложение VPN и нажмите в нём «Подключить». '
                'Не получается — напишите нам, поможем.')
    return ('🟢 VPN настроен', 'Откройте приложение VPN и нажмите в нём «Подключить».')


def period_line(p):
    if p['kind'] == 'trial':
        return ('🎁 Бесплатные дни — до <b>%s</b>. Потом от %s в месяц.'
                % (human_date(p['until']), CHEAPEST['price']))
    return 'Подписка оплачена до <b>%s</b>' % human_date(p['until'])


def cabinet_caption(p):
    state, hint = connection_line(p)
    return ('👤 <b>%s</b>\n\n<b>%s</b>\n%s\n\n<blockquote>👉 %s</blockquote>'
            % (esc(p['name']), state, period_line(p), hint))


def cabinet_buttons(p):
    if not p['connected']:
        rows = [[{'text': CONNECT, 'web_app': miniapp()}]]
    else:
        rows = [[{'text': ('💳 Купить подписку' if p['kind'] == 'trial' else '🛒 Продлить подписку'),
                  'nav': 'tariffs'}],
                [{'text': '➕ Подключить ещё телефон или ноутбук', 'web_app': miniapp()}]]
    rows += [
        [{'text': '🎁 Пригласить друга', 'nav': 'referral'}],
        [{'text': '📘 Как настроить', 'nav': 'howto'},
         {'text': '❓ Помощь', 'nav': 'info'}],
    ]
    return rows


# ── Истекает: меньше суток ─────────────────────────────────────────

def expiring_caption(p):
    what = 'Бесплатные дни заканчиваются' if p['kind'] == 'trial' else 'Подписка заканчивается'
    return (
        '⏳ <b>VPN отключится через %s</b>\n\n'
        '%s. Оплатите сейчас — и ничего не прервётся, '
        'настраивать заново не придётся.\n\n'
        '<blockquote>👇 Выберите срок — от %s в месяц.</blockquote>'
    ) % (span(p['left']), what, CHEAPEST['price'])


def expiring_buttons(p):
    rows = [[{'text': '💳 Купить подписку' if p['kind'] == 'trial' else '🛒 Продлить подписку',
              'nav': 'tariffs'}]]
    if not p['connected']:
        rows.append([{'text': CONNECT, 'web_app': miniapp()}])
    rows.append([{'text': '❓ Помощь', 'nav': 'info'}])
    return rows


# ── Истёк ──────────────────────────────────────────────────────────

def expired_caption(p):
    what = ('Бесплатные %d дня закончились' % TRIAL_DAYS if p['kind'] == 'trial'
            else 'Подписка закончилась %s' % human_date(p['until']))
    return (
        '🔴 <b>VPN отключён</b>\n\n'
        '%s. Чтобы включить снова, оплатите подписку.\n\n'
        '<blockquote>Настраивать заново не нужно: оплатите — '
        'и всё заработает как раньше.</blockquote>\n'
        '👇 От %s в месяц.'
    ) % (what, CHEAPEST['price'])


def expired_buttons(p):
    return [
        [{'text': '💳 Купить подписку' if p['kind'] == 'trial' else '🛒 Продлить подписку',
          'nav': 'tariffs'}],
        [{'text': '❓ Помощь', 'nav': 'info'}],
    ]


# ── Тарифы и оплата ────────────────────────────────────────────────

def tariffs_caption(p):
    rows = '\n'.join('<b>%s</b> — %s  · %s' % (t['title'], t['price'], t['note'])
                     for t in TARIFFS)
    return ('💳 <b>Сколько стоит</b>\n\n<blockquote>%s</blockquote>\n'
            'Одна подписка — на все ваши устройства. '
            'Скорость и объём не ограничены.\n\n'
            '👇 Выберите срок') % rows


def tariffs_buttons(p):
    return [[{'text': '%s — %s' % (t['title'], t['price']), 'act': 'buy:' + t['id']}]
            for t in TARIFFS]


def pay_screen(t):
    def caption(p):
        # Продление добавляется к остатку, а не съедает его.
        base = p['until'] if p['until'] and p['until'] > p['now'] else p['now']
        until = base + timedelta(days=t['days'])
        return ('💳 <b>%s — %s</b>\n\n'
                'После оплаты VPN будет работать до <b>%s</b>.\n\n'
                '<blockquote>Оплата картой или Telegram Stars. '
                'Подписка не продлевается сама — спишем только то, что вы выбрали.</blockquote>\n'
                '👇 Нажмите «Оплатить».') % (t['title'], t['price'], human_date(until))

    return {
        'banner': 'tariffs-banner.png', 'back': 'tariffs',
        'caption': caption,
        # TODO: в бою — sendInvoice. Пока кнопка помечена как демо.
        'buttons': lambda p: [[{'text': '💳 Оплатить %s (демо)' % t['price'], 'act': 'pay:' + t['id']}]],
    }


# ── Как настроить ──────────────────────────────────────────────────

def howto_caption(p):
    return ('📘 <b>Как настроить</b>\n\n'
            'Выберите, на чём хотите включить VPN. '
            'Дальше всё покажем по шагам.\n\n'
            '<blockquote>Скачивать и настраивать будем вместе — '
            'на каждом шаге подскажем, что нажать.</blockquote>')


def howto_buttons(p):
    return [[{'text': title, 'web_app': miniapp(pid)}] for pid, title in PLATFORMS]


# ── Пригласить друга ───────────────────────────────────────────────

def referral_caption(p):
    return ('🎁 <b>Пригласите друга</b>\n\n'
            'Отправьте другу вашу ссылку. Он получит %d дня бесплатно, '
            'а когда оплатит подписку — вы получите <b>%s</b>.\n\n'
            '<blockquote>Ваша ссылка:\n<code>%s</code></blockquote>\n'
            '👇 Нажмите «Отправить другу» — откроется список чатов.'
            ) % (TRIAL_DAYS, REFERRAL_REWARD, esc(p['referral_link']))


def referral_buttons(p):
    share = ('https://t.me/share/url?url=%s&text=%s'
             % (p['referral_link'],
                'Han%20VPN%20%E2%80%94%20%D0%B1%D0%B5%D0%B7%D0%BB%D0%B8%D0%BC%D0%B8%D1%82'
                '%2C%203%20%D0%B4%D0%BD%D1%8F%20%D0%B1%D0%B5%D1%81%D0%BF%D0%BB%D0%B0%D1%82%D0%BD%D0%BE'))
    return [
        [{'text': '📤 Отправить другу', 'url': share}],
        [{'text': '👥 Кого я пригласил', 'act': 'refstats'}],
    ]


# ── Помощь ─────────────────────────────────────────────────────────

def info_caption(p):
    return ('❓ <b>Помощь</b>\n\n'
            'Выберите, что вас интересует.\n\n'
            '<blockquote>Если не нашли ответ — нажмите «Написать нам», '
            'ответит живой человек.</blockquote>')


def info_buttons(p):
    return [
        [{'text': '🔌 Не работает VPN', 'nav': 'support'}],
        [{'text': '💳 Сколько стоит', 'nav': 'tariffs'},
         {'text': '📘 Как настроить', 'nav': 'howto'}],
        [{'text': '📣 Новости и статус серверов', 'nav': 'channel'}],
        [{'text': '📄 Документы', 'nav': 'terms'}],
        [{'text': '✍️ Написать нам', 'url': SUPPORT_URL}],
    ]


def support_caption(p):
    return ('💬 <b>Поддержка</b>\n\n'
            'Ответим и поможем с настройкой. '
            'Выберите, что случилось, или сразу напишите нам.\n\n'
            '<blockquote>Ваш номер для обращения: <code>%s</code>\n'
            'Нажмите на него — скопируется.</blockquote>') % p['telegram_id']


def support_buttons(p):
    return [
        [{'text': '🔌 Не подключается', 'web_app': miniapp()}],
        [{'text': '💳 Вопрос по оплате', 'url': SUPPORT_URL}],
        [{'text': '📘 Помогите настроить', 'nav': 'howto'}],
        [{'text': '✍️ Написать нам', 'url': SUPPORT_URL}],
    ]


SCREENS = {
    # корневые — выбираются по состоянию, см. home()
    'welcome':  {'banner': 'unlimited-banner.png', 'caption': welcome_caption,  'buttons': welcome_buttons},
    'cabinet':  {'banner': 'cabinet-banner.png',   'caption': cabinet_caption,  'buttons': cabinet_buttons},
    'expiring': {'banner': 'expiring-banner.png',  'caption': expiring_caption, 'buttons': expiring_buttons},
    'expired':  {'banner': 'expired-banner.png',   'caption': expired_caption,  'buttons': expired_buttons},

    'activated': {'banner': 'unlimited-banner.png', 'back': 'home',
                  'caption': activated_caption, 'buttons': activated_buttons},
    'tariffs':  {'banner': 'tariffs-banner.png', 'back': 'home',
                 'caption': tariffs_caption, 'buttons': tariffs_buttons},
    'howto':    {'banner': 'howto-banner.png', 'back': 'home',
                 'caption': howto_caption, 'buttons': howto_buttons},
    'referral': {'banner': 'referral-banner.png', 'back': 'home',
                 'caption': referral_caption, 'buttons': referral_buttons},
    'info':     {'banner': 'info-banner.png', 'back': 'home',
                 'caption': info_caption, 'buttons': info_buttons},
    'support':  {'banner': 'support-banner.png', 'back': 'info',
                 'caption': support_caption, 'buttons': support_buttons},
    'channel': {
        'banner': 'channel-banner.png', 'back': 'info',
        'caption': lambda p: ('📣 <b>Новости и статус серверов</b>\n\n'
                              'Если VPN вдруг перестал работать — загляните в канал: '
                              'там пишем, что случилось и когда починим.\n\n'
                              '<blockquote>👇 Нажмите «Открыть канал» и подпишитесь, '
                              'чтобы не пропустить.</blockquote>'),
        'buttons': lambda p: [[{'text': '📣 Открыть канал', 'url': CHANNEL_URL}]],
    },
    'terms': {
        'banner': 'terms-banner.png', 'back': 'info',
        'caption': lambda p: ('📄 <b>Документы</b>\n\n'
                              'Условия использования и правила обработки данных.\n\n'
                              '<blockquote>Мы не следим, какие сайты вы открываете, '
                              'и не храним историю.</blockquote>'),
        'buttons': lambda p: [[{'text': '📄 Открыть документы', 'url': TERMS_URL}]],
    },
}
for _t in TARIFFS:
    SCREENS['pay:' + _t['id']] = pay_screen(_t)

ROOTS = ('welcome', 'cabinet', 'expiring', 'expired')


def home(p):
    """Корневой экран — по состоянию подписки, а не по кнопке."""
    if p['kind'] == 'new':
        return 'welcome'
    if p['phase'] == 'expired':
        return 'expired'
    if p['phase'] == 'expiring':
        return 'expiring'
    return 'cabinet'
