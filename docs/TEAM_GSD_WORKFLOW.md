# Team GSD Workflow

Этот документ фиксирует командный workflow для GSD, когда два человека могут вести
разные задачи параллельно.

## Базовые правила

Фаза - это логически самостоятельный deliverable.

- Если две задачи дают две самостоятельные ценности, заводим две integer-фазы:
  `N` и `N+1`.
- Если две задачи являются частями одной цели, заводим одну фазу с несколькими
  `PLAN.md` внутри.
- Decimal-фазы (`N.1`, `N.2`) используем только для вставок между уже
  существующими фазами: urgent work, gap closure, polish, regression fix.
- Номер фазы означает логический порядок в roadmap, а не обязательный порядок
  физического выполнения.

## Как определяем номера фаз

1. Если одна задача является prerequisite для другой, prerequisite получает
   меньший номер.
2. Если задачи независимы, раньше ставим ту, которая снижает больший риск,
   разблокирует больше будущей работы или вероятнее изменит архитектурные
   решения.
3. Если задача обнаружена после планирования и должна быть выполнена между уже
   существующими фазами, используем `$gsd-insert-phase` и decimal-номер.
4. Не используем decimal-фазу только потому, что работу делает второй человек.

## Роли

- Planning Owner - на короткое время заводит общую структуру фаз и фиксирует
  договоренности.
- Phase Owner - отвечает за конкретную фазу и ее phase-local артефакты.
- Integration Owner - приводит общую project memory в порядок после merge.

В маленькой команде один человек может совмещать несколько ролей, но в каждый
момент должно быть понятно, кто владеет общей памятью.

## Общий workflow

### 1. Planning Owner заводит общий план

Planning Owner стартует от актуального `main` и добавляет обе фазы:

```bash
git checkout main
git pull

$gsd-add-phase "Task A ..."
$gsd-add-phase "Task B ..."
```

Если работа вставляется после уже существующей фазы:

```bash
$gsd-insert-phase 12 "Urgent compatibility fix ..."
```

В roadmap/state фиксируем:

- phase number;
- phase owner;
- можно ли делать параллельно;
- зависимости между фазами;
- ожидаемые зоны кода, где возможны конфликты.

Этот planning commit быстро вливаем в `main`, чтобы оба участника стартовали от
одной версии project memory.

### 2. Каждый владелец стартует от обновленного main

Каждый Phase Owner создает свою branch или worktree:

```bash
git checkout main
git pull
git checkout -b gsd/phase-N-task-a
```

Для второй задачи:

```bash
git checkout main
git pull
git checkout -b gsd/phase-Nplus1-task-b
```

Для более сильной изоляции можно использовать `$gsd-new-workspace`, но дефолт
для команды из двух человек - отдельные branches или worktrees.

### 3. Каждый ведет только свою фазу

Владелец Phase `N` выполняет цикл только для Phase `N`:

```bash
$gsd-discuss-phase N
$gsd-plan-phase N
$gsd-execute-phase N
$gsd-verify-work N
```

Владелец Phase `N+1` аналогично:

```bash
$gsd-discuss-phase N+1
$gsd-plan-phase N+1
$gsd-execute-phase N+1
$gsd-verify-work N+1
```

Phase-local артефакты принадлежат владельцу фазы:

```text
.planning/phases/N-*/*
.planning/phases/Nplus1-*/*
```

## Правило для общих артефактов

Общие файлы не мержим вслепую из двух рабочих веток:

```text
.planning/STATE.md
.planning/ROADMAP.md
.planning/REQUIREMENTS.md
.planning/PROJECT.md
```

`STATE.md` в рабочей ветке считаем локальным курсором исполнителя. Он может
говорить "сейчас Phase N" у одного человека и "сейчас Phase N+1" у другого.
Обе версии не являются одновременно общей истиной проекта.

Финальная версия общих артефактов на `main` должна быть собрана осознанно
Integration Owner'ом.

## PR и review

Если ревьюерам нужен только код, перед PR используем:

```bash
$gsd-pr-branch main
```

Это позволяет убрать `.planning`-шум из code review.

Если хотим полный GSD shipping loop:

```bash
$gsd-ship
```

В PR указываем:

- phase number;
- что сделано;
- какие проверки прошли;
- есть ли отдельные planning artifacts, которые нужно перенести или сохранить.

## Merge порядок

- Если фазы независимы, мержим в любом порядке после CI и review.
- Если `N+1` зависит от `N`, сначала мержим `N`.
- После merge `N` владелец `N+1` обновляется от `main`, решает конфликты и
  повторяет verification при необходимости.

## Integration sync

После каждого merge Integration Owner делает небольшой planning-sync commit.

В нем обновляются:

- `ROADMAP.md` - статус фазы и completion;
- `REQUIREMENTS.md` - traceability;
- `PROJECT.md` - validated decisions/current state, если решение важно;
- `STATE.md` - общий актуальный статус проекта.

Смысл sync: `main` содержит собранную общую картину, а не случайный `STATE.md`
последней замерженной ветки.

## Definition of Done для фазы

Фаза считается завершенной, когда:

- код влит или готов к merge;
- `$gsd-verify-work N` пройден или gaps явно заведены;
- phase-local `SUMMARY.md` и `VERIFICATION.md` сохранены;
- общий planning sync сделан или явно запланирован;
- следующий владелец понимает, от какого состояния продолжать.

## Короткая формула

Один общий planning старт -> две phase branches -> каждый ведет свою фазу ->
чистые PR -> Integration Owner синхронизирует общую память.
