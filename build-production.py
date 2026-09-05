#!/usr/bin/env python3
"""
Собирает production/index.html из index.html.

Из прототипа убирается вся демонстрационная обвязка:
  · панель состояний <aside class="proto"> и её стили;
  · корпус телефона (.stage / .device / .scroll) — в бою страница
    занимает окно целиком, рамка нужна была только для показа;
  · заглушка API и захардкоженные строки статусов.

Вместо заглушки подставляется рабочий fetch и расчёт подписи из
expires_at. Места, где нужен ваш адрес, помечены TODO.

    python3 build-production.py
"""

import io
import os
import sys

SRC = 'index.html'
OUT = os.path.join('production', 'index.html')


def cut(s, start, end, label):
    """Вырезает кусок от start до end (end остаётся)."""
    i = s.find(start)
    if i < 0:
        sys.exit('не найдено начало: ' + label)
    j = s.find(end, i)
    if j < 0:
        sys.exit('не найден конец: ' + label)
    return s[:i] + s[j:]


def must_replace(s, old, new, label, count=1):
    if old not in s:
        sys.exit('не найдено для замены: ' + label)
    return s.replace(old, new, count)


def must_replace_all(s, old, new, label):
    return must_replace(s, old, new, label, count=-1)


DATA_LAYER = '''  /* ── Бэкенд ─────────────────────────────────────
     Один запрос. Авторизация — подписанным initData из Telegram;
     проверять подпись обязательно на сервере, идентификатор из тела
     запроса брать нельзя.

     Ответ:
       { expires_at:        ISO,            // когда заканчивается
         unlimited:         bool,           // бессрочная — вместо даты «Бессрочная»
         period_days:       number,         // длина оплаченного периода, для шкалы
         subscription_url:  string,         // ссылка подписки
         config_fetched_at: ISO | null,     // когда клиент забрал конфиг
         last_client:       string | null } // чем забрали, из user-agent

     config_fetched_at — то, на чём держится весь мастер: мини-апка не
     наблюдает за приложением (в вебвью Telegram это ненадёжно), она
     спрашивает сервер, забрали ли подписку. */

  const API_URL       = '/miniapp/status';                                  // TODO: свой адрес
  const DOWNLOAD_URL  = (device) => 'https://example.com/download/' + device; // TODO
  const OPEN_APP_URL  = (app) => 'https://example.com/open/' + app;           // TODO

  let SUB_LINK = '';   // приходит с бэка вместе со статусом

  async function fetchStatus() {
    const res = await fetch(API_URL, {
      cache: 'no-store',
      headers: { 'X-Telegram-Init-Data': (tg && tg.initData) || '' }
    });
    if (!res.ok) throw new Error('status ' + res.status);
    return res.json();
  }

  /* ── Статус подписки ────────────────────────────
     Из ответа бэка собирается то, что рисуется в шапке экрана. */
  const MONTHS = ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня',
                  'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря'];

  const fmtDate = (iso) => {
    const d = new Date(iso);
    return d.getDate() + ' ' + MONTHS[d.getMonth()] + ' ' + d.getFullYear();
  };

  const fmtTime = (iso) => {
    const d = new Date(iso);
    return String(d.getHours()).padStart(2, '0') + ':' + String(d.getMinutes()).padStart(2, '0');
  };

  function plural(n, one, few, many) {
    const a = Math.abs(n) % 100, b = a % 10;
    if (a > 10 && a < 20) return many;
    if (b > 1 && b < 5) return few;
    return b === 1 ? one : many;
  }

  const RENEW = { label: 'Продлить подписку', alarm: false };

  function describe(p) {
    if (p.unlimited) {
      return { name: 'active', beacon: 'активна', cmd: 'han --status',
               top: 'Подписка', bottom: 'активна',
               note: 'Бессрочная', pct: 100, val: '∞', renew: null };
    }

    const left = new Date(p.expires_at).getTime() - Date.now();

    if (left <= 0) {
      return { name: 'off', beacon: 'истекла', cmd: 'han --status',
               top: 'VPN', bottom: 'отключен',
               note: 'Подписка закончилась ' + fmtDate(p.expires_at),
               pct: 6, val: 'offline',
               renew: { label: RENEW.label, alarm: true } };
    }

    const hours = left / 3600000;
    const period = (p.period_days || 30) * 86400000;
    const pct = Math.max(4, Math.min(100, Math.round(left / period * 100)));

    if (hours < 24) {
      const h = Math.max(1, Math.round(hours));
      return { name: 'soon', beacon: 'истекает', cmd: 'han --expires',
               top: 'Осталось', bottom: h + ' ' + plural(h, 'час', 'часа', 'часов'),
               note: 'Отключится в ' + fmtTime(p.expires_at),
               pct, val: fmtTime(p.expires_at),
               renew: { label: RENEW.label, alarm: false } };
    }

    const d = Math.round(hours / 24);
    return { name: 'active', beacon: 'активна', cmd: 'han --status',
             top: 'Подписка', bottom: 'активна',
             note: 'Действует до ' + fmtDate(p.expires_at),
             pct, val: d + ' ' + plural(d, 'день', 'дня', 'дней'),
             renew: null };
  }

  let status = null;      // последний describe()
  let lastClient = null;

  function paintState(view) {
    status = view;
    app.dataset.state = view.name;
    $('beaconText').textContent = view.beacon;
    $('statusCmd').textContent = view.cmd;
    $('headTop').textContent = view.top;
    $('headBottom').textContent = view.bottom;
    $('statusNote').textContent = view.note;
    $('railFill').style.setProperty('--pct', view.pct + '%');
    $('railVal').textContent = view.val;
    app.removeAttribute('data-connect-open');
    paint();
  }

  /* TODO: оплата. Внутри мини-аппы это tg.openInvoice(url, cb),
     ссылку на счёт выдаёт бэк. Пока — переход в бота. */
  const renew = () => { buzz('medium'); toast('Открываем оплату'); };
'''


