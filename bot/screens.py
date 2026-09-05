#!/usr/bin/env python3
"""
Экраны бота: содержимое отдельно от механики.

Правило навигации одно: бот не шлёт новые сообщения на каждое нажатие,
а перерисовывает одно и то же — баннер, подпись и кнопки. Иначе через
пять нажатий чат превращается в ленту, где не найти актуальный кабинет.

Два первых экрана — для двух разных людей:
    welcome  — новичок. Ему нужен рассказ и одна кнопка, а не номер счёта.
    cabinet  — тот, у кого подписка есть. Ему нужен статус: работает ли,
               до какого числа, где продлить.

Экран описывается словарём:
    banner   — файл в assets/
    caption  — функция profile → HTML-подпись (лимит Telegram 1024 символа)
    buttons  — функция profile → список рядов кнопок
    back     — куда ведёт «Назад» (у корневых экранов нет)

Кнопка — один из четырёх видов:
    {'text': …, 'nav': 'screen'}   переход на другой экран
    {'text': …, 'act': 'buy:m3'}   действие
    {'text': …, 'web_app': url}    открыть мини-аппу
    {'text': …, 'url': url}        внешняя ссылка
"""

from datetime import timedelta

HOUR = timedelta(hours=1)

MINIAPP_URL = 'https://hanproject.ru/vpnminiapp/'
CHANNEL_URL = 'https://t.me/hanvpn'          # TODO: настоящий канал
SUPPORT_URL = 'https://t.me/hanvpn_support'  # TODO: настоящая поддержка
TERMS_URL = 'https://hanproject.ru/terms'    # TODO: документы

# TODO: цены. На баннере «актуальные цены в боте» — значит правда живёт здесь.
TARIFFS = [
    {'id': 'm3', 'title': '3 месяца', 'price': '449 ₽',  'note': 'выгодно'},
    {'id': 'y1', 'title': 'Год',      'price': '1490 ₽', 'note': 'максимум'},
]

# TODO: реальная сумма. Без цифры партнёрская программа не мотивирует —
# «получайте вознаграждение» никого не заставит поделиться ссылкой.
REFERRAL_REWARD = '300 ₽'

# Инструкции живут в одном месте — в мини-аппе. Бот только выбирает
# устройство и открывает её сразу на нужном. Иначе текст в боте и мастер
# в мини-аппе рано или поздно разойдутся.
PLATFORMS = [
    ('ios',     '📱 iPhone · iPad'),
    ('android', '🤖 Android'),
    ('windows', '🪟 Windows'),
    ('macos',   '🍎 macOS'),
    ('tv',      '📺 Android TV'),
]

BACK = '‹ Назад'
HOME = '🏠 Кабинет'

MONTHS = ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня',
          'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря']


def esc(s):
    return str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def human_date(d):
    return '%d %s' % (d.day, MONTHS[d.month - 1])


