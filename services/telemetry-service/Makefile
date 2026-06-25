install-deps:
	pip install -r requirements.txt

gunicorn-telemetry-app:
	export FLASK_APP=app.telemetry.app:app && flask db upgrade
	gunicorn \
		--bind=0.0.0.0:$(GUNICORN_TELEMETRY_PORT) \
		--timeout=$(GUNICORN_TELEMETRY_TIMEOUT) \
		--workers=$(GUNICORN_TELEMETRY_WORKERS) \
		--worker-class=gthread \
		--threads=$(GUNICORN_TELEMETRY_THREADS) \
		app.telemetry.app:app


GUNICORN_TELEMETRY_WORKERS ?= 3
GUNICORN_TELEMETRY_TIMEOUT ?= 300
GUNICORN_TELEMETRY_PORT ?= 8004
GUNICORN_TELEMETRY_THREADS ?= 8
