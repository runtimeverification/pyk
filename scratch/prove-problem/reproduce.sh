#!/bin/sh

set -eux

# install pyk
make -C ../../

# compile the verification module
poetry run pyk kompile imp-verification.k --backend haskell

# watch the proof
poetry run pyk prove my-spec.k
