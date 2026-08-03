# YouTube Agent — thin ergonomics over the venv. Postgres is the docker-compose service (port 5433).
PY := ./.venv/bin/python
export POSTGRES_HOST ?= localhost
export POSTGRES_PORT ?= 5433

.PHONY: health migrate pg

health:   ## Run the verify suite — "do the codes work" (exit 0 pass, 1 fail, 3 env)
	$(PY) -m scripts.health

pg:       ## Start the Postgres service the DB verifies need
	docker compose up -d postgres

migrate:  ## Apply pending DB migrations
	$(PY) -c "from ytagent.config import load_settings; from ytagent.migrations.runner import run_migrations; print('applied:', run_migrations(load_settings()))"
