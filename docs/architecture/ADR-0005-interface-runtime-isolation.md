# ADR-0005: Interface Runtime Isolation

## Status
Accepted

## Context
`ONX` выполняет `site-to-site` apply через SSH и должна оставаться устойчивой при частичных отказах.

Ранее интерфейсы поднимались напрямую из orchestration кода через `awg-quick`.
Это связывало lifecycle интерфейсов с lifecycle API/worker процесса и усложняло восстановление.

Дополнительно, конфиги содержат `quick`-директивы (`Table`, `PostUp`, `PostDown`), которые корректно
обрабатываются именно `awg-quick`, но не `awg setconf`.

## Decision
Вводим изолированный runtime слой на ноде:

- template unit: `onx-link@.service`
- runner script: `/usr/local/lib/onx/onx-link-runner`
- `ONX` управляет интерфейсами только через `systemctl` (`start/restart/stop`) для `onx-link@<iface>.service`

`onx-link-runner` использует `awg-quick` и тем самым сохраняет корректную обработку quick-специфичных строк.

## Consequences
Плюсы:

- отказ API/UI/worker не должен автоматически ронять уже поднятые интерфейсы
- lifecycle интерфейсов вынесен в systemd и управляется отдельно
- проще операционно: можно проверять/перезапускать интерфейс через стандартный `systemctl`

Минусы:

- добавляется слой runtime assets (unit + script), который нужно устанавливать и обновлять на нодах
- при смене шаблонов runtime требуется `daemon-reload` на нодах

## Notes
Следующий шаг: добавить versioning runtime assets и явную проверку drift между желаемой и установленной версией.
