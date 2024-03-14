SHELL=/bin/bash

UNAME := $(shell uname)

ROOT=$(abspath $(MAKEFILE_PATH)/../..)
POETRY_RUN?=poetry run -C $(ROOT)
# path to the current makefile
MAKEFILE_PATH := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))
# path to the kompile binary of this distribuition
KOMPILE=$(POETRY_RUN) pyk kompile
# ditto for krun
KRUN=$(POETRY_RUN) pyk run
# and kprove
KPROVE=$(POETRY_RUN) pyk prove
# path relative to current definition of test programs
TESTDIR?=tests
# path to put -kompiled directory in
DEFDIR?=.
# path to kompile output directory
KOMPILED_DIR=$(DEFDIR)/$(notdir $(DEF))-kompiled
# all tests in test directory with matching file extension
RUN_TESTS?=$(wildcard $(TESTDIR)/*.$(EXT))
PROOF_TESTS?=$(wildcard $(TESTDIR)/*-spec.k) $(wildcard $(TESTDIR)/*-spec.md)
# default KOMPILE_BACKEND
KOMPILE_BACKEND?=llvm
# check if .k file exists, if not, check if .md file exists
# if not, default to .k to give error message
SOURCE_EXT?=$(or $(and $(wildcard $(DEF).k), k), $(or $(and $(wildcard $(DEF).md), md), k))

VERBOSITY?=

ifeq ($(UNAME), Darwin)
	KOMPILE_FLAGS+=--no-haskell-binary
endif

KOMPILE_FLAGS+=--type-inference-mode checked $(VERBOSITY)
KRUN_FLAGS+=
KPROVE_FLAGS+=--type-inference-mode checked --failure-info $(VERBOSITY)

CHECK?=| diff -
REMOVE_PATHS=| sed 's!'`pwd`'/\(\./\)\{0,2\}!!g'
CONSIDER_ERRORS=2>&1

PIPEFAIL?=set -o pipefail;
# null by default, add CONSIDER_PROVER_ERRORS=2>&1 to the local Makefile to test kprove output
#CONSIDER_PROVER_ERRORS=

.PHONY: kompile all clean update-results proofs

# run all tests
all: kompile krun proofs

# run only kompile
kompile: $(KOMPILED_DIR)/timestamp

$(KOMPILED_DIR)/timestamp: $(DEF).$(SOURCE_EXT)
	$(KOMPILE) $(KOMPILE_FLAGS) --backend $(KOMPILE_BACKEND) $(DEBUG) $< --output-definition $(KOMPILED_DIR)

krun: $(RUN_TESTS)

proofs: $(PROOF_TESTS)

# run all tests and regenerate output files
update-results: all
update-results: CHECK=>

# run a single test. older versions of make run pattern rules in order, so
# if some programs should be run with different options their rule should be
# specified in the makefile prior to including ktest.mak.
%.$(EXT): kompile
	$(PIPEFAIL) (cat $@.in 2>/dev/null || true) | $(KRUN) $@ $(KRUN_FLAGS) $(DEBUG) --definition $(KOMPILED_DIR) $(CHECK) $@.out

%-spec.k %-spec.md: kompile
	$(KPROVE) $@ $(KPROVE_FLAGS) $(DEBUG) --definition $(KOMPILED_DIR) $(CONSIDER_PROVER_ERRORS) $(REMOVE_PATHS) $(CHECK) $@.out

clean:
	rm -rf $(KOMPILED_DIR) .depend-tmp .depend .kompile-* .krun-* .kprove-* kore-exec.tar.gz
ifeq ($(KOMPILE_BACKEND),kore)
	rm -f $(DEF).kore
endif

ifneq ($(MAKECMDGOALS),clean)
-include .depend
endif
