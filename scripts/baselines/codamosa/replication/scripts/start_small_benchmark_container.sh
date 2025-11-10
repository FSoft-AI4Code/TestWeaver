#!/bin/bash
# Use main codamosa folder (same as testweaver)
# From scripts/baselines/codamosa/replication/scripts, go to root: ../../../../ (4 levels up)
# Then to codamosa/replication/test-apps
SCRIPT_DIR="$( cd -- "$( dirname -- "${BASH_SOURCE[0]:-$0}"; )" &> /dev/null && pwd 2> /dev/null; )";
TEST_APPS_DIR="$SCRIPT_DIR/../../../../codamosa/replication/test-apps"
mkdir -p "${TEST_APPS_DIR}"
docker run -v "${TEST_APPS_DIR}:/home/codamosa/test-apps" -it --name codamosa-benchmarks-container benchmarks-image  /bin/bash /home/codamosa/scripts/setup_only_necessary_test_apps.sh
