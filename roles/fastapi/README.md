# Роль `fastapi`

Управляет развёртыванием контейнера FastAPI backend в общей Docker-сети `infradrive_net`.

## Особенности
* Код и Docker-образ backend разрабатываются отдельно.
* Если переменная `fastapi_image` не задана или образ отсутствует локально (при `fastapi_pull_image: false`), роль завершается с понятной ошибкой и инструкцией.
* Healthcheck отключён по умолчанию (`fastapi_healthcheck_enabled: false`) до согласования реального HTTP endpoint с разработчиком backend.
* Внешний порт не публикуется по умолчанию (`fastapi_publish_port: false`).
