---
type: meta
tags: [cicd, database, frontend, infra, llm, testing]
---

# CHECKPOINT.md — [[STORY-87]] Workflow Integration Tests

> Created: 2026-06-16
> Branch: prompts (HEAD: dc19f9b)
> Status: **NEEDS HARDENING** — tests pass but don't prove real flow works

---

## Что есть сейчас

**103 integration tests pass, 12 skipped (L1 sandbox).**

Детальная разбивка:
- `test_bootstrap_cli.py` (10) — flags, env vars, exit codes, legacy mode
- `test_phase_sync.py` (13) — SYNC artifact creation, repo state capture, prompt content
- `test_phase_engage.py` (4) — ENGAGE gating + prompt structure
- `test_phase_act.py` (4) — ACT gating + prompt content (pytest, no-commit)
- `test_phase_wrap.py` (4) — WRAP gating + prompt content (commit format, rvc transition)
- `test_gate_errors.py` (9) — every L3 error case (missing artifact, pending status, malformed)
- `test_artifact_schema.py` (7) — L2 field validation (ISO-8601 timestamp, short SHA, status values)
- `test_full_pipeline.py` (1) — SYNC→ENGAGE→ACT→WRAP golden path
- `test_idempotence.py` (6) — re-run safety for all phases
- `test_sandbox_lifecycle.py` (6, ALL SKIPPED) — L1 worktree, not yet implemented

**session_bootstrap.sh** — all 4 phases implemented, L3 gating works, ACT/WRAP/RVC pre-flight from [[STORY-87]].

---

## Что НЕ проверено (реальные проблемы)

### Problem 1: Тесты не запускают реальный rvc

`rvc issue` и `rvc context` вызываются скриптом напрямую. В тестах:
- Если rvc в PATH — вызывается реальный rvc (может упасть если vault не настроен)
- Если rvc не в PATH — fallback на placeholder text

Нет теста где реальный rvc читает реальный story файл и возвращает реальное issue содержимое. Мы не знаем работает ли prompt с реальными данными или схлопнется.

**Решение:** сделать integration fixture который указывает VAULT на реальный `adlai-vault/` и запускает `--phase sync [[STORY-87]]`. Проверить что prompt содержит реальный title, реальные decisions/gotchas. Это уже полутест-полуручной запуск.

### Problem 2: Golden path тест — мок-агент

`test_full_pipeline.py::test_full_pipeline` — всё делает `set_artifact_status()` + `inject_*()` helpers. Это симуляция, а не реальное прохождение. Реальный агент:
- Читает ENGAGE артефакт, реализует код
- Запускает `uv run pytest backend/tests/unit -q`, парсит результат
- Заполняет ACT артефакт реальными данными
- Делает git commit, rvc issue review

**Решение:** Невозможно автоматизировать без LLM, но можно сделать E2E bash-агент:
```bash
# test_e2e_manual.sh — запускается человеком
# 1. Создаёт temp vault + story
# 2. Запускает --phase sync → проверяет exit 0, artifact
# 3. Читает SYNC артефакт глазами (или парсером), заполняет ready
# 4. Запускает --phase engage → проверяет промпт
# 5. Повторяет для ACT и WRAP
# 6. Все assertions в bash, логи в stdout
```

### Problem 3: Idempotence проверяет только SYNC-маркер

`test_sync_idempotent_no_duplicate` проверяет что `<!-- l3:phase=sync` не дублируется. Но не проверяет:
- Что `status=pending` не перезапишется back to pending при повторном запуске
- Что artifact body (Timestamp, branch, head) остаётся нетронутым
- Что `ARTIFACT TARGET` в promptе корректно ссылается на существующий артефакт

**Решение:** Добавить assertions в idempotence тесты — сравнивать artifact body побайтно до и после повторного запуска (кроме timestamp).

### Problem 4: Нет теста на полный промпт-контент для ACT/WRAP

SYNC промпт проверяется детально (HARD STOP, forbidden rules, ARTIFACT TARGET). Для ACT/WRAP проверяется только:
- `## PHASE: ACT` / `## PHASE: WRAP` присутствует
- `uv run pytest` в ACT
- `git commit` / `rvc issue` в WRAP

Нет проверки что промпт содержит ENGAGE plan reference для ACT или что WRAP требует DECISIONS.md/GOTCHAS.md update.

**Решение:** Добавить `test_act_prompt_references_engage_plan` — проверить что stdout содержит "Read the ENGAGE artifact" + имя файла. Добавить `test_wrap_prompts_decisions_and_gotchas`.

### Problem 5: WRAP промпт говорит "git commit" но не запрещает менять код

ACT промпт содержит `### Forbidden: Do NOT commit`. WRAP промпт содержит `### Forbidden: Do NOT write code. Do NOT modify tests.` — это проверяется только косвенно (`test_wrap_prompt_includes_commit_format`).

**Решение:** Добавить explicit assertion: `assert "Do NOT write code" in stdout[wrap_start:]` для WRAP фазы.

### Problem 6: L3 гейт проверяет только sync/engage/act но не wrap

`test_wrap_blocks_act_pending` — проверяет что ACT pending блокирует WRAP. Но нет теста что:
- WRAP блокируется если ENGAGE pending (даже если ACT ready)
- WRAP блокируется если SYNC pending (даже если все остальные ready)

По скрипту — да, wrap проверяет SYNC + ENGAGE + ACT, но тесты не покрывают все комбинации.

**Решение:** Добавить `test_wrap_blocks_on_engage_pending` и `test_wrap_blocks_on_sync_pending`.

---

## Что нужно прямо сейчас (по приоритету)

| # | Задача | Сложность | Что даёт |
|---|--------|-----------|----------|
| 1 | Запустить `--phase sync [[STORY-87]]` на реальном vault вручную | 5 мин | Увидеть живой промпт, понять работает ли на реальных данных |
| 2 | Добавить E2E bash harness (Problem 2) | 30 мин | Максимально автоматизированный flow без LLM |
| 3 | Дополнить ACT/WRAP prompt content assertions (Problem 4) | 15 мин | Покрыть что промпты содержат все нужные секции |
| 4 | Добавить wrap gate combo tests (Problem 6) | 15 мин | Полный L3 coverage |
| 5 | Idempotence deep-check (Problem 3) | 10 мин | Убедиться что ре-ран не ломает body |

---

## Что нужно от Лекса

1. **Запуск на реальном vault**: `bash adlai-vault/00_Project/session_bootstrap.sh --phase sync [[STORY-87]] | head -80` — скинь вывод, посмотрим вместе.
2. **Решение по E2E**: bash-harness (Problem 2) или реальный PoC с opencode/qwen CLI?
3. **Статус [[STORY-87]]**: если скрипт реально работает на живых данных — можно переводить в Review? Или сначала допилить problems 3-6?

---

## Текущий статус ветки

```
dc19f9b (HEAD, prompts) merge: ACT/WRAP + integration tests
├── cc24052 [[STORY-87]]: session_bootstrap.sh ACT/WRAP/RVC fixes
├── f86fe06 integration test suite (59 workflow tests)
└── [diverged] origin/prompts = cc24052 (behind by dc19f9b + f86fe06 origin)
```

origin/prompts отстаёт на 2 коммита. Пушь после того как решим проблемы.
