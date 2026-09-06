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
CHECK_URL = 'https://www.instagram.com/'      # TODO: сайт, который без VPN не открывается
TERMS_URL = 'https://hanproject.ru/terms'    # TODO: документы

# TODO: цены. На баннере «актуальные цены в боте» — значит правда живёт здесь.
TARIFFS = [
    {'id': 'm1', 'title': '1 месяц',  'price': '199 ₽',  'days': 30,  'devices': 3, 'note': 'попробовать'},
    {'id': 'm3', 'title': '3 месяца', 'price': '449 ₽',  'days': 90,  'devices': 3, 'note': 'выгодно'},
    {'id': 'y1', 'title': 'Год',      'price': '1490 ₽', 'days': 365, 'devices': 5, 'note': 'ещё выгоднее'},
]
CHEAPEST = TARIFFS[0]
TRIAL_DEVICES = 1          # бесплатные дни — на одно устройство

# TODO: реальная сумма за приглашённого.
REFERRAL_REWARD = '300 ₽'

# Человек знает марку телефона, а не название системы. Подсказываем.
PLATFORMS = [
    ('ios',     '📱 iPhone / iPad'),
    ('android', '🤖 Android-телефон'),
    ('windows', '💻 Windows (ноутбук, ПК)'),
    ('macos',   '🍎 MacBook / iMac'),
    ('tv',      '📺 Телевизор'),
]

# ── Анимация ───────────────────────────────────────────────────────
# Telegram умеет три вида анимации, и все три доступны обычному боту.
#
# 1. Анимированные эмодзи в тексте — <tg-emoji> в HTML-подписи.
#    Внутри тега остаётся обычный значок: клиент, который не покажет
#    анимацию, покажет его, и текст не сломается.
#    В кнопках анимация невозможна: подписи кнопок — только простой
#    текст, это ограничение Telegram, а не наше.
# 2. Эффект на сообщение (message_effect_id) — салют или огонь на весь
#    экран. Только в личных чатах и только на новом сообщении:
#    при правке старого эффект не показывается.
# 3. Реакция бота на сообщение человека (setMessageReaction).
#
# Выключить всю анимацию разом: ANIMATED = False.

ANIMATED = True

# id взяты из открытых наборов Telegram (Animated Emoji, Hand Emoji и
# другие) через getStickerSet — их можно обновить тем же способом.
EMOJI_IDS = {
    '🎉': '5436040291507247633',
    '🎁': '5199749070830197566',
    '👇': '5470177992950946662',
    '👉': '5471978009449731768',
    '🔥': '5420315771991497307',
    '⏳': '5451732530048802485',
    '👤': '5373012449597335010',
    '👋': '5195448447062251797',
    '✅': '5427009714745517609',
    '📤': '5433614747381538714',
    '👥': '5372926953978341366',
    '📣': '5469903029144657419',
    '🌐': '5359619818150436536',
    '➕': '5226945370684140473',
    '🛒': '5431499171045581032',
    '✍️': '5435884367014536083',
    '🚀': '5445284980978621387',
    '📱': '5407025283456835913',
    '💻': '5431376038628171216',
    '📺': '5373330964372004748',
    '🤖': '5372981976804366741',
    '🏠': '5235882793900188063',
    '👀': '5424885441100782420',
    '🔔': '5242628160297641831',
    '📊': '5431577498364158238',
    '💡': '5472146462362048818',
    '🎯': '5350460637182993292',
    '🥳': '5407057942388153892',
    '💰': '5375296873982604963',
    '⭐️': '5435957248314579621',
    '⚡️': '5431449001532594346',
}


def animate(text):
    """Подставляет анимированные эмодзи в готовый текст подписи."""
    if not ANIMATED or not text:
        return text
    for e, eid in EMOJI_SORTED:
        if e in text:
            text = text.replace(e, '<tg-emoji emoji-id="%s">%s</tg-emoji>' % (eid, e))
    return text


# длинные значки первыми: «⭐️» содержит «⭐», подменять надо целиком
EMOJI_SORTED = sorted(EMOJI_IDS.items(), key=lambda kv: -len(kv[0]))

# Эффекты на весь экран для пиковых моментов: включили бесплатные дни,
# оплатили, подключились. Больше нигде — иначе это перестанет радовать.
EFFECT_PARTY = '5046509860389126442'   # 🎉
EFFECT_FIRE  = '5104841245755180586'   # 🔥
EFFECT_LIKE  = '5107584321108051014'   # 👍
EFFECT_HEART = '5159385139981059251'   # ❤️


