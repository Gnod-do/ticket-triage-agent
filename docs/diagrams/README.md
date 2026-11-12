# Диаграммы решения

Исходники — Mermaid (`*.mmd`) для схем 02–05 и `draw_architecture.py` (matplotlib, фиксированная сетка 16:9) для схемы 01;
отрисованные версии — `rendered/*.png` (для DOCX и слайдов) и `rendered/*.svg`. Палитра общая: navy `#10314C` — детерминированный код,
teal `#00918F` — модели Qwen, orange `#F56A2B` — политика и решения, белый — люди, серый — данные.

Пересборка:
```bash
.venv/bin/python docs/diagrams/draw_architecture.py
npx -p @mermaid-js/mermaid-cli mmdc -i 02-business-process.mmd -o rendered/02-business-process.png -s 2 -b white -c mermaid-config.json
```
(если npm не видит корневые сертификаты: `NODE_EXTRA_CA_CERTS=/etc/ssl/cert.pem npm install @mermaid-js/mermaid-cli` в отдельную папку и запуск `node_modules/.bin/mmdc`).

| Файл | Что показывает | Где используется |
|---|---|---|
| `01-architecture` | 5 логических сервисов в 3 процессах, источники, получатели, контур без внешних API (рисуется `draw_architecture.py`) | Решение п.1, слайд «Архитектура» |
| `02-business-process` | Агент работает параллельно поддержке: всплеск → старший смены, тема → дайджест → решение команды | Решение п.1, слайд «Процесс» |
| `03-agent-workflow` | Алгоритм агента по кластеру, 4 исхода, PolicyGate, бюджет 8 вызовов | Решение п.2–3 |
| `04-digest-sequence` | Последовательность вызовов инструментов при создании элемента дайджеста | Решение п.2 |
| `05-rollout` | Офлайн-оценка → shadow → пилот → масштабирование и критерии перехода | Решение п.4 |

![Архитектура](rendered/01-architecture.png)
