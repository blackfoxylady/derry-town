# Технические источники

Технические решения сверялись с первичной документацией. География новой версии не исследовалась заново: сохранена реконструкция исходного проекта.

- Django: миграции — https://docs.djangoproject.com/en/5.2/topics/migrations/
- Django: поддерживаемые версии — https://www.djangoproject.com/download/
- Django: подготовка к эксплуатации — https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/
- Docker Compose: ожидание готовности зависимостей — https://docs.docker.com/compose/how-tos/startup-order/
- PostgreSQL: поддерживаемые версии и обновления — https://www.postgresql.org/support/versioning/
- Python 3.12.14 — https://www.python.org/downloads/release/python-31214/

Версии приложения зафиксированы в requirements.in и requirements.lock, контейнеров — в Dockerfile/compose.yaml. Список источников карты хранится отдельно в Source/Evidence и отображается в интерфейсе.
