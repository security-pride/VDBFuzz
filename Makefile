SHELL := /bin/bash

PYTHON ?= python3
COMPOSE := ./scripts/compose.sh
ENV_FILE := .env

-include $(ENV_FILE)
export

.PHONY: env install install-capture install-full check-docker compose-config vdb-up vdb-down vdb-wait smoke-weaviate smoke-qdrant smoke-milvus smoke-all

env:
	@if [[ ! -f $(ENV_FILE) ]]; then cp .env.example $(ENV_FILE); fi
	@echo "env ready: $(ENV_FILE)"

install:
	@$(PYTHON) -m pip install -e .

install-capture:
	@$(PYTHON) -m pip install -e ".[capture]"

install-full:
	@$(PYTHON) -m pip install -e ".[capture,weaviate]"

check-docker:
	@docker --version
	@docker-compose --version

compose-config: env
	@$(COMPOSE) config >/dev/null
	@echo "compose config OK"

vdb-up: env
	@./scripts/up_vdbs.sh

vdb-down:
	@./scripts/down_vdbs.sh

vdb-wait:
	@$(PYTHON) scripts/wait_for_vdbs.py

smoke-weaviate:
	@$(PYTHON) -m vdbfuzz.run -i templates -o output/weaviate -t http://127.0.0.1:$(WEAVIATE_HTTP_PORT) -vdb weaviate -n 2 -l 0 --reset-history

smoke-qdrant:
	@$(PYTHON) -m vdbfuzz.run -i templates -o output/qdrant -t http://127.0.0.1:$(QDRANT_HTTP_PORT) -vdb qdrant -n 2 -l 0 --reset-history

smoke-milvus:
	@$(PYTHON) -m vdbfuzz.run -i templates -o output/milvus -t http://127.0.0.1:$(MILVUS_HTTP_PORT) -vdb milvus -n 2 -l 0 --reset-history

smoke-all: smoke-qdrant smoke-weaviate smoke-milvus
