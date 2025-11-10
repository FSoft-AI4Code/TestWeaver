# CoverUp Replication Package
This artifact accompanies the [FSE'25](https://conf.researchr.org/home/fse-2025) accepted paper

Juan Altmayer Pizzorno and Emery D. Berger. 2025. [CoverUp: Effective High Coverage Test Generation for Python](CoverUp.pdf). <em>Proc. ACM Softw. Eng. 2</em>, FSE, Article FSE128 (July 2025), 23 pages. https://doi.org/10.1145/3729398.

It contains materials used in the evaluation of CoverUp, including modified versions of other packages and experimental results.
If you are only looking to use CoverUp, please see its [repository on GitHub](https://github.com/plasma-umass/coverup) instead.

## License
The [Apache license](LICENSE) applies to all CoverUp materials as well as the author's modifications;
See CodaMosa, Pynguin (on which CodaMosa is based), and MuTAP for their respective licenses.

## Requirements
Python3.10+ and, to run CoverUp or CodaMosa on the CM or PY suites, a Linux system with Docker.
To run MuTAP or evaluate on the MT suite, Python 3.9.
See [requirements.txt](requirements.txt) for Python module requirements.

## Obtaining a Local Copy
This repository includes [submodules](https://git-scm.com/book/en/v2/Git-Tools-Submodules).
When cloning it, you should pass in the `--recurse-submodules` option:
```
    git clone --recurse-submodules git@github.com:plasma-umass/coverup-eval
    cd coverup-eval
```

## Guide to Files and Directories
The main directories are:
- [coverup](coverup): a submodule copy of CoverUp;
- [codamosa](codamosa):
a submodule fork of [CodaMosa](https://github.com/microsoft/codamosa), modified to use OpenAI's chat API.
Also contains original CodaMosa replication data, the CM and PY benchmark suites, and new configuration and experimental results;
- [MuTAP](MuTAP):
a submodule fork of [MuTAP](https://github.com/ExpertiseModel/MuTAP), modified to use OpenAI's chat API.
- [config](config): various CoverUp configurations used in evaluation;
- [docker](docker): Docker image, based on that of CodaMosa, used for evaluating CoverUp;
- [output](output): CoverUp experimental results;
- [scripts](scripts): various small programs used to run CoverUp and extract results;
- [MuTAP-benchmarks](MuTAP-benchmarks):
the MT benchmark suite, extracted from MuTAP and reorganized as modules to facilitate use with CoverUp;
- [MuTAP-results](MuTAP-results):
coverage results from running MuTAP-generated tests;
- [cache](cache): cache directory used by some scripts to speed up execution.

### config
This directory contains configuration shell scripts that provide options for the various CoverUp runs.
For example, the main CoverUp results used `gpt4o-v2`, which selects (a specific version of) the GPT-4o model and uses CoverUp's "v2" prompt.
The fully ablated results used instead the `gpt4o-v2-ablated` configuration, etc.

The script `common.sh` is used with all configurations and is useful, for example, for providing an API key;
`common.EXAMPLE.sh` provides an example.

### scripts
There are various programs in `scripts`:
- `compare.py`: compares coverage results (used in RQ1, RQ2, and RQ5).
It always compares CoverUp results to those of another system, which may be CodaMosa, MuTAP, or CoverUp itself.
Usage examples:
```
python3 scripts/compare.py --to codamosa-gpt4o                 # or codamosa-codex
python3 scripts/compare.py --to coverup-gpt4o-v2-ablated
python3 scripts/compare.py --suite mutap --to mutap-Codex_zero # or mutap-gp4o_zero, etc.
python3 scripts/compare.py --suite 1_0                         # "1_0" is suite PY
```
- `cost.py`: estimates cost of running (used in RQ4).
Usage examples:
```
python3 scripts/cost.py --config gpt4o-v2-ablated
python3 scripts/cost.py --system codamosa --config gpt4o
```
- `time.py`: estimates running time for CoverUp (used in RQ4).
Usage example:
```
python3 scripts/cost.py --config gpt4o-v2-ablated
```
- `sequences.py`: evaluates execution sequences (used in RQ3).
Usage example:
```
python3 scripts/sequences.py --config gpt4o-v2
```
- `eval_coverup.py`: runs CoverUp in a docker container.
Before running this script, load the image from `docker/coverup-runner.tar.bz2` into Docker.
Usage example:
```
python3 scripts/eval_coverup --config my-new-config
```
- `run_coverup.sh`: runs CoverUp in the container when started by `eval_coverup.py`.
- `get_test_coverage.sh`: used by `eval_coverup.py` to measure per-test coverage.

- `function-by-run.py`: computes the test functions that are effective in increasing coverage added per run (used in RQ5).
Usage example:
```
python3 scripts/function-by-run.py gpt4o-v2 gpt4o-v2-no-coverage
```
- `suite-stats.py`: counts the number of functions, lines, and files in one of our benchmark suites.

### `codamosa/replication`
This directory contains the original CodaMosa replication data, as well as other files for CoverUp.

- `codamosa-dataset`: original CodaMosa Codex experimental results, extracted from https://github.com/microsoft/codamosa-dataset;
- `config-args/gpt4o`: contains the CodaMosa configuration for running with GPT-4o;
- `docker-images/gpt4-coda-runner.tar.bz2`: Docker image used to run CodaMosa;
- `docker-images/slipcover-runner.tar.bz2`: Docker image used to run CodaMosa tests, measuring coverage;
- `run_codamosa.py`: script to execute CodaMosa on its "good" modules, a superset of suite CM;
- `eval_codamosa.py`: script to run CodaMosa tests, measuring covege;
- `run_coda_tests.sh`: used by `eval_codamosa.py`;
- `get_1_0_modules.sh`: used to create suite PY;
- `gen_1_0_modules.sh`: used to create suite PY;
- `test-apps`: modules used to benchmark CodaMosa and CoverUp;
- `test-apps/good_modules.csv`: a set of modules used to evaluate CodaMosa;
- `test-apps/cm_modules.csv`: defines suite CM;
- `test-apps/1_0_modules.csv`: defines suite PY;
- `gpt4-coda`: output from running CodaMosa with GPT-4 (not used in the paper);
- `gpt4o-coda`: output from running CodaMosa with GPT-4o (Codamosa (gpt4o));
- `output-codex`: coverage measurements for Codamosa (codex);
- `output-gpt4`: coverage measurements for Codamosa on GPT-4 (not used in the paper);
- `output-gpt4o`: coverage measurements for Codamosa (gpt4o);

## Running CoverUp's Evaluation on a New Configuration
- Set up pip cache (to speed up module installations)
```
    mkdir pip-cache
    sudo chown root:root pip-cache
```

- Load docker image
```
    bunzip2 docker/coverup-runner.tar.bz2
    docker load <docker/coverup-runner.tar
```

- Add any keys needed (from OpenAI or elsewhere) to `config/common.sh` or `your-new-model.sh` below.
`config/common.sh` is always included and is in `.gitignore` to help avoid checking it in by mistake.
```
    vim config/common.sh
```

- Create a new configuration. This will be a new file; see `config/gpt4o-v2.sh` for an example
```
    echo COVERUP_ARGS=\"--model your-new-model\" > config/your-new-model.sh
```

- Run CoverUp on a first benchmark (here, `flutils`) to try it out
```
    python3 scripts/eval_coverup.py --config your-new-model flutils
```

- If things look good, let it run on the others (it will skip any that are already done)
```
    python3 scripts/eval_coverup.py --config your-new-model >coverup-your-new-model.log 2>&1 &
```

## Replicating Results
The steps below outline how to replicate the results in the paper.

> [!NOTE]
> At the time of writing, running CoverUp, CodaMosa, and MuTAP, as described below, is very costly (in the order of thousands of dollars in OpenAI fees).

### Running CoverUp
- enter OpenAI key in `config/common.sh`; see `config/common.EXAMPLE.sh` for an example.
- for each configuration C in `gpt4o-v2`, `gpt4o-v2-ablated`,  ... (see `config/gpt4o-v2*`), execute, replacing C:
  - remove existing output: `rm -rf output/cm.C`
  - run CoverUp: `python3 scripts/eval_coverup.py --config C`
- run CoverUp on suite PY (known as "1_0" in the repository):
  - remove existing output: `rm -rf output/1_0.gpt4o-v2`
  - run CoverUp: `python3 scripts/eval_coverup.py --config gpt4o-v2 --suite 1_0`
- run CoverUp on suite MT (known as "mutap" in the repository):
  - remove existing output: `rm -rf output/mutap.gpt4o-v2`
  - run CoverUp: `python3 scripts/eval_coverup.py --config gpt4o-v2 --suite mutap`

### Running CodaMosa
- execute `source config/common.sh` to load the OpenAI key (from above) as an environment variable
- `pushd codamosa/replication`
- delete previous results: `rm -rf output-* gpt4*-coda`
- run CodaMosa using GPT-4o: `python3 run_codamosa.py`
- measure coverage for CodaMosa (gpt4o): `python3 eval_codamosa.py --codamosa-results gpt4o`
- measure coverage for CodaMosa (codex): `python3 eval_codamosa.py --codamosa-results codex`
- `popd`

### Running MuTAP
- if not already done, execute `source config/common.sh` to load the OpenAI key (from above) as an environment variable
- remove old results: `rm -rf MuTAP-results/*`
- `pushd MuTAP`
- run MuTAP: `bash run.sh`
- measure coverage for MuTAP with Codex: `python3 eval.py --llm Codex --run ../MuTAP-results`
- measure coverage for MuTAP with gpt4o: `python3 eval.py --llm gpt4o --run ../MuTAP-results`
- `popd`

### Extracting Results
- coverage results:
  - for each configuration C in `gpt4o-v2`, `gpt4o-v2-ablated`,  ... (see `config/gpt4o-v2*`), execute, replacing C:
    - `python3 scripts/compare.py --to coverup-C`
  - `python3 scripts/compare.py --to codamosa-gpt4o`
  - `python3 scripts/compare.py --to codamosa-codex`
  - `python3 scripts/compare.py --suite 1_0`
  - for each configuration C in `Codex_few`, `Codex_zero`, `gpt4o_few`, `gpt4o_zero`, execute, replacing C:
    - `python3 scripts/compare.py --suite mutap --to mutap-C`
- cost and time results:
  - `python3 scripts/cost.py --config gpt4o-v2`
  - `python3 scripts/cost.py --config gpt4o-v2-ablated`
  - `python3 scripts/cost.py --system codamosa --config gpt4o`
- contribution of continued chat: `python3 scripts/sequences.py --config gpt4o-v2`
- coverage-increasing test functions per run: `python3 scripts/function-by-run.py gpt4o-v2 gpt4o-v2-no-coverage`
