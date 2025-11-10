# Runs CodaMosa (deepseek) on the "good_modules" benchmark set
# Designed so that various instances can be run in parallel

import csv
from pathlib import Path
import subprocess
import os
from dotenv import load_dotenv

# Load environment variables from .env file (following testweaver pattern)
load_dotenv()

# Get API key and base URL from environment variables (following testweaver pattern)
api_key = os.getenv('OPENAI_API_KEY')
base_url = os.getenv('OPENAI_BASE_URL')

if not api_key:
    raise ValueError("OPENAI_API_KEY environment variable is not set. Please set it in .env file or environment.")

# Create a temporary key file for the script to use
openai_key = Path(os.environ.get('HOME', '/tmp')) / ".openai-key-tmp"
with open(openai_key, 'w') as f:
    f.write(api_key)
openai_key.chmod(0o600)  # Make it readable only by owner

# Use main codamosa folder (same as testweaver)
# From scripts/baselines/codamosa/replication, go to root: ../../../
# Then to codamosa/replication/test-apps
test_apps = Path(__file__).parent.parent.parent.parent / "codamosa" / "replication" / "test-apps"
modules_csv = test_apps / "good_modules.csv"
config = "deepseek"
codamosa_tests = Path(f"{config}-coda")
runs=1
max_search_secs=600

modules = list()
with modules_csv.open() as f:
    reader = csv.reader(f)
    for d, m in reader:
        modules.append(m)

codamosa_tests.mkdir(exist_ok=True)

for run in range(runs):
    for m in modules:
        d = codamosa_tests / f"{m}-{run}"
        d = d.resolve()

        try:
            d.mkdir(exist_ok=False)
        except FileExistsError:
            continue

        cmd = f"scripts/run_one.sh {m} {str(d)} config-args/{config} {max_search_secs} --auth {openai_key}"
        print(f"**** {cmd}")
        subprocess.run(cmd, shell=True, check=False)

# Clean up temporary key file
if openai_key.exists():
    openai_key.unlink() 