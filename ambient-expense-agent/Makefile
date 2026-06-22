.PHONY: install playground test lint generate-traces grade

install:
	uv sync --all-extras

playground:
	uv run uvicorn expense_agent.agent_runtime_app:app --host 127.0.0.1 --port 8080 --reload

test:
	uv run pytest

lint:
	agents-cli lint

generate-traces:
	uv run python tests/eval/generate_traces.py

grade:
	uv run python tests/eval/run_grade.py

