pip install pytest-repeat || exit $?

PYTEST_ARGS=" --count 10"
SLIPCOVER_ARGS=""
COVERUP_ARGS="--model gpt-4o-2024-05-13 --isolate-tests --prompt-family gpt-v1"
PYTEST_FINAL_ARGS=" --cleanslate"
