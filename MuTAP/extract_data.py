from pathlib import Path
import json
import re

source = Path('HumanEval/Testing_HumanEval')

def parse_test(file: Path) -> str:
    if not file.exists():
        return ''

    text = file.read_text()

    if (m := re.search(r'\n(def test\(\):\n.*)$', text, re.DOTALL)):
        test = m.group(1)
        if not re.match(r'def test\(\):\n\s*\w', test):
            test = ''
        return test

    print(f"Unable to parse {file}")


if __name__ == "__main__":
    data = []
    for task_id in range(1, 163+1):
        code = source / str(task_id) / f"script_NDS_{task_id}.py"
        if not code.exists() or not (source / str(task_id) / "gpt4o").exists():
            break

        normal = parse_test(source / str(task_id) / 'gpt4o' / f"normal_full_{task_id}.py")
        fewshot = parse_test(source / str(task_id) / 'gpt4o' / f"fewshot_full{task_id}.py")

        data.append(json.dumps({
            'task_id': task_id,
            'solution': code.read_text(),
            'zero_augmented_test': normal,
            'few_augmented_test': fewshot,
        }))

    print(f"Gathered {len(data)} records")

    (Path("Data") / "gpt4o_test.jsonl").write_text(
        '\n'.join(data)
    )
