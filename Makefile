.PHONY: setup dev test smoke evidence scan
setup:
	python3 -m venv .venv
	.venv/bin/python -m pip install -r requirements.lock
	cd apps/web && npm ci && npm run build
dev:
	.venv/bin/python -m uvicorn services.api.main:app --host 127.0.0.1 --port 8765 --no-access-log
test:
	.venv/bin/python -m pytest --junitxml=evidence/python-tests.xml -q
	cd apps/web && npm test > ../../evidence/npm-tests.tap && npm run build
smoke:
	.venv/bin/python scripts/smoke.py
	.venv/bin/python scripts/face_smoke.py
evidence:
	.venv/bin/python scripts/evidence.py
	.venv/bin/python scripts/verify_evidence.py
scan:
	.venv/bin/python scripts/privacy_scan.py