def ago(delta):
    m = int(delta.total_seconds() // 60)
    if m < 1:
        return 'только что'
    if m < 60:
        return '%d мин назад' % m
    h = m // 60
    if h < 24:
        return '%d ч назад' % h
    return '%d дн назад' % (h // 24)


def miniapp(platform=None):
    return MINIAPP_URL + ('?platform=' + platform if platform else '')


# ── Первый экран новичка ───────────────────────────────────────────

def welcome_caption(p):
    if p['subscriptions']:
        # триал уже выдан молча на /start — говорим об этом как о факте
        gift = ('🎁 <b>Первые 3 дня — бесплатно, уже активированы</b>\n'
                'Действуют до %s.' % human_date(p['expire_at']))
    else:
        gift = '🎁 <b>Первые 3 дня — бесплатно.</b>'
    return (
        '<b>Han VPN</b>\n\n'
        'Безлимит, обход блокировок, 15+ стран. Без ограничений скорости.\n\n'
        '<blockquote>%s</blockquote>\n'
        'Нажмите «Подключить» — приложение поставится само, '
        'ключ подставится тоже. Одна минута.'
    ) % gift


def welcome_buttons(p):
    return [
        [{'text': '🔌 Подключить', 'web_app': miniapp()}],
        [{'text': '📘 Инструкции', 'nav': 'howto'},
         {'text': '💬 О сервисе', 'nav': 'info'}],
    ]


# ── Кабинет ────────────────────────────────────────────────────────

def connection_line(p):
    """
    Подписка и соединение — разные вещи. Человек хочет знать второе:
    работает ли у него сейчас. Отсюда состояния вместо одной даты.
    """
    if not p.get('sub_last_opened_at'):
        return ('⚠️ Устройство ещё не настроено',
                'Нажмите «Подключить» — это одна минута.')
    if p.get('online_at') and p['online_at'] > p['now'] - HOUR:
        return ('🟢 Подключено · были онлайн %s' % ago(p['now'] - p['online_at']),
                'Всё работает, делать ничего не нужно.')
    if p.get('online_at'):
        return ('🟡 Соединения не было %s' % ago(p['now'] - p['online_at']),
                'Откройте приложение и нажмите «Подключить». '
                'Если не выходит — загляните в поддержку.')
    return ('🟡 Настроено, но соединений ещё не было',
            'Откройте приложение и нажмите «Подключить».')


def cabinet_caption(p):
    state, hint = connection_line(p)
    until = ('VPN работает до <b>%s</b>' % human_date(p['expire_at'])
             if p.get('expire_at') else 'VPN работает')
    # Без ID и баланса: ID нужен только поддержке — он там и живёт;
    # баланса как понятия пока нет, показывать ноль — шум.
    return (
        '👤 <b>%s</b>\n\n'
        '<b>%s</b>\n%s\n\n'
        '<blockquote>🔧 <i>%s</i></blockquote>'
    ) % (esc(p['name']), state, until, hint)


def cabinet_buttons(p):
    # Главная кнопка — то, что человеку нужно сделать следующим.
    if not p.get('sub_last_opened_at'):
        rows = [[{'text': '🔌 Подключить', 'web_app': miniapp()}]]
    else:
        rows = [[{'text': '🛒 Продлить подписку', 'nav': 'tariffs'}],
                [{'text': '🔌 Подключить ещё устройство', 'web_app': miniapp()}]]
    rows += [
        [{'text': '🤝 Партнёрская программа', 'nav': 'referral'}],
        [{'text': '📘 Инструкции', 'nav': 'howto'},
         {'text': '💬 О сервисе', 'nav': 'info'}],
    ]
    return rows


# ── Тарифы ─────────────────────────────────────────────────────────

def tariffs_caption(p):
    rows = '\n'.join('%s — <b>%s</b>  · %s' % (t['title'], t['price'], t['note'])
                     for t in TARIFFS)
    return ('💳 <b>Тарифы</b>\n\n<blockquote>%s</blockquote>\n'
            'Безлимит, обход блокировок, 15+ стран. '
            'Ограничений по скорости нет.') % rows


def tariffs_buttons(p):
    return [[{'text': '%s · %s' % (t['title'], t['price']), 'act': 'buy:' + t['id']}]
            for t in TARIFFS]


# ── Инструкции ─────────────────────────────────────────────────────

def howto_caption(p):
    return ('📘 <b>Инструкции</b>\n\n'
            'Выберите устройство — откроется пошаговая настройка '
            'с проверкой на каждом шаге.\n\n'
            '<blockquote><i>Приложение поставится само, ключ подставится тоже. '
            'Если что-то пойдёт не так, экран подскажет, что делать.</i></blockquote>')


def howto_buttons(p):
    return [[{'text': title, 'web_app': miniapp(pid)}] for pid, title in PLATFORMS]


# ── Партнёрская программа ──────────────────────────────────────────

def referral_caption(p):
    return ('🤝 <b>Партнёрская программа</b>\n\n'
            '<b>%s</b> за каждого, кто оформит подписку по вашей ссылке.\n\n'
            '<blockquote>Ваша ссылка:\n<code>%s</code></blockquote>\n'
            '<i>Нажмите на ссылку, чтобы скопировать.</i>'
            ) % (REFERRAL_REWARD, esc(p['referral_link']))


def referral_buttons(p):
    share = ('https://t.me/share/url?url=%s&text=%s'
             % (p['referral_link'],
                'Han%20VPN%20%E2%80%94%20%D0%B1%D0%B5%D0%B7%D0%BB%D0%B8%D0%BC%D0%B8%D1%82'
                '%2C%203%20%D0%B4%D0%BD%D1%8F%20%D0%B1%D0%B5%D1%81%D0%BF%D0%BB%D0%B0%D1%82%D0%BD%D0%BE'))
    return [
        [{'text': '📤 Поделиться ссылкой', 'url': share}],
        [{'text': '👥 Мои приглашения', 'act': 'refstats'}],
    ]


# ── Информация ─────────────────────────────────────────────────────

def info_caption(p):
    return ('💬 <b>О сервисе</b>\n\n'
            'Han VPN — безлимитный доступ без ограничений скорости, '
            'обход блокировок, 15+ стран.\n\n'
            '<blockquote>Всё о сервисе в одном месте: '
            'как подключить, тарифы, инструкции и поддержка.</blockquote>')


def info_buttons(p):
    return [
        [{'text': '🔌 Как подключить', 'web_app': miniapp()}],
        [{'text': '💳 Тарифы', 'nav': 'tariffs'},
         {'text': '📘 Инструкции', 'nav': 'howto'}],
        [{'text': '💬 Поддержка', 'nav': 'support'}],
        [{'text': '📣 Наш канал', 'nav': 'channel'}],
        [{'text': '📄 Условия и документы', 'nav': 'terms'}],
    ]


def support_caption(p):
    # ID живёт здесь, а не в кабинете: он нужен ровно в момент обращения.
    return ('💬 <b>Поддержка</b>\n\n'
            'Отвечаем на вопросы и помогаем с настройкой.\n\n'
            '<blockquote>Не подключается\n'
            'Вопросы по оплате\n'
            'Настройка устройства</blockquote>\n'
            'Ваш ID для обращения: <code>%s</code>') % p['telegram_id']


SCREENS = {
    'welcome': {
        'banner': 'unlimited-banner.png',
        'caption': welcome_caption, 'buttons': welcome_buttons,
    },
    'cabinet': {
        'banner': 'cabinet-banner.png',
        'caption': cabinet_caption, 'buttons': cabinet_buttons,
    },
    'tariffs': {
        'banner': 'tariffs-banner.png', 'back': 'home',
        'caption': tariffs_caption, 'buttons': tariffs_buttons,
    },
    'howto': {
        'banner': 'howto-banner.png', 'back': 'home',
        'caption': howto_caption, 'buttons': howto_buttons,
    },
    'referral': {
        'banner': 'referral-banner.png', 'back': 'home',
        'caption': referral_caption, 'buttons': referral_buttons,
    },
    'info': {
        'banner': 'info-banner.png', 'back': 'home',
        'caption': info_caption, 'buttons': info_buttons,
    },
    'support': {
        'banner': 'support-banner.png', 'back': 'info',
        'caption': support_caption,
        'buttons': lambda p: [[{'text': '✍️ Написать в поддержку', 'url': SUPPORT_URL}]],
    },
    'channel': {
        'banner': 'channel-banner.png', 'back': 'info',
        'caption': lambda p: ('📣 <b>Канал Han VPN</b>\n\n'
                              'Новости, обновления и статус серверов.\n\n'
                              '<blockquote><i>Если VPN вдруг перестал работать — '
                              'сначала загляните сюда, обычно там уже есть ответ.</i></blockquote>'),
        'buttons': lambda p: [[{'text': '📣 Открыть канал', 'url': CHANNEL_URL}]],
    },
    'terms': {
        'banner': 'terms-banner.png', 'back': 'info',
        'caption': lambda p: ('📄 <b>Условия и документы</b>\n\n'
                              'Условия использования сервиса, политика '
                              'конфиденциальности и оферта.\n\n'
                              '<blockquote><i>Мы не храним логи вашего трафика.</i></blockquote>'),
        'buttons': lambda p: [[{'text': '📄 Открыть документы', 'url': TERMS_URL}]],
    },
}


def home(profile):
    """
    Корневой экран зависит от человека, а не от кнопки.
    Новичок — это не «без подписки» (триал выдаётся молча, подписка
    есть у всех), а «ни разу не подключался». Ему — рассказ и одна
    кнопка. Кто уже подключался — тому статус.
    """
    return 'cabinet' if profile.get('sub_last_opened_at') else 'welcome'
