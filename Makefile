.PHONY: install dev-install lint typecheck test eval web run server mcp docker-build clean

install:
	pip install -e .

dev-install:
	pip install -e ".[dev]"

lint:
	ruff check sre_triage_agent server eval tests

format:
	ruff format sre_triage_agent server eval tests

typecheck:
	mypy sre_triage_agent server

test:
	pytest

eval-offline:
	python3 -m eval.run_evals --mode offline

eval-adk:
	adk eval sre_triage_agent eval/sre_triage.evalset.json --config_file_path eval/test_config.json

web:
	adk web .

run:
	adk run sre_triage_agent

server:
	uvicorn server.app:app --host 0.0.0.0 --port $${PORT:-8080} --reload

mcp:
	python3 -m sre_triage_agent.mcp_server.ops_mcp_server

docker-build:
	docker build -t sre-triage-agent:latest .

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache build dist *.egg-info
