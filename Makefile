VENV := .venv
PY := $(VENV)/bin/python
PIP := $(VENV)/bin/pip

.PHONY: install run test eval reset

$(VENV)/.installed: requirements.txt
	python3 -m venv $(VENV)
	$(PIP) install -q --upgrade pip
	$(PIP) install -q -r requirements.txt
	touch $(VENV)/.installed

install: $(VENV)/.installed

run: install
	$(PY) -m app.seed
	$(PY) -m uvicorn app.main:app --port 8000

test: install
	$(PY) -m pytest -q

eval: install
	$(PY) -m app.evaluate

reset: install
	rm -rf data
	$(PY) -m app.seed
