.PHONY: default all clean build install          \
        poetry-install                           \
        test test-unit test-integration test-pyk \
        format isort autoflake black             \
        check check-isort check-autoflake check-black check-flake8 check-mypy

default: check test-unit

all: check test

clean:
	rm -rf dist .mypy_cache
	find -type d -name __pycache__ -prune -exec rm -rf {} \;
	$(MAKE) -C pyk-tests clean

build:
	poetry build

install: build
	pip3 install ./dist/*.whl --root=$(DESTDIR) --prefix=$(PREFIX)

poetry-install:
ifndef NO_POETRY_INSTALL
	poetry install
endif

POETRY_RUN := poetry run


# Tests

TEST_ARGS :=

test: test-unit test-integration test-pyk test-kit

test-unit: poetry-install
	$(POETRY_RUN) python -m unittest discover tests --failfast --verbose $(TEST_ARGS)

ifdef TESTS
test-integration: poetry-install $(TESTS)
else
test-integration: poetry-install
	@$(MAKE) --no-print-directory $@ TESTS=$$(poetry run python3 -m integration_tests) NO_POETRY_INSTALL=true
endif

integration_tests.%: poetry-install
	$(POETRY_RUN) python -m unittest $@ $(TEST_ARGS)

test-pyk: poetry-install
	$(POETRY_RUN) $(MAKE) -C pyk-tests

test-kit: poetry-install
	$(POETRY_RUN) $(MAKE) -C kit-tests


# Checks and formatting

format: autoflake isort black
check: check-flake8 check-mypy check-autoflake check-isort check-black

check-flake8: poetry-install
	$(POETRY_RUN) flake8 src

check-mypy: poetry-install
	$(POETRY_RUN) mypy src

autoflake: poetry-install
	$(POETRY_RUN) autoflake --quiet --in-place src

check-autoflake: poetry-install
	$(POETRY_RUN) autoflake --quiet --check src

isort: poetry-install
	$(POETRY_RUN) isort src

check-isort: poetry-install
	$(POETRY_RUN) isort --check src

black: poetry-install
	$(POETRY_RUN) black src

check-black: poetry-install
	$(POETRY_RUN) black --check src
