#!/usr/bin/env bash

run() {
    echo $1
    eval $1 || exit 1
}

run "cd /output"
run "pip install -r package.txt || true"    # ignore any errors because so did CodaMOSA
run "pip install /eval/coverup"
run "pip install -r /eval/coverup/test-modules.txt"

if [ -r missing-modules.txt ]; then
    run "pip install -r missing-modules.txt"
fi
