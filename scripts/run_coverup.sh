#!/usr/bin/env bash

CONFIG=$1; shift
SRC=$1; shift
PKG=$1; shift
FILES=$@

OWNER=`stat -c %u /output`:`stat -c %g /output`

run() {
    echo $1
    eval $1 || exit 1
}

# load/run base settings (such as OpenAI key)
if [ -e /eval/config/common.sh ]; then
    source /eval/config/common.sh
fi

# load/run configuration-specific settings
if [ -e /eval/config/$CONFIG.sh ]; then
    source /eval/config/$CONFIG.sh
fi

run "cd /output"

if [ -e /package/$SRC/package2.txt ]; then
    run "pip install -r /package/$SRC/package2.txt"
else
    # install CodaMOSA-computed package dependencies;
    # requirementslib has a variable named _fragment_dict and pydantic, if also installed,
    # causes load failures (saying it should be renamed to fragment_dict).
    if ! [ -e package.txt ]; then
        run "cp /package/$SRC/package.txt ."
        run "sed -i '/requirementslib/d' package.txt"
        run "chown $OWNER package.txt"
    fi
    run "pip install -r package.txt || true"    # ignore any errors because so did CodaMOSA
fi

# (re)install modules previously found missing
if [ -r missing-modules.txt ]; then
    run "pip install -r missing-modules.txt"
fi

# install CoverUp and common test modules
run "pip install /eval/coverup"
if ! [ -e /package/$SRC/package2.txt ]; then
    run "pip install -r /eval/coverup/test-modules.txt"
fi

PYTEST_ARGS+=" --rootdir . -c /dev/null" # ignore configuration which would deviate from expected defaults

SLIPCOVER_ARGS+=" --source $SRC/$PKG --branch --json"
COVERUP_ARGS+=" --source-dir $SRC/$PKG --tests-dir coverup-tests --save-coverage-to coverage --pytest-args \"$PYTEST_ARGS\""

[ -d coverup-tests ] || mkdir coverup-tests
[ -d coverage ] || mkdir coverage

# set Python path so the package can be 'import'ed
export PYTHONPATH=$SRC

# run coverup three times: once to get stated, then another to help fill any gaps
for RUN in 1 2 3; do
    if ! [ -e coverup-ckpt-$RUN.json ]; then
        # run CoverUp on it
        run "coverup $COVERUP_ARGS --log-file coverup-log-$RUN --checkpoint coverup-ckpt.json $FILES"
        run "chown -R $OWNER coverup-log* *.json coverup-tests"
        if [ -e missing-modules.txt ]; then
            run "chown $OWNER missing-modules.txt"
        fi
        run "mv coverup-ckpt.json coverup-ckpt-$RUN.json"
    fi
done

# measure final coverage
if ! [ -e /output/final.json ]; then
    # rc==5: no tests ran (maybe none generated)
    run "python3 -m slipcover $SLIPCOVER_ARGS --out final.json -m pytest -qq --disable-warnings $PYTEST_ARGS $PYTEST_FINAL_ARGS coverup-tests || [ \$? == 5 ]"
    run "chown $OWNER final.json"
fi

run "chown -R $OWNER coverage"
