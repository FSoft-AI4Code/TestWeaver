import json
import re
from pathlib import Path
from collections import namedtuple, defaultdict
from coverup.logreader import get_sequences
from compare import load_suite
from sequences import get_coverup_logs
from tqdm import tqdm


def parse_args():
    import argparse
    ap = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    ap.add_argument('--suite', choices=['cm', '1_0', 'mutap'], default='cm',
                    help='suite of modules to compare')

    ap.add_argument('config', type=str, help='specify a configuration to use')
    ap.add_argument('compare_to', type=str, help='specify a configuration to compare to')

    ap.add_argument('--latex', default=False,
                    action=argparse.BooleanOptionalAction,
                    help='output main results in LaTeX format')

    return ap.parse_args()


def scan_logs(config, args):
    print(f"scanning {config} logs...")

    rejected = defaultdict(int)
    test_ckpt = dict()
    for file, rel in tqdm(sorted(get_coverup_logs(args.suite, config))):
        mod = rel.parts[0]
        m = re.search(r"-(\d+)$", str(file))
        ckpt = m.group(1)

        for seg, seq in get_sequences(file.read_text(), check_c_p_equivalence=False):
            if seq[-1][0] == 'u':
                defs = re.findall(r'^ *def test_\w+\(', seq[-2][2], re.M)
                rejected[ckpt] += len(defs) # number of test functions in generation

            elif seq[-1][0] == 'G':
                m = re.search(r'/(test_coverup_\d+.py)', seq[-1][2])
                test_ckpt[(mod, m.group(1))] = ckpt

#    print(f"{config} {rejected=}")

    return {
        'rejected': rejected,
        'test_ckpt': test_ckpt
    }


def test_order_key(it: Path):
    m = re.match(r'test_coverup_(\d+)\.', it.name)
    return (int(m.group(1)), str(it))


def gather_coverage(path, suite):
    if not path.exists():
        raise RuntimeError(f"{path} doesn't exist")

    base_modules = {m['base_module'] for m in load_suite(suite)['modules']}

    print(f"gathering from {path}...")
    coverage = []
    for filepath in tqdm(sorted(path.glob("*/func-coverage/*.json"), key=test_order_key)):
        rel = filepath.relative_to(path)
        mod = rel.parts[0]
        if mod not in base_modules:
            continue

        test_coverage = []
        with filepath.open('r') as file:
            data = json.load(file)

        for file_name, file_data in data.get('files', {}).items():
            if 'coverup-tests' in file_name:    # ignore coverage in test files
                continue

            for line in file_data.get('executed_lines', []):
                test_coverage.append(f"{file_name}:{line}")
            for branch in file_data.get('executed_branches', []):
                test_coverage.append(f"{file_name}:{branch}")

        coverage.append({
            'module': mod,
            'test': str(filepath),
            'test_file': str(filepath.name).split('::')[0],
            'coverage': test_coverage
        })

    return coverage


def compute(coverage, args):
    print(f"computing {coverage['name']}...")
    useful = defaultdict(int)
    total = defaultdict(int)

    test_ckpt = coverage['test_ckpt']
    rejected = coverage['rejected']

    covered_set = set()
    for e in coverage['data']:
        ckpt = test_ckpt[(e['module'], e['test_file'])]

        total[ckpt] += 1
        # add module to file+line or file+branch to make sure we're not confusing files
        entry_set = set((e['module'], it) for it in e['coverage'])
        if not covered_set.issuperset(entry_set):
            useful[ckpt] += 1

        covered_set.update(entry_set)

    for c in sorted(total):
        n = useful[c]
        d = total[c] + rejected[c]
        print(f"{coverage['name']} {c:5} ({n}/{d}) {n/d*100:.1f}%")

    n = sum(useful[c] for c in total)
    d = sum(total[c]+rejected[c] for c in total)
    print(f"{coverage['name']} total ({n}/{d}) {n/d*100:.1f}%")

    if args.latex:
        print()
        numbers = []
        for c in sorted(total):
            numbers += [0.0, 100*useful[c]/(total[c]+rejected[c])]
        numbers += [0.0, d]

        print(' & '.join([f"\\pct{{{v:.1f}}}" if isinstance(v, float) else str(v) for v in numbers]), "\\\\")

#    return namedtuple('data', ['name', 'useless_tests'])(coverage['name'], useless_tests)


def load_or_gather(config, args):
    import gzip
    coverage_json = Path(f"cache/func-coverage-{config}.json.gz")

    if coverage_json.exists():
        print(f"reading {coverage_json}...")
        with gzip.open(coverage_json, "r") as f:
            coverage = json.load(f)
    else:
        path = Path('output') / (args.suite + (f".{config}" if config else ""))
        if not path.exists() and args.suite == 'cm':
            path = Path('output') / ('good' + (f".{config}" if config else ""))

        coverage = {
            'name': config,
            'data': gather_coverage(path, args.suite)
        }
        with gzip.open(coverage_json, "wt") as f:
            json.dump(coverage, f)

    return coverage


if __name__ == "__main__":
    args = parse_args()

    log1 = scan_logs(args.config, args)
    log2 = scan_logs(args.compare_to, args)

    cov1 = load_or_gather(args.config, args)
    cov1.update(log1)
    compute(cov1, args)

    cov2 = load_or_gather(args.compare_to, args)
    cov2.update(log2)
    compute(cov2, args)
