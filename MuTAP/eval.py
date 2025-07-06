from pathlib import Path
from statistics import median, mean
import subprocess
from collections import defaultdict

TEST_DIR = Path('HumanEval/Testing_HumanEval')


def read_jsonl(datafile: Path):
    import json
    import gzip

    data = []
    if datafile.suffix == '.gz':
        with datafile.open("rb") as df:
            with gzip.open(df, "rt") as fp:
                for line in fp:
                    data.append(json.loads(line))
    else:
        with datafile.open("r") as df:
            for line in df:
                data.append(json.loads(line))

    return data


def run_test(case, test, outfile):
    import json
    import tempfile
    import sys
    import os

    try:
        with tempfile.TemporaryDirectory(dir='.') as d:
            d = Path(d).resolve()

            (d / "m.py").write_text(case['solution'])
            (d / "test.py").write_text("from m import *\n" + case[test])

            p = subprocess.run([sys.executable, '-m', 'slipcover', '--branch', '--json', '--out', str(outfile),
                                '--source', str(d),
                                '-m', 'pytest', '-qq', '-x', '--disable-warnings', str(d / "test.py")],
                                check=True, capture_output=True, timeout=60)

            with outfile.open("r") as f:
                cov = json.load(f)

            cov = cov['files'].get(str((d / "m.py").relative_to(Path.cwd())), {'summary': {'percent_covered': 0}})
            return cov['summary']['percent_covered']

    except subprocess.CalledProcessError as e:
        (outfile.parent / f"{outfile.stem}.failure").write_text(str(e.output, 'utf-8'))
        print(e, str(e.output, 'utf-8'))
        return -1

def find_dependencies(source):
    import ast

    with source.open("r") as f:
        tree = ast.parse(f.read(), filename=str(source))

    dependencies = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                dependencies.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            dependencies.add(node.module)
    return dependencies


def parse_args():
    import argparse

    ap = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    ap.add_argument("--run", type=Path, help="run tests, saving to the given path")
    ap.add_argument("--llm", type=str, help="if running, pick llm to run from given llm")
    ap.add_argument("--extract", type=Path, help="extract code")

    args = ap.parse_args()
    if not (args.run or args.extract):
        ap.error("Please select either --run or --extract")

    return args


#def del_empty(s):
#    nonempty = [line for line in s.split('\n') if line.strip() != '']
#    return '\n'.join(nonempty)


def main():
    import tqdm

    args = parse_args()

    data = dict()
    for llm in ([args.llm] if args.llm else ["Codex", "llama2", "gpt4o"]):
        file = Path("Data") / f"{llm}_test.jsonl.gz"
        if not file.exists():
            file = Path("Data") / f"{llm}_test.jsonl"

        data[llm] = read_jsonl(file)

    counts = defaultdict(int)

    if args.run:
        for llm in data:
            for case in data[llm]:
                for prompt in ['zero', 'few']:
                    test = f"{prompt}_augmented_test"
                    test_id = int(case['task_id'])

                    if test in case:
                        outfile = args.run / f"{llm}_{test}" / f"{test_id:03d}.json"
                        outfile.parent.mkdir(parents=True, exist_ok=True)

                        print(f"---- {llm} {test_id} {test} ----")
                        result = run_test(case, test, outfile)
                        print(f"{result=}")

            if (f := (TEST_DIR / f"normal_{llm}_completions.jsonl")).exists():
                (args.run / f"{llm}_zero_augmented_test" / "completions.jsonl").write_text(f.read_text())
            if (f := (TEST_DIR / f"fewshot_{llm}_completions.jsonl")).exists():
                (args.run / f"{llm}_few_augmented_test" / "completions.jsonl").write_text(f.read_text())


    if args.extract:
        humaneval_task = dict()
        for case in data['Codex']:
            assert case['task_id'] not in humaneval_task
            humaneval_task[case['task_id']] = case['solution']

        for case in data['llama2']:
            assert humaneval_task[case['task_id']] == case['solution']

        lengths = [len(t.splitlines()) for t in humaneval_task.values()]
        print(f"function lengths: {min(lengths)} - {max(lengths)}, median: {median(lengths)}")

        for t, solution in tqdm.tqdm(humaneval_task.items()):
            p = args.extract / f"f{int(t):03d}"
            p.mkdir(parents=True)

            src = p / p.name
            src.mkdir()

            code = src / "__init__.py"
            code.write_text(solution)
            deps = find_dependencies(code)

            (p / "package.txt").write_text("\n".join(deps))

if __name__ == "__main__":
    main()
