.PHONY: help up down logs build shell test lint format baseline defense-none defense-basic defense-strict clean

help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

up:            ## Dựng toàn bộ hệ thống (W1 tiêu chí 1.1: một lệnh)
	docker compose up -d --build

down:          ## Dừng hệ thống
	docker compose down

logs:          ## Xem log target
	docker compose logs -f target

build:         ## Chỉ build lại image
	docker compose build

shell:         ## Vào shell trong container target
	docker compose exec target bash

test:          ## Chạy kiểm thử
	pytest tests/ -v

lint:          ## Kiểm tra lint
	ruff check src/ tests/

format:        ## Định dạng code
	ruff format src/ tests/

baseline:      ## Chạy 5 baseline attack thủ công (W1)
	python scripts/run_baseline.py

defense-none:  ## Chạy target ở baseline, không bật guardrail
	DEFENSE_PROFILE=none docker compose up -d --build --force-recreate target

defense-basic: ## Bật input filter, prompt hardening và canary check
	DEFENSE_PROFILE=basic docker compose up -d --build --force-recreate target

defense-strict: ## Bật toàn bộ guardrail, gồm output filter
	DEFENSE_PROFILE=strict docker compose up -d --build --force-recreate target

clean:         ## Dọn cache
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true
