.PHONY: help up down logs build shell test lint format baseline defense-none defense-basic defense-strict clean llama-guard-up llama-guard-down prompt-guard-up prompt-guard-down

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

LLAMA_GUARD_GGUF ?= Llama-Guard-3-1B.Q4_K_M.gguf
LLAMA_GUARD_GGUF_URL ?= https://huggingface.co/QuantFactory/Llama-Guard-3-1B-GGUF/resolve/main/$(LLAMA_GUARD_GGUF)

llama-guard-up: ## Tải GGUF Llama Guard 3 1B (~1 GB) và chạy llama.cpp server local (CPU)
	mkdir -p data/models
	test -s data/models/$(LLAMA_GUARD_GGUF) || curl -L --fail -C - -o data/models/$(LLAMA_GUARD_GGUF) $(LLAMA_GUARD_GGUF_URL)
	LLAMA_GUARD_GGUF=$(LLAMA_GUARD_GGUF) docker compose --profile llama-guard up -d llama-guard
	@echo "Chờ model load..."; for i in $$(seq 1 60); do curl -fsS http://localhost:8088/health >/dev/null 2>&1 && echo "Llama Guard sẵn sàng tại http://localhost:8088/v1" && exit 0; sleep 2; done; echo "Chưa sẵn sàng — xem: docker compose logs llama-guard"; exit 1

llama-guard-down: ## Dừng Llama Guard local
	docker compose --profile llama-guard stop llama-guard

prompt-guard-up: ## Build + chạy Prompt Guard 2 86M local (CPU). Lần đầu cần HF_TOKEN đã được Meta duyệt
	@test -f data/models/Llama-Prompt-Guard-2-86M/model.safetensors || test -n "$$HF_TOKEN" || grep -qE '^[[:space:]]*HF_TOKEN[[:space:]]*=[[:space:]]*.?hf_' .env || { echo "Thiếu HF_TOKEN: xin quyền https://huggingface.co/meta-llama/Llama-Prompt-Guard-2-86M rồi đặt HF_TOKEN trong .env"; exit 1; }
	docker compose --profile prompt-guard up -d --build prompt-guard
	@echo "Chờ tải/load model..."; for i in $$(seq 1 900); do s=$$(curl -fsS http://localhost:8089/health 2>/dev/null); case "$$s" in *'"status":"ready"'*) echo "Prompt Guard sẵn sàng tại http://localhost:8089"; exit 0;; *'"status":"error"'*) echo "$$s"; exit 1;; esac; sleep 2; done; echo "Chưa sẵn sàng — xem: docker compose logs prompt-guard"; exit 1

prompt-guard-down: ## Dừng Prompt Guard local
	docker compose --profile prompt-guard stop prompt-guard