BACK = '◀️ Назад'
HOME = '🏠 Кабинет'   # только на нижней клавиатуре
CONNECT = '🔌 Подключить VPN'
HELP = '🆘 Помощь'

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


def devices_word(n):
    return '%d %s' % (n, plural(n, 'устройство', 'устройства', 'устройств'))


def up_to(n):
    # после «до» — родительный: «до 3 устройств», «до 1 устройства»
    return 'до %d %s' % (n, 'устройства' if n == 1 else 'устройств')


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


def miniapp(platform=None, p=None):
    """
    Ссылка на мини-аппу. p — подсказка о состоянии (kind/until): прототип
    без бэка узнаёт из неё, есть ли подписка, и умеет включить бесплатные
    дни сам. В бою мини-аппа спросит бэк по initData, параметр не нужен.
    """
    q = []
    if platform:
        q.append('platform=' + platform)
    if p:
        q.append('kind=' + p['kind'])
        if p.get('until'):
            q.append('until=' + p['until'].strftime('%Y-%m-%d'))
    return MINIAPP_URL + ('?' + '&'.join(q) if q else '')


def tariff(pid):
    return next((t for t in TARIFFS if t['id'] == pid), None)


# ── Новичок: VPN ещё не активирован ────────────────────────────────

def welcome_caption(p):
    invited = ('👋 <b>Вас пригласил %s</b> — первые %d дня бесплатно.\n\n'
               % (esc(p['referrer_name']), TRIAL_DAYS)) if p.get('referrer_name') else ''
    return (
        '<b>Han VPN</b>\n\n' + invited +
        'Открывает сайты и приложения, которые без VPN не работают. '
        'Без ограничений по скорости и объёму.\n\n'
        '<blockquote>🎁 <b>Первые %d дня — бесплатно</b>, на одно устройство.\n'
        'Включатся сами при первом подключении. Карта не нужна.</blockquote>\n'
        'Нужно сразу несколько устройств — купите подписку: от %s в месяц.\n\n'
        '👇 Одна кнопка — и через минуту VPN работает.'
    ) % (TRIAL_DAYS, CHEAPEST['price'])


def welcome_buttons(p):
    # Подключить — главное. Купить — видно сразу, не после пробных дней.
    # «Помощь» здесь не дублируем: она постоянно висит на нижней клавиатуре.
    return [
        [{'text': '🔌 Подключить VPN', 'web_app': miniapp(None, p)}],
        [{'text': '💳 Купить подписку', 'nav': 'tariffs'}],
    ]


# ── Только что активировали или оплатили ───────────────────────────

def activated_caption(p):
    if p['kind'] == 'trial':
        head = ('🎉 <b>Бесплатные %d дня включены</b>\n'
                'Работают до %s. Платить не нужно.' % (TRIAL_DAYS, human_date(p['until'])))
    else:
        plan = p.get('plan') or CHEAPEST
        head = ('🎉 <b>Подписка оплачена</b>\n'
                'Работает до %s · %s.' % (human_date(p['until']), up_to(plan['devices'])))
    step = ('Остался один шаг — включить VPN на телефоне. '
            'Нажмите кнопку: покажем, что скачать, и всё настроим. Одна минута.'
            if not p['connected'] else
            'VPN уже настроен — ничего делать не нужно, всё продолжает работать.')
    return '%s\n\n<blockquote>👇 %s</blockquote>' % (head, step)


def activated_buttons(p):
    if not p['connected']:
        return [[{'text': CONNECT, 'web_app': miniapp(None, p)}]]
    return []


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
        return ('🎁 Бесплатные дни до <b>%s</b> · %s.\n'
                'Нужно больше устройств — выберите тариф, от %s в месяц.'
                % (human_date(p['until']), devices_word(TRIAL_DEVICES), CHEAPEST['price']))
    plan = p.get('plan') or CHEAPEST
    return 'Подписка оплачена до <b>%s</b> · %s' % (human_date(p['until']), up_to(plan['devices']))


def cabinet_caption(p):
    state, hint = connection_line(p)
    return ('👤 <b>%s</b>\n\n<b>%s</b>\n%s\n\n<blockquote>👉 %s</blockquote>'
            % (esc(p['name']), state, period_line(p), hint))


