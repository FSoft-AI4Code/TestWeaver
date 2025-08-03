# TestWeaver

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
python testweaver.py --test-index $sample_id
```




## 📌 Notes

- TestWeaver builds tests incrementally by reasoning about what code remains uncovered.
- It uses slicing and closest-test retrieval to make LLM prompts more focused and effective.
- Generated tests are saved as `.py` files and can be executed with `pytest`.

---



