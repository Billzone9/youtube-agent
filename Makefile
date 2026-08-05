# YouTube Agent — thin ergonomics over the venv. Postgres is the docker-compose service (port 5433).
# PY is overridable so CI (which has no ./.venv) can run the SAME targets with `make PY=python ci`.
PY ?= ./.venv/bin/python
export POSTGRES_HOST ?= localhost
export POSTGRES_PORT ?= 5433

.PHONY: health health-live migrate pg seed ci

health:   ## Run the verify suite — "do the codes work" (exit 0 pass, 1 fail, 3 env). NO spend.
	$(PY) -m scripts.health

health-live: ## health + the live vision CALIBRATION (spends ~£0.05 of Anthropic). Deliberate, opt-in.
	HEALTH_LIVE=1 $(PY) -m scripts.health

pg:       ## Start the Postgres service the DB verifies need
	docker compose up -d postgres

migrate:  ## Apply pending DB migrations
	$(PY) -c "from ytagent.config import load_settings; from ytagent.migrations.runner import run_migrations; print('applied:', run_migrations(load_settings()))"

seed:     ## Seed the baseline (wildlife channel + platform settings) — the state CI needs to match local
	$(PY) -m ytagent.seed

ci:       ## What CI runs: migrate + seed a known baseline, then the SAME health suite as local
	$(MAKE) migrate && $(MAKE) seed && $(MAKE) health
