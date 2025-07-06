#!/usr/bin/env bash

# FIXME DRY with run_coverup.sh

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

run "pip install -r /package/$SRC/package2.txt"
# (re)install modules previously found missing
if [ -r missing-modules.txt ]; then
    run "pip install -r missing-modules.txt"
fi

run "pip install /eval/coverup"

# hypothesis slows down loading considerably, and our tests don't use it
run "pip uninstall -y hypothesis"

PYTEST_ARGS=" --rootdir . -c /dev/null" # ignore configuration which would deviate from expected defaults
SLIPCOVER_ARGS+=" --source $SRC/$PKG --branch --json"
PYTEST_FINAL_ARGS="" # delete --cleanslate, as it can't handle test names

DIR=func-coverage
[ -d $DIR ] || mkdir $DIR

# set Python path so the package can be 'import'ed
export PYTHONPATH=$SRC

shopt -s nullglob # allow empty expansion
for FILE in coverup-tests/test_coverup_*.py; do
    # remove [] to remove duplication of parametrized tests
    for TESTFUNC in $(python3 -m pytest -q --collect-only $FILE 2>/dev/null | grep "::" | sed 's/\[.*\]//' | uniq); do
        B=`basename $TESTFUNC`
        OUT=$DIR/$B.json
        if ! [ -e $OUT ]; then
            run "python3 -m slipcover $SLIPCOVER_ARGS --out $OUT -m pytest -qq --disable-warnings $PYTEST_ARGS $PYTEST_FINAL_ARGS $TESTFUNC || [ \$? == 5 ]"
        fi
    done
done