def main():
    s = io.open(SRC, encoding='utf-8').read()

    # ── стили обвязки ───────────────────────────────────────────
    s = cut(s, '  /* ── Оболочка прототипа ', '  @media (max-width: 359px)',
            'стили панели и корпуса')
    s = must_replace(
        s,
        '    padding-bottom: 260px;  /* кнопка главного действия + панель прототипа */',
        '    padding-bottom: 110px;  /* место под кнопку главного действия */',
        'отступ под панель')

    # ── разметка обвязки ────────────────────────────────────────
    for tag in ('<div class="stage">\n', '<div class="device">\n', '<div class="scroll">\n',
                '</div><!-- /scroll -->\n', '</div><!-- /device -->\n', '</div><!-- /stage -->\n'):
        s = must_replace(s, tag, '', 'обёртка ' + tag.strip())
    s = cut(s, '<aside class="proto"', '<script>', 'панель состояний')

    # ── слой данных ─────────────────────────────────────────────
    s = cut(s, '  /* ── Бэкенд ─────', '  /* ── Устройство и приложение ───', 'заглушка API')
    s = must_replace(s, '  /* ── Устройство и приложение ───',
                     DATA_LAYER + '\n  /* ── Устройство и приложение ───', 'вставка слоя данных')

    # ── обработчики панели ──────────────────────────────────────
    s = cut(s, '  /* ── Панель прототипа ───', '  /* ── Старт ───', 'обработчики панели')

    # ── статус: вместо трёх готовых состояний — расчёт из ответа ─
    s = must_replace(
        s,
        "    return statusName === 'off' && !app.hasAttribute('data-connect-open');",
        "    return !!status && status.name === 'off' && !app.hasAttribute('data-connect-open');",
        'wizardHidden')
    s = must_replace_all(s, '    const s = STATES[statusName];', '    const s = status;',
                         'обращения к STATES')
    # у состояния может быть своё действие (например «Повторить» при ошибке)
    s = must_replace_all(s, 'run: renew };', 'run: s.renew.run || renew };',
                         'действие кнопки статуса')

    # ── ссылки наружу и запуск ──────────────────────────────────
    s = must_replace(s, "openExternal('https://hanvpn.app/download/' + state.device)",
                     'openExternal(DOWNLOAD_URL(state.device))', 'ссылка на загрузку')
    s = must_replace(s, "openExternal('https://hanvpn.app/open/' + currentApp().toLowerCase())",
                     'openExternal(OPEN_APP_URL(currentApp().toLowerCase()))', 'ссылка на приложение')
    s = must_replace(s, "        demo.fetchedAt = Date.now() + 4500;   // заглушка: бэк «увидит» через 4.5 с\n", '',
                     'заглушка ожидания')
    s = must_replace(s, "    demo.fetchedAt = Date.now() + 7000;   // заглушка ручного пути\n", '',
                     'заглушка ручного пути')
    s = must_replace(s, "        { label: 'настроить другое устройство', run: () => { demo.fetchedAt = null; pickDevice(); } }",
                     "        { label: 'настроить другое устройство', run: pickDevice }",
                     'сброс в done')

    # якорь берём подлиннее: короткий совпадает раньше, внутри renderWizard
    tail = '\n  if (tg && tg.BackButton) {\n    tg.BackButton.onClick'
    boot_old = s[s.index('  async function boot() {'):s.index(tail)]
    boot_new = '''  async function boot() {
    const raw = await load();
    if (raw) { try { Object.assign(state, JSON.parse(raw)); } catch (e) {} }

    // Бот открывает мини-аппу сразу на нужном устройстве: ?platform=ios.
    // Явный выбор важнее сохранённого состояния и «уже настроено» с сервера.
    const want = new URLSearchParams(location.search).get('platform');
    if (want && DEVICES[want]) {
      state.device = want; state.appId = null; state.phase = 'install';
    }

    let payload;
    try {
      payload = await fetchStatus();
    } catch (e) {
      // Показать ошибку честно и дать повторить — пустой экран хуже.
      paintState({ name: 'off', beacon: 'нет связи', cmd: 'han --status',
                   top: 'Не удалось', bottom: 'загрузить',
                   note: 'Проверьте интернет и попробуйте ещё раз',
                   pct: 6, val: 'error',
                   renew: { label: 'Повторить', alarm: false, run: () => boot() } });
      return;
    }

    SUB_LINK = payload.subscription_url;
    if (payload.config_fetched_at && !want) {
      lastClient = payload.last_client;
      state.phase = 'done';
    } else if (state.phase === 'checking') {
      state.phase = 'link';   // вернулись в середине ожидания — начинаем заново
    }
    paintState(describe(payload));
  }

'''
    if not boot_old:
        sys.exit('пустой срез boot() — якорь совпал не там')
    s = s.replace(boot_old, boot_new, 1)

    s = must_replace(s, '''  // ссылку со #soon / #off / #ready можно вставить в адрес на лету
  window.addEventListener('hashchange', () => {
    stopWatch();
    demo.fetchedAt = null;
    demo.state = 'active';
    state.phase = 'install';
    readHash();
    markChips();
    boot();
  });

  readHash();
  markChips();
  boot();''', '  boot();', 'запуск')

    # ── проверки ────────────────────────────────────────────────
    leftovers = [w for w in ('demo.', 'markChips', 'readHash', 'writeHash', 'statusName',
                             'STATES', 'protoReset', 'class="proto', 'class="stage', 'class="device')
                 if w in s]
    if leftovers:
        sys.exit('в продакшен-версии осталась обвязка: ' + ', '.join(leftovers))

    os.makedirs('production', exist_ok=True)
    io.open(OUT, 'w', encoding='utf-8').write(s)
    print('%s — %d КБ' % (OUT, len(s.encode('utf-8')) // 1024))


if __name__ == '__main__':
    main()
