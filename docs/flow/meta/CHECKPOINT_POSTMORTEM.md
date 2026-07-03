---
type: meta
tags: [workflow]
domain: workflow_meta
domain_tags: []
---

# CHECKPOINT_POSTMORTEM

> 2026-06-16

Path bug в трёх python скриптах. Три неправильных `.parent`. Не проверил path за 30 сек в терминале — кодил вслепую.

Исправление: `assert BOOTSTRAP.exists()` при старте. Искать repo root по `pyproject.toml`, не угадывать.

───

## Реальные проблемы текущего флоw

### 1. Промпт — 385 строк, HARD STOP в конце
SYNC фаза: агент получает всё сразу (issue 79 строк + specs + decisions + gotchas + code state).
Инструкция "не делай ничего" — на 385-й строке. Модель уже думает об имплементации.

**Решение:** PHASE инструкция в НАЧАЛЕ промпта, контекст после.

### 2. Нет логов ошибок
stderr пустой (rvc в PATH). Когда rvc нет — warning теряется в файле.
Нет классификации, нет записи в vault.

**Решение:** `pult` собирает stderr, классифицирует каждую строку, пишет JSON в vault.

### 3. Тесты в вакууме
103 теста на temp vault. Не тестируют реальный vault + rvc + git state.

**Решение:** integration fixture на реальном vault (`VAULT=adlai-vault`, не temp).

### 4. Нет пульта
Есть bootstrap (промпт), rvc (issues), conductor (L4). Нет одного места для запуска SYNC→ENGAGE→ACT→WRAP.

**Решение:** `pult run STORY-XX` — phase runner с логированием.

### 5. Артефакты только для SYNC
ENGAGE/ACT/WRAP — агент пишет вручную. Нет шаблона, нет валидации.

### 6. WRAP не запрещает код
Prompt: "verify git status, git commit". Нет "Do NOT write code". Агент может менять файлы в WRAP.

───

## Что сделано (реально)

- WORKFLOW_PULT.md — архитектура пульта (draft)
- WORKFLOW_DOMAIN.md — добавлена ссылка на Pult
- [[STORY-87]].md — добавлена секция Next: Pult
- CHECKPOINT.md — честная оценка (6 проблем)
- 103 интеграционных теста — работают, но в вакууме

##Что НЕ сделано

- pult.py — нет
- 路径 resolver — нет
- E2E тест на реальном vault — нет
- Промпт не переписан

## Следующий шаг

`backend/app/services/paths.py` — один файл, правильные пути, проверка.
Потом `pult.py` — вызывает bootstrap, собирает stderr, пишет лог.
Потом запуск на реальном vault и РЕАЛЬНЫЕ ошибки.
