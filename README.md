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

### 1. Clone the repository

```bash
git clone https://github.com/<your-org-or-user>/testweaver.git
cd testweaver
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```


---

## 🔐 Configure API Key

You need to set up access to an LLM provider before running TestWeaver.

### OpenAI

```bash
export OPENAI_API_KEY=sk-...
```

### Deepseek

```bash
export Deepseek_API_KEY=...
```




## 🚀 Usage

Run TestWeaver with your project:

```bash
python testweaver.py --test-index ...
```





## 📌 Notes

- TestWeaver builds tests incrementally by reasoning about what code remains uncovered.
- It uses slicing and closest-test retrieval to make LLM prompts more focused and effective.
- Generated tests are saved as `.py` files and can be executed with `pytest`.

---



