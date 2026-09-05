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

def main():
    s = io.open(SRC, encoding='utf-8').read()

    # ── слой данных: заглушка → бэк ─────────────────────────────
    s = cut(s, '  /* ── Бэкенд ─────', '  /* ── Статус ─────', 'заглушка бэка')
    s = must_replace(s, '  /* ── Статус ─────', DATA_LAYER + '  /* ── Статус ─────', 'вставка слоя данных')

    # ── ссылки наружу ───────────────────────────────────────────
    s = must_replace(s, "  const DOWNLOAD_URL = (device) => 'https://hanvpn.app/download/incy/' + device;   // TODO: ваш редирект в магазин",
                     "  const DOWNLOAD_URL = (device) => 'https://example.com/download/incy/' + device;    // TODO: ваш редирект в магазин",
                     'ссылка на загрузку')

    # ── оплата: без сервера не притворяемся, что оплатили ──────
    s = must_replace(s, """        await API.pay(t);
        paidHere = t.id; cheer();""",
"""        try { await API.pay(t); } catch (e) { return; }
        paidHere = t.id; cheer();""", 'оплата')
    s = must_replace(s, """    await API.trial();
    trialHere = true; cheer();""",
"""    try { await API.trial(); } catch (e) { toast('Не удалось включить. Попробуйте ещё раз'); return; }
    trialHere = true; cheer();""", 'триал')

    # ── ошибка сети: честный экран вместо пустого ───────────────
    s = must_replace(s, """    loadSub();
    const st = await API.status();""",
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

    # ── проверки ────────────────────────────────────────────────
    leftovers = [w for w in ("Q.get('kind')", 'han.sub', 'sub.hanvpn.app', 'class="proto', 'class="stage')
                 if w in s]
    if leftovers:
        sys.exit('в продакшен-версии осталась обвязка: ' + ', '.join(leftovers))

    os.makedirs('production', exist_ok=True)
    io.open(OUT, 'w', encoding='utf-8').write(s)
    print('%s — %d КБ' % (OUT, len(s.encode('utf-8')) // 1024))


if __name__ == '__main__':
    main()
