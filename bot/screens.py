#!/usr/bin/env python3
"""
Экраны бота: содержимое отдельно от механики.

Аудитория — люди, которые не знают слов «ключ», «соединение» и «Android».
Поэтому правила для текста:
  · говорим, что человек увидит и что нажать, а не как это устроено;
  · одно действие на экран — крупно; остальное — ниже и короче;
  · кнопка называет результат: «Подключить VPN», а не «Далее»;
  · ничего, что выглядит как кнопка, но не нажимается;
  · ни одного тупика: любой экран ведёт дальше или к живому человеку.

Механика навигации: бот перерисовывает одно сообщение, а не шлёт новые.

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
    {'id': 'y1', 'title': 'Год',      'price': '1490 ₽', 'note': 'ещё выгоднее'},
]

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

MONTHS = ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня',
          'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря']


def esc(s):
    return str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def human_date(d):
    return '%d %s' % (d.day, MONTHS[d.month - 1])


def plural(n, one, few, many):
    a = abs(n) % 100
    b = a % 10
    if 10 < a < 20:
        return many
    if 1 < b < 5:
        return few
    return one if b == 1 else many


def ago(delta):
    m = int(delta.total_seconds() // 60)
    if m < 1:
        return 'только что'
    if m < 60:
        return '%d %s назад' % (m, plural(m, 'минуту', 'минуты', 'минут'))
    h = m // 60
    if h < 24:
        return '%d %s назад' % (h, plural(h, 'час', 'часа', 'часов'))
    d = h // 24
    return '%d %s назад' % (d, plural(d, 'день', 'дня', 'дней'))


def miniapp(platform=None):
    return MINIAPP_URL + ('?platform=' + platform if platform else '')


# ── Первый экран новичка ───────────────────────────────────────────

def welcome_caption(p):
    if p['subscriptions']:
        gift = ('🎁 <b>3 дня бесплатно — уже включены</b>\n'
                'Работают до %s. Платить не нужно.' % human_date(p['expire_at']))
    else:
        gift = '🎁 <b>Первые 3 дня — бесплатно.</b>\nПлатить не нужно.'
    return (
        '<b>Han VPN</b>\n\n'
        'Открывает сайты и приложения, которые без VPN не работают. '
        'Без ограничений по скорости и объёму.\n\n'
        '<blockquote>%s</blockquote>\n'
        '👇 Нажмите кнопку — покажем, что скачать, и всё настроим. '
        'Займёт одну минуту.'
    ) % gift


def welcome_buttons(p):
    # У новичка одна задача — подключиться. Вторая кнопка — живой человек,
    # если что-то непонятно. Остальное найдётся потом, в кабинете.
    return [
        [{'text': CONNECT, 'web_app': miniapp()}],
        [{'text': '❓ Не понятно — помогите', 'nav': 'support'}],
    ]


# ── Кабинет ────────────────────────────────────────────────────────

def connection_line(p):
    """
    Подписка и VPN на телефоне — разные вещи, и человек хочет знать
    именно второе: работает ли у него сейчас. Говорим прямо: включён
    или нет, и что сделать.
    """
    if not p.get('sub_last_opened_at'):
        return ('🔴 VPN на этом устройстве ещё не включён',
                'Нажмите «Подключить VPN» — займёт одну минуту.')
    if p.get('online_at') and p['online_at'] > p['now'] - HOUR:
        return ('🟢 VPN работает',
                'Всё в порядке, ничего делать не нужно.')
    if p.get('online_at'):
        return ('🟡 VPN не включён уже %s' % ago(p['now'] - p['online_at']).replace(' назад', ''),
                'Откройте приложение VPN и нажмите в нём «Подключить». '
                'Не получается — напишите нам, поможем.')
    return ('🟡 VPN настроен, но ещё ни разу не включался',
            'Откройте приложение VPN и нажмите в нём «Подключить».')


def cabinet_caption(p):
    state, hint = connection_line(p)
    if p.get('expire_at'):
        paid = 'Подписка оплачена до <b>%s</b>' % human_date(p['expire_at'])
    else:
        paid = 'Подписка активна'
    return (
        '👤 <b>%s</b>\n\n'
        '<b>%s</b>\n%s\n\n'
        '<blockquote>👉 %s</blockquote>'
    ) % (esc(p['name']), state, paid, hint)


def cabinet_buttons(p):
    # Первая кнопка — то, что нужно сделать прямо сейчас.
    if not p.get('sub_last_opened_at'):
        rows = [[{'text': CONNECT, 'web_app': miniapp()}]]
    else:
        rows = [[{'text': '🛒 Продлить подписку', 'nav': 'tariffs'}],
                [{'text': '➕ Подключить ещё телефон или ноутбук', 'web_app': miniapp()}]]
    rows += [
        [{'text': '🎁 Пригласить друга', 'nav': 'referral'}],
        [{'text': '📘 Как настроить', 'nav': 'howto'},
         {'text': '❓ Помощь', 'nav': 'info'}],
    ]
    return rows


# ── Тарифы ─────────────────────────────────────────────────────────

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
            'Отправьте другу вашу ссылку. Он получит 3 дня бесплатно, '
            'а когда оплатит подписку — вы получите <b>%s</b>.\n\n'
            '<blockquote>Ваша ссылка:\n<code>%s</code></blockquote>\n'
            '👇 Нажмите «Отправить другу» — откроется список чатов.'
            ) % (REFERRAL_REWARD, esc(p['referral_link']))


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
    # ID живёт здесь, а не в кабинете: он нужен ровно в момент обращения.
    return ('💬 <b>Поддержка</b>\n\n'
            'Ответим и поможем с настройкой. '
            'Выберите, что случилось, или сразу напишите нам.\n\n'
            '<blockquote>Ваш номер для обращения: <code>%s</code>\n'
            'Нажмите на него — скопируется.</blockquote>') % p['telegram_id']


def support_buttons(p):
    # Раньше эти три пункта были текстом и выглядели как кнопки —
    # люди в них тыкали. Теперь это кнопки, и каждая куда-то ведёт.
    return [
        [{'text': '🔌 Не подключается', 'web_app': miniapp()}],
        [{'text': '💳 Вопрос по оплате', 'url': SUPPORT_URL}],
        [{'text': '📘 Помогите настроить', 'nav': 'howto'}],
        [{'text': '✍️ Написать нам', 'url': SUPPORT_URL}],
    ]


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
        'caption': support_caption, 'buttons': support_buttons,
    },
    'channel': {
        'banner': 'channel-banner.png', 'back': 'info',
        'caption': lambda p: ('📣 <b>Новости и статус серверов</b>\n\n'
                              'Если VPN вдруг перестал работать — '
                              'загляните в канал: там пишем, что случилось '
                              'и когда починим.\n\n'
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


def home(profile):
    """
    Корневой экран зависит от человека, а не от кнопки.
    Новичок — это не «без подписки» (триал выдаётся молча, подписка
    есть у всех), а «ни разу не подключался». Ему — рассказ и одна
    кнопка. Кто уже подключался — тому статус.
    """
    return 'cabinet' if profile.get('sub_last_opened_at') else 'welcome'
