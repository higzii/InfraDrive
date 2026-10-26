# Роль `storage`

Развёртывает три логически равноправные storage-ноды (`storage-1`, `storage-2`, `storage-3`) в Docker.

## Режимы работы (`storage_mode`)
* `storage_mode: "service"` (по умолчанию) — промышленный режим. Требует явно заданного образа реального storage-сервиса (`storage_image` / `INFRADRIVE_STORAGE_IMAGE`). Запрещает неявный запуск на контейнерах-заглушках.
* `storage_mode: "stub"` — явный инфраструктурный тестовый режим. Запускает контейнеры `debian:trixie-slim` с меткой `infradrive.storage.mode=stub` исключительно для проверки создания томов `/data`, лимитов ресурсов и сетевой связности.

## Особенности и границы ответственности
* Для каждой ноды создаётся отдельный persistent volume (`infradrive_storage_1_data`, `infradrive_storage_2_data`, `infradrive_storage_3_data`), монтируемый в `/data`.
* Все ноды подключаются к общей сети `infradrive_net`.
* Репликация `RF=2` выполняется кодом backend, а не средствами Ansible.
