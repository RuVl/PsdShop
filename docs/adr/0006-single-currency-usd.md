---
status: accepted
---

# Одна валюта: цены в USD

Цена товара хранится и показывается в долларах. Переключателя валют на витрине нет, курсов в базе
нет, внешнего сервиса курсов нет.

Витрина двуязычная (ru/en), но язык интерфейса и валюта — разные вещи: Plisio всё равно выставляет
инвойс в крипте от фиатной суммы, и этой суммой всегда был доллар.

## Consequences

- `djmoney` и `djmoney.contrib.exchange` уходят из зависимостей: `MoneyField` заменяется на
  `DecimalField(max_digits=10, decimal_places=2)`, `SERIALIZATION_MODULES` и настройки
  `CURRENCIES/BASE_CURRENCY/EXCHANGE_BACKEND` — из `settings.py`.
- Уходит `OPENEXCHANGERATES_APP_ID`, цель `make update-rates` и эндпоинт `GET /api/exchange-rates/`.
  Вместе с ними — стор `currencies` и компонент `CurrencySwitch` на фронте.
- На `OrderItem` остаётся один снимок цены (`unit_price`): второе поле `unit_price_usd` было нужно
  только потому, что рублёвая цена конвертировалась каждый день по-новому.
- Появление второй валюты позже — это не «вернуть djmoney», а решение уровня ADR: снимок цены в
  заказе и сумма, отданная Plisio, должны остаться в одной валюте, иначе выручку не сложить.