def cabinet_buttons(p):
    """
    Одно главное действие сверху, не больше двух вспомогательных под ним.
    «Настройки» здесь нет: это та же мини-аппа, что и «Подключить», —
    она сама спрашивает устройство. Отдельный вход остался в «Помощи».
    """
    trial = p['kind'] == 'trial'
    if not p['connected']:
        # Не подключился — всё внимание на это. Звать друзей ещё рано.
        return [[{'text': CONNECT, 'web_app': miniapp(None, p)}],
                [{'text': '💳 Купить' if trial else '🛒 Продлить', 'nav': 'tariffs'},
                 {'text': HELP, 'nav': 'help'}]]
    rows = [[{'text': '💳 Купить подписку' if trial else '🛒 Продлить подписку',
              'nav': 'tariffs'}]]
    if not trial:
        # бесплатные дни — одно устройство; второе только по тарифу
        rows.append([{'text': '➕ Ещё устройство', 'web_app': miniapp(None, p)}])
    rows.append([{'text': '🎁 Пригласить', 'nav': 'referral'}, {'text': HELP, 'nav': 'help'}])
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
        rows.append([{'text': CONNECT, 'web_app': miniapp(None, p)}])
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
    return [[{'text': '💳 Купить подписку' if p['kind'] == 'trial' else '🛒 Продлить подписку',
              'nav': 'tariffs'}]]


# ── Тарифы и оплата ────────────────────────────────────────────────

