# This file is executed by scripts/run_coverup.sh if using the "default" configuration
# "default" configuration
PYTEST_ARGS=""
SLIPCOVER_ARGS=""
COVERUP_ARGS="--model gpt-4-1106-preview --disable-failing --no-isolate-tests --prompt-family gpt-v1"

REPEAT=false
if $REPEAT; then
    pip install pytest-repeat || exit $?
    PYTEST_ARGS+=" --count 5"
fi

