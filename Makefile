PYTHON ?= .venv/bin/python

.PHONY: publish test

# Take the current saved runs live: export -> Vercel prod deploy -> re-point alias.
publish:
	$(PYTHON) publish.py

test:
	$(PYTHON) -m pytest -q
