#!/usr/bin/env python3
"""
Собирает production/index.html из index.html.

Прототип держит состояние подписки в адресе (kind/until от бота)
и в памяти браузера. Сборка заменяет этот блок на два запроса к бэку
по initData: статус и включение бесплатных дней; оплату оставляет
как TODO под tg.openInvoice. Места, где нужен ваш адрес, помечены TODO.

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


DATA_LAYER = """  /* ── Бэкенд ─────────────────────────────────────
     Два запроса, оба авторизуются подписанным initData из Telegram;
     подпись проверять на сервере, идентификатор из тела брать нельзя.

       GET  /miniapp/status  → { kind: 'new'|'trial'|'paid',
                                 expires_at: ISO | null,       // null — подписки нет
                                 subscription_url: string,
                                 config_fetched_at: ISO | null, // когда клиент забрал конфиг
                                 last_client: string | null }
       POST /miniapp/trial   → включить бесплатные дни
       оплата — tg.openInvoice(url) со ссылкой на счёт от бэка (TODO) */

  const API_URL   = '/miniapp/status';                                     // TODO
  const TRIAL_URL = '/miniapp/trial';                                      // TODO
  const TRIAL_DAYS = 3;
  const TARIFFS = [
    { id: 'm1', title: '1 месяц',  price: '199 ₽',  days: 30 },            // TODO: цены
    { id: 'm3', title: '3 месяца', price: '449 ₽',  days: 90 },
    { id: 'y1', title: 'Год',      price: '1490 ₽', days: 365 },
  ];
  let SUB_LINK = '';               // приходит с бэка вместе со статусом
  const DEMO_NOTE = '';            // предупреждение о заглушке — только в прототипе
  const CHECK_URL = 'https://www.instagram.com/';                          // TODO: сайт, который без VPN не открывается
  const TRIAL_DEVICES = 1;
  const sub = { kind: 'new', until: null, fetchedAt: null };
  function loadSub() {}            // в бою состояние только с бэка
  function saveSub() {}

  const headers = () => ({ 'X-Telegram-Init-Data': (tg && tg.initData) || '' });
  const API = {
    async status() {
      const res = await fetch(API_URL, { cache: 'no-store', headers: headers() });
      if (!res.ok) throw new Error('status ' + res.status);
      const p = await res.json();
      SUB_LINK = p.subscription_url || SUB_LINK;
      return p;
    },
    async trial() {
      const res = await fetch(TRIAL_URL, { method: 'POST', cache: 'no-store', headers: headers() });
      if (!res.ok) throw new Error('trial ' + res.status);
    },
    async pay(plan) {
      // TODO: ссылку на счёт выдаёт бэк; tg.openInvoice(url, status => …)
      toast('Оплата ещё не подключена');
      throw new Error('payments not wired');
    },
  };

