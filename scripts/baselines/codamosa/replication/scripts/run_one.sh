#!/bin/bash
# This file lets you run one instance of codamosa, etc.

# pynguin-runner is CodaMosa's original pynguin runner;
# updating-pynguin-runner automatically updates CodaMosa from /codamosa, if present;
#   This was used for developing CodaMosa (gpt4).
# gpt4-coda-runner has the "final" version of CodaMosa (gpt4) preinstalled.

#OPTS_AND_IMAGE="pynguin-runner"
#OPTS_AND_IMAGE="-v ${HOME}/codamosa:/codamosa:ro updating-pynguin-runner"
OPTS_AND_IMAGE="gpt4-coda-runner"

SCRIPT_DIR="$( cd -- "$( dirname -- "${BASH_SOURCE[0]:-$0}"; )" &> /dev/null && pwd 2> /dev/null; )";

if [ "$#" -lt 5 ]; then
	echo "Usage: $0 module-name out-dir argfile authkeyfile searchtime"
	exit 1
fi
MOD=$1
OUT_DIR=$2
ARGFILE=$3
ARGS=`cat $ARGFILE`
SEARCH_TIME=$4
PLAY_OPTION=$5 #"--auth" for querying codex with auth key or "--replay" with existing codex generations
PLAY_KEY=$6 # auth key file or codex generations file

# Use main codamosa folder (same as testweaver)
# From scripts/baselines/codamosa/replication/scripts, go to root: ../../../../ (4 levels up)
# Then to codamosa/replication/test-apps
TEST_APPS_DIR="$SCRIPT_DIR/../../../../codamosa/replication/test-apps"

if [[ ! -d "$TEST_APPS_DIR" ]]; then
	echo "It seems that the directory test-apps does not exist at $TEST_APPS_DIR. Please ensure codamosa submodule is initialized."
	exit 1
fi

grep $1 "$TEST_APPS_DIR/good_modules.csv" |
while IFS=, read  -r TEST_DIR TEST_MOD
do
	TEST_DIR="$TEST_APPS_DIR/$TEST_DIR"
	mkdir -p $OUT_DIR
	if [ $PLAY_OPTION = "--auth" ]; then
		PLAY_CONFIG="--authorization-key $(cat $PLAY_KEY)"
	elif [ $PLAY_OPTION = "--replay" ]; then
		PLAY_CONFIG="--replay-generation-from-file $PLAY_KEY"
	else
		echo "Invalid option $PLAY_OPTION"
		exit 1
	fi
CMD="docker run --rm -v ${TEST_DIR}:/input:ro -v ${OUT_DIR}:/output -v ${TEST_DIR}:/package:ro ${OPTS_AND_IMAGE} --assertion-generation NONE --project_path /input --module-name ${TEST_MOD} --output-path /output --maximum_search_time $SEARCH_TIME --output_variables TargetModule,Coverage,BranchCoverage,LineCoverage,ParsedStatements,UninterpStatements,ParsableStatements,LLMCalls,LLMQueryTime,LLMStageSavedTests,LLMStageSavedMutants,LLMNeededExpansion,LLMNeededUninterpreted,LLMNeededUninterpretedCallsOnly,RandomSeed,AccessibleObjectsUnderTest,CodeObjects,CoverageTimeline --report-dir /output --coverage_metrics BRANCH,LINE $ARGS $PLAY_CONFIG -v"
	$CMD
	cat $OUT_DIR/statistics.csv
done
