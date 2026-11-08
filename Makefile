.PHONY: check backend frontend policy
check: backend frontend policy
backend:
	cd backend && uv sync --locked --extra dev
	cd backend && uv run --locked ruff check . ../pdf-worker && uv run --locked ruff format --check . ../pdf-worker
	cd backend && uv run --locked pytest -m 'not integration' --allow-unix-socket --cov=app --cov-report=term-missing
frontend:
	cd frontend && npm ci --ignore-scripts && npm test && npm run build
policy:
	cd backend && uv run --locked python ../scripts/check_repository.py
	cd backend && uv run --locked python ../scripts/test_ci_scope.py