def tariffs_caption(p):
    rows = '\n'.join('<b>%s</b> — %s · %s' % (t['title'], t['price'], up_to(t['devices']))
                     for t in TARIFFS)
    return ('💳 <b>Сколько стоит</b>\n\n<blockquote>%s</blockquote>\n'
            'Телефон, ноутбук и телевизор — одной подпиской. '
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
        return ('💳 <b>%s — %s</b> · %s\n\n'
                'После оплаты VPN будет работать до <b>%s</b>.\n\n'
                '<blockquote>Оплата картой или Telegram Stars. '
                'Подписка не продлевается сама — спишем только то, что вы выбрали.</blockquote>\n'
                '👇 Нажмите «Оплатить».') % (t['title'], t['price'], up_to(t['devices']), human_date(until))

    return {
        'banner': 'tariffs-banner.jpg', 'back': 'tariffs',
        'caption': caption,
        # TODO: в бою — sendInvoice. Пока кнопка помечена как демо.
        'buttons': lambda p: [[{'text': '💳 Оплатить %s (демо)' % t['price'], 'act': 'pay:' + t['id']}]],
    }


# ── Как настроить ──────────────────────────────────────────────────

def howto_caption(p):
    return ('📘 <b>Настройка</b>\n\n'
            'Выберите, на чём включить VPN — дальше всё покажем по шагам.\n\n'
            '<blockquote>Android — это Samsung, Xiaomi, Huawei, Honor, Realme '
            'и почти все телефоны, кроме iPhone.</blockquote>')


def howto_buttons(p):
    return [[{'text': title, 'web_app': miniapp(pid, p)}] for pid, title in PLATFORMS]


# ── Пригласить друга ───────────────────────────────────────────────

def referral_caption(p):
    return ('🎁 <b>Пригласите друга</b>\n\n'
            'Отправьте другу вашу ссылку. Он получит %d дня бесплатно, '
            'а когда оплатит подписку — вы получите <b>%s</b>.\n\n'
            '<blockquote>Ваша ссылка:\n<code>%s</code>\n'
            'Пришли по ней: <b>%d</b> · подключили VPN: <b>%d</b></blockquote>\n'
            '👇 Нажмите «Отправить другу» — откроется список чатов.'
            ) % (TRIAL_DAYS, REFERRAL_REWARD, esc(p['referral_link']), p.get('invited', 0), p.get('invited_connected', 0))


def referral_buttons(p):
    share = ('https://t.me/share/url?url=%s&text=%s'
             % (p['referral_link'],
                'Han%20VPN%20%E2%80%94%20%D0%B1%D0%B5%D0%B7%D0%BB%D0%B8%D0%BC%D0%B8%D1%82'
                '%2C%203%20%D0%B4%D0%BD%D1%8F%20%D0%B1%D0%B5%D1%81%D0%BF%D0%BB%D0%B0%D1%82%D0%BD%D0%BE'))
    # «Мои приглашения» здесь была лишней: те же два числа уже в тексте выше.
    return [[{'text': '📤 Отправить другу', 'url': share}]]


# ── Помощь: один экран, и писать можно прямо сюда ──────────────────

def help_caption(p):
    return ('🆘 <b>Помощь</b>\n\n'
            'Нажмите, что подходит. Если ничего не помогло — '
            '<b>напишите нам</b>, ответит живой человек.\n\n'
            '<blockquote>Ваш номер для обращения: <code>%s</code>\n'
            'Нажмите на него — скопируется.</blockquote>\n'
            'Перестало работать сразу у всех — смотрите «Новости»: '
            'там пишем, что случилось и когда починим. '
            '<a href="%s">Условия и документы</a>.') % (p['telegram_id'], TERMS_URL)


def help_buttons(p):
    # «Цены» убраны: кнопка покупки есть на каждом корневом экране.
    # «Новости» ведут в канал напрямую, документы — ссылкой в тексте:
    # экран ради одной ссылки — лишнее нажатие.
    return [
        [{'text': '🔌 Показать подключение', 'web_app': miniapp(None, p)}],
        [{'text': '📘 Настройка', 'nav': 'howto'}, {'text': '📣 Новости', 'url': CHANNEL_URL}],
        [{'text': '✍️ Написать нам', 'url': SUPPORT_URL}],
    ]


SCREENS = {
    # корневые — выбираются по состоянию, см. home()
    'welcome':  {'banner': 'unlimited-banner.jpg', 'caption': welcome_caption,  'buttons': welcome_buttons},
    'cabinet':  {'banner': 'cabinet-banner.jpg',   'caption': cabinet_caption,  'buttons': cabinet_buttons},
    'expiring': {'banner': 'expiring-banner.jpg',  'caption': expiring_caption, 'buttons': expiring_buttons},
    'expired':  {'banner': 'expired-banner.jpg',   'caption': expired_caption,  'buttons': expired_buttons},

    'activated': {'banner': lambda p: 'ready-banner.jpg' if p['connected'] else 'unlimited-banner.jpg',
                  'back': 'home',
                  'caption': activated_caption, 'buttons': activated_buttons},
    # Мини-аппа сообщила «подключился» — экран-подтверждение на своём баннере
    'ready': {'banner': 'ready-banner.jpg', 'back': 'home',
              'caption': lambda p: ('🟢 <b>Подписка добавлена в приложение</b>\n\n'
                                    'Включите VPN в самом приложении — кнопка «Подключить» на его '
                                    'главном экране.\n\n'
                                    '<blockquote>Проверить просто: нажмите «Проверить» — открылся сайт, '
                                    'значит работает. Не открылся — «Помощь» внизу.</blockquote>'
                                    + ('\n%s' % period_line(p) if p['until'] else '')),
              'buttons': lambda p: [[{'text': '🌐 Проверить VPN', 'url': CHECK_URL}]]},
    'tariffs':  {'banner': 'tariffs-banner.jpg', 'back': 'home',
                 'caption': tariffs_caption, 'buttons': tariffs_buttons},
    'howto':    {'banner': 'howto-banner.jpg', 'back': 'home',
                 'caption': howto_caption, 'buttons': howto_buttons},
    'referral': {'banner': 'referral-banner.jpg', 'back': 'home',
                 'caption': referral_caption, 'buttons': referral_buttons},
    'help':     {'banner': 'help-banner.jpg', 'back': 'home',
                 'caption': help_caption, 'buttons': help_buttons},
}
for _t in TARIFFS:
    SCREENS['pay:' + _t['id']] = pay_screen(_t)

ROOTS = ('welcome', 'cabinet', 'expiring', 'expired')

# Постоянная клавиатура под полем ввода. Не зависит от того, какая
# карточка на экране, — «Помощь» в одно нажатие откуда угодно.
# «Подключить VPN» здесь — KeyboardButton с web_app: только так мини-аппа
# сможет ответить боту через sendData (из инлайн-кнопок это не работает).
KB_CONNECT, KB_HOME, KB_HELP = '🔌 Подключить VPN', '🏠 Кабинет', '🆘 Помощь'
KEYBOARD_VERSION = 2


def reply_keyboard():
    return {
        'keyboard': [
            [{'text': KB_CONNECT, 'web_app': {'url': miniapp() + '?src=kb'}}],
            [{'text': KB_HOME}, {'text': KB_HELP}],
        ],
        'resize_keyboard': True,
        'is_persistent': True,
        'input_field_placeholder': 'Нажмите кнопку внизу',
    }


def home(p):
    """Корневой экран — по состоянию подписки, а не по кнопке."""
    if p['kind'] == 'new':
        return 'welcome'
    if p['phase'] == 'expired':
        return 'expired'
    if p['phase'] == 'expiring':
        return 'expiring'
    return 'cabinet'
