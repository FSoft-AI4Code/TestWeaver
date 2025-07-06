from pathlib import Path
import json
import matplotlib.pyplot as plt
from compare import load_suite
import re
from collections import namedtuple

def parse_args():
    import argparse
    ap = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    ap.add_argument('--suite', choices=['good', 'cm', '1_0', 'mutap'], default='cm',
                    help='suite of modules to compare')

    ap.add_argument('--config', type=str, default='gpt4o-v2', help='specify a (non-default) configuration to use')

    ap.add_argument('--compare-to', type=str, default='gpt4o-v2-no-coverage', help='specify a configuration to compare to')
    return ap.parse_args()


def test_order_key(it: Path):
    m = re.match('test_coverup_(\d+).', it.name)
    return (int(m.group(1)), str(it))


def load_coverage(path, suite):
    if not path.exists():
        raise RuntimeError(f"{path} doesn't exist")

    base_modules = {m['base_module'] for m in load_suite(suite)['modules']}

    print(f"gathering from {path}...")
    coverage = []
    for filepath in sorted(path.glob("*/coverage/test_coverup_*.json"), key=test_order_key):
        rel = filepath.relative_to(path)
        if rel.parts[0] not in base_modules:
            continue

        test_coverage = set()
        with filepath.open('r') as file:
            data = json.load(file)

        for file_name, file_data in data.get('files', {}).items():
            if 'coverup-tests' in file_name:    # ignore coverage in test files
                continue

            for line in file_data.get('executed_lines', []):
                test_coverage.add(file_name + ":" + str(line))

        coverage.append({'test': filepath, 'coverage': test_coverage})

    return coverage


def compute_overlap(coverage):
    print("computing...")
    test_overlap = []
    covered_set_size = []
    covered_set = set()
    for e in coverage:
        overlap = len(covered_set.intersection(e['coverage']))
#        if overlap > 1000:
#            print(f"{e['test']} {overlap=}")
        test_overlap.append(overlap)
        covered_set.update(e['coverage'])
        covered_set_size.append(len(covered_set))
    return namedtuple('data', ['test_overlap', 'covered_set_size'])(test_overlap, covered_set_size)


def make_figure(coverage, filename):
    data = compute_overlap(coverage)

    print("drawing...")
    plt.figure(figsize=(10, 6))
    plt.bar(range(1, len(data.test_overlap)+1), data.test_overlap, color='orange', label='overlap with previous')
    plt.plot(data.covered_set_size, color='blue', label='coverage set size')
    plt.xlabel('Test sequence')
    plt.ylabel('Line Coverage')
    plt.title('Line Coverage from Successive Tests')

    plt.xticks(rotation=90)
    plt.tight_layout()
    plt.legend()
    plt.savefig(filename)


def make_comparison(cov1, cov2, filename):
    print("computing...")

    data1 = compute_overlap(cov1)
    data2 = compute_overlap(cov2)

    print("drawing...")
    plt.figure(figsize=(10, 6))
    plt.bar(range(1, len(data1.test_overlap)+1), data1.test_overlap, color='orange')
    plt.plot(data1.covered_set_size, color='orange')

    plt.bar(range(1, len(data2.test_overlap)+1), data2.test_overlap, color='blue')
    plt.plot(data2.covered_set_size, color='blue')

    plt.xlabel('Test sequence')
    plt.ylabel('Line Coverage')
    plt.title('Line Coverage from Successive Tests')

    plt.xticks(rotation=90)
    plt.tight_layout()
    plt.legend()
    plt.savefig(filename)


def load_or_gather(args, config):
    coverage_json = Path(f"coverage-{config}.json")

    if coverage_json.exists():
        print(f"reading {coverage_json}...")
        with coverage_json.open("r") as f:
            coverage = json.load(f)
            coverage = [{'test': e['test'], 'coverage': set(e['coverage'])} for e in coverage]
    else:
        path = Path('output') / (args.suite + (f".{config}" if config else ""))
        print(f"{path=}")
        if not path.exists() and args.suite == 'cm':
            path = Path('output') / ('good' + (f".{config}" if config else ""))

        coverage = load_coverage(path, args.suite)
        with coverage_json.open("w") as f:
            json.dump([{'test': str(e['test']), 'coverage': list(e['coverage'])} for e in coverage], f)

    return coverage


if __name__ == "__main__":
    args = parse_args()

    cov1 = load_or_gather(args, args.config)
    if args.compare_to:
        cov2 = load_or_gather(args, args.compare_to)
        make_comparison(cov1, cov2, "overlap.png")
    else:
        make_figure(coverage, "overlap.png")

