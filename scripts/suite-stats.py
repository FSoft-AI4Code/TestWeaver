from pathlib import Path
from eval_coverup import load_suite

def parse_args():
    import argparse
    ap = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    ap.add_argument('--suite', choices=['cm', '1_0', 'mutap'], default='cm',
                    help='suite of modules to compare')

    ap.add_argument('--skip-package', action='append', default=[], help='skip given package')

    return ap.parse_args()

args = parse_args()
suite = load_suite(args.suite)

def count_functions(code_string: str) -> int:
    import ast
    tree = ast.parse(code_string)
    return sum(isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef) for node in ast.walk(tree))

files = lines = functions = 0

for pkg_top, pkg in suite.items():
    if pkg['package'] in args.skip_package:
        print(f"Skipping {pkg_top}")
        continue

    for file in pkg['files']:
        file = pkg_top / Path(file)

        files += 1

        with file.open("r") as f:
            lines += sum(1 for _ in f)

        functions += count_functions(file.read_text())

print(f"Suite {args.suite} has {functions} functions, {lines} lines in {files} files.")
