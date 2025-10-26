PYTHON := python3
VENV_DIR := venv
HOOKS_DIR := .githooks

.PHONY: install hooks venv clean lint test deploy docker-up docker-down

install: hooks venv
	@echo "Installing Python dependencies..."
	$(VENV_DIR)/bin/pip install --upgrade pip
	$(VENV_DIR)/bin/pip install -r requirements.txt
	@echo "Installation complete."

hooks:
	@echo "Configuring git hooks..."
	git config core.hooksPath $(HOOKS_DIR)
	chmod +x $(HOOKS_DIR)/*
	@echo "Git hooks enabled."

venv:
	@if [ ! -d "$(VENV_DIR)" ]; then \
		echo "Creating virtual environment..."; \
		$(PYTHON) -m venv $(VENV_DIR); \
	fi

clean:
	rm -rf $(VENV_DIR) .pytest_cache __pycache__

lint:
	$(VENV_DIR)/bin/pip install flake8 >/dev/null 2>&1 || true
	$(VENV_DIR)/bin/flake8 market_data tests

test:
	$(VENV_DIR)/bin/pytest

docker-up:
	docker compose up --build market_data

docker-down:
	docker compose down
