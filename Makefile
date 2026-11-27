# TUỲ CHỌN, chỉ cho máy có sẵn make. Lệnh chính là `python run.py …` (chạy được cả trên Windows).
# Makefile này chỉ gọi lại run.py, không làm gì thêm.
PY ?= python
run: ; $(PY) run.py
check: ; $(PY) run.py check
eval: ; $(PY) run.py eval
eval-try: ; $(PY) run.py eval --try
score: ; $(PY) run.py score $(RUN)
simulate: ; $(PY) run.py simulate
simulate-try: ; $(PY) run.py simulate --try

# Lệnh cho ứng dụng web tổng hợp & kiểm tra lịch đào tạo (FastAPI + React/Vite)
web-init: ; $(PY) -m alembic upgrade head
web-seed: ; $(PY) -m backend.cli seed-synthetic
web-test: ; $(PY) -m pytest -v && $(PY) -m ruff check backend codebase tests
web-dev: ; powershell -ExecutionPolicy Bypass -File scripts/dev.ps1

.PHONY: run check eval eval-try score simulate simulate-try web-init web-seed web-test web-dev
