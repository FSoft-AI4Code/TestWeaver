<div align="center">
  
# [ICSE 2026] TestWeaver: Execution-aware, Feedback-driven Regression Testing Generation with Large Language Models 
[![arXiv](https://img.shields.io/badge/arXiv-2508.01255-b31b1b.svg)](https://arxiv.org/abs/2508.01255)

</div>


## Overview

**TestWeaver** is an advanced regression test generation tool that integrates [Large Language Models (LLMs)](https://en.wikipedia.org/wiki/Large_language_model) with lightweight program analysis. Its goal is to generate high-quality test cases that enhance [code coverage](https://en.wikipedia.org/wiki/Code_coverage) while addressing common challenges such as redundant test generation and the *coverage plateau*.

Unlike traditional test generators, **TestWeaver** incrementally builds a test suite by reasoning about program execution. It begins with seed tests and iteratively refines them through feedback-driven guidance informed by execution analysis, slicing, and "closest" test case retrieval.


---

## Key Features

- **Execution-aware feedback**: Uses real execution traces to guide the LLM toward covering uncovered lines.
- **Backward slicing**: Focuses the LLM on only the relevant code for each target line, reducing hallucinations.
- **Closest test retrieval**: Identifies test cases that nearly reach the uncovered line to serve as contextual guidance.
- **Support for multiple LLM providers**: Works with OpenAI, Anthropic, or AWS Bedrock.


---

## 🔧 Setup


### . Install dependencies

```bash
pip install -r requirements.txt
```


---

## 🔐 Configure API Key

You need to set up access to an LLM provider before running TestWeaver.

```bash
echo "OPENAI_API_KEY=sk-your-actual-api-key-here" > .env
echo "OPENAI_BASE_URL=https://api.openai.com/v1" >> .env
```

## 📂 Prepare Dataset for Evaluation

We conduct our evaluation using the **CodaMosa (CM) suite**,  a dataset derived from 35 open-source Python projects.

To download the dataset, run:

```bash
git clone https://github.com/plasma-umass/codamosa.git
```



### 🧪 Running TestWeaver on a Specific Subproject

You can run **TestWeaver** on a specific subproject within a larger repository.  
This will launch an experimental run.

The results will be saved under the `output/cm/...` directory.

```bash
cd scripts/
export PYTHONPATH=$(pwd)
export sample_id=21  # The id of your chosen Codamosa module, e.g. 21 is corresponding to 'tqdm' module   
python testweaver.py --test-index $sample_id
```
### 🧪 Running TestWeaver Ablation Study

To evaluate the impact of different components, you can run TestWeaver in an ablation study mode.
This command will execute five experimental configurations:

1. With slicing  
2. Without slicing  
3. Without execution-in-line  
4. Without closest-test retrieval  
5. Full TestWeaver pipeline

The results will be saved under the `output/cm/...` directory.

```bash
cd scripts/
export PYTHONPATH=$(pwd)
export sample_id=21  # The id of your chosen Codamosa module, e.g. 21 is corresponding to 'tqdm' module   
python ablate.py --test-index $sample_id
```




## 📌 Notes

- TestWeaver builds tests incrementally by reasoning about what code remains uncovered.
- It uses slicing and closest-test retrieval to make LLM prompts more focused and effective.
- Generated tests are saved as `.py` files and can be executed with `pytest`.

---




## Baselines:

### CoverUp Baseline

Run CoverUp baseline with DeepSeek model.

**Prerequisites:** Docker, Python 3.10+

**Steps:**
1. Ensure `.env` file is configured (same as TestWeaver):
```bash
echo "OPENAI_API_KEY=sk-your-actual-api-key-here" > .env
echo "OPENAI_BASE_URL=https://llm-prof-tien.thaiminhpv.id.vn/" >> .env
```

2. Load docker image:
```bash
docker load -i scripts/baselines/coverup/docker/coverup-runner.tar
```

3. Run CoverUp baseline:
```bash
cd scripts/baselines/coverup
python3 scripts/eval_coverup.py --config deepseek-v3 --suite cm
```

**Optional:** Run on specific package or file:
```bash
python3 scripts/eval_coverup.py --config deepseek-v3 --suite cm --package tqdm
python3 scripts/eval_coverup.py --config deepseek-v3 --suite cm --only tqdm/_tqdm.py
```

**Output:** `scripts/baselines/coverup/output/cm.deepseek-v3/<package>/final.json`

### CodaMosa Baseline

Run CodaMosa baseline with DeepSeek model.

**Prerequisites:** Docker, Python 3.10+

**Steps:**
1. Ensure `.env` file is configured (same as TestWeaver):
```bash
echo "OPENAI_API_KEY=sk-your-actual-api-key-here" > .env
echo "OPENAI_BASE_URL=https://llm-prof-tien.thaiminhpv.id.vn/" >> .env
```

2. Load docker images:
```bash
cd scripts/baselines/codamosa/replication
docker load < docker-images/benchmarks-docker.tar.gz
docker load < docker-images/codamosa-docker.tar.gz
```

3. Start benchmark container (if not already started):
```bash
./scripts/start_benchmark_container.sh
```

4. Run CodaMosa baseline:
```bash
python3 run_codamosa_deepseek.py
```

**Output:** `scripts/baselines/codamosa/replication/deepseek-coda/<module>-<run>/statistics.csv`