"""

def check_js(html, label):
    """Синтаксис inline-скриптов: node, а на macOS без node — JavaScriptCore
    через osascript (тот же движок, что в WebView клиента Telegram для macOS).
    Нет ни того ни другого — пропускаем с пометкой."""
    import re, shutil, subprocess, tempfile
    scripts = [m.group(1) for m in re.finditer(r'<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>', html, re.S)]
    if shutil.which('node'):
        def run(path): return subprocess.run(['node', '--check', path], capture_output=True, text=True)
    elif shutil.which('osascript'):
        jxa = ("function run(a){ObjC.import('Foundation');"
               "const s=$.NSString.stringWithContentsOfFileEncodingError(a[0],4,null).js;"
               "new Function(s);return 'ok';}")
        def run(path): return subprocess.run(['osascript', '-l', 'JavaScript', '-e', jxa, path],
                                             capture_output=True, text=True)
    else:
        print('  синтаксис JS не проверен: нет ни node, ни osascript')
        return
    for n, code in enumerate(scripts, 1):
        with tempfile.NamedTemporaryFile('w', suffix='.js', delete=False, encoding='utf-8') as f:
            f.write(code); path = f.name
        r = run(path); os.unlink(path)
        if r.returncode:
            sys.exit('%s: ошибка синтаксиса в скрипте %d:\n%s' % (label, n, (r.stderr or r.stdout).strip()))
    print('  синтаксис JS: %s — %d скрипт(а) без ошибок' % (label, len(scripts)))


def main():
    s = io.open(SRC, encoding='utf-8').read()
    check_js(s, SRC)

    # Всё, что объявлено в вырезаемом куске: если имя останется в ходу,
    # а объявление уедет, страница упадёт на первом же обращении.
    import re
    i, j = s.find('  /* ── Бэкенд ─────'), s.find('  /* ── Статус ─────')
    # Только верхний уровень модуля (два пробела отступа): локальные
    # переменные внутри функций уезжают вместе со своими функциями.
    dropped = set(re.findall(r'(?m)^  (?:const|let|var|function)\s+([A-Za-z_$][\w$]*)', s[i:j]))

    # ── слой данных: заглушка → бэк ─────────────────────────────
    s = cut(s, '  /* ── Бэкенд ─────', '  /* ── Статус ─────', 'заглушка бэка')
    s = must_replace(s, '  /* ── Статус ─────', DATA_LAYER + '  /* ── Статус ─────', 'вставка слоя данных')

    # ── ссылки на магазины настоящие, править нечего ─────────────

    # ── оплата: без сервера не притворяемся, что оплатили ──────
    s = must_replace(s, """        await API.pay(t);
        paidHere = t.id; cheer();""",
"""        try { await API.pay(t); } catch (e) { return; }
        paidHere = t.id; cheer();""", 'оплата')
    s = must_replace(s, """    await API.trial();
    trialHere = true;
    toast(TRIAL_DAYS + ' дня бесплатно включены');
    return API.status();""",
"""    try { await API.trial(); } catch (e) { toast('Не удалось включить бесплатные дни'); return st; }
    trialHere = true;
    toast(TRIAL_DAYS + ' дня бесплатно включены');
    return API.status();""", 'триал')

    # ── ошибка сети: честный экран вместо пустого ───────────────
    s = must_replace(s, """    loadSub();
    let st = await API.status();""",
"""    loadSub();
    let st;
    try { st = await API.status(); }
    catch (e) {
      paintState({ name: 'off', beacon: 'нет связи', cmd: 'han --status',
                   top: 'Не удалось', bottom: 'загрузить',
                   note: 'Проверьте интернет и попробуйте ещё раз', pct: 6, val: 'error',
                   renew: { label: 'Повторить', run: () => boot() } });
      return;
    }""", 'ошибка сети')

    # ── телеметрия прототипа: в бою пустышка ─────────────────────
    s = cut(s, '  /* Телеметрия прототипа:', "  window.addEventListener('error'", 'телеметрия')
    s = must_replace(s, "  window.addEventListener('error'",
                     "  window.beacon = function () {};\n\n  window.addEventListener('error'", 'пустышка beacon')
    s = must_replace(s, "  beacon('script');\n", '', 'первый сигнал телеметрии')

    # ── тестовые крючки прототипа (sim=…) в бою не нужны ─────────
    s = must_replace(s, "    } else if (!Q.has('sim')) {      // sim=… — проверка в браузере без запуска приложений",
                     "    } else {", 'sim в openExternal')
    s = cut(s, '    // Подтверждение приходит только с сервера',
            '    openExternal(', 'подделка подтверждения')

    # ── проверки ────────────────────────────────────────────────
    leftovers = [w for w in ("Q.get('kind')", 'han.sub', 'sub.hanvpn.app', 'sim=', "Q.has('sim')", 'class="proto', 'class="stage',
                               'log.php', 'sendBeacon')
                 if w in s]
    if leftovers:
        sys.exit('в продакшен-версии осталась обвязка: ' + ', '.join(leftovers))

    # Синтаксис такого не ловит: имя используется, а объявления нет.
    # «sub.kind» — не использование имени kind, поэтому обращения
    # к свойствам не считаем.
    lost = sorted(n for n in dropped
                  if re.search(r'(?<![.\w$])%s\b' % n, s)
                  and not re.search(r'\b(?:const|let|var|function)\s+%s\b' % n, s))
    if lost:
        sys.exit('в продакшен-версии используется, но нигде не объявлено: %s\n'
                 'перенесите объявление в DATA_LAYER' % ', '.join(lost))

    check_js(s, OUT)
    os.makedirs('production', exist_ok=True)
    io.open(OUT, 'w', encoding='utf-8').write(s)
    print('%s — %d КБ' % (OUT, len(s.encode('utf-8')) // 1024))


if __name__ == '__main__':
    main()
