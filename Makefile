PYTHON ?= python3
.PHONY: install test demo verify counterfactual benchmark api fluss-up fluss-bridge fluss-sql fluss-down
install:
	$(PYTHON) -m pip install -e '.[dev]'
test:
	$(PYTHON) -m pytest -q
demo:
	$(PYTHON) -m causal_lab.cli demo
verify:
	$(PYTHON) -m causal_lab.cli verify
counterfactual:
	$(PYTHON) -m causal_lab.cli counterfactual
benchmark:
	$(PYTHON) -m causal_lab.cli --db .data/bench.sqlite3 benchmark --accounts 1000
api:
	uvicorn causal_lab.api:app --host 127.0.0.1 --port 8000
fluss-up:
	docker compose -f infra/docker-compose.fluss.yml up -d zookeeper coordinator-server tablet-server jobmanager taskmanager
fluss-bridge:
	docker compose -f infra/docker-compose.fluss.yml --profile tools run --build --rm bridge
fluss-sql:
	docker compose -f infra/docker-compose.fluss.yml --profile tools run --rm sql-client
fluss-down:
	docker compose -f infra/docker-compose.fluss.yml down
