SLIPCOVER_ARGS=""
COVERUP_ARGS="--model deepseek-v3-0324 --max-attempts 3 --isolate-tests --prompt-family gpt-v2"
COVERUP_ARGS+=" --install-missing-modules --write-requirements-to missing-modules.txt"
PYTEST_FINAL_ARGS=" --cleanslate"
 
COVERUP_ARGS+=" --repeat-tests 5" 