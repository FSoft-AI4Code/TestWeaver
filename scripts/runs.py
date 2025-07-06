from pathlib import Path
from collections import defaultdict
import json
import csv
from statistics import mean, median

replication = Path("codamosa") / "replication"  # 'codamosa' links to its replication package
coverup_output = Path("output")
RUNS=3

def parse_args():
    import argparse
    ap = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    ap.add_argument('--suite', choices=['good', '1_0'], default='good',
                    help='suite of modules to compare')

    ap.add_argument('--config', type=str, help='specify a (non-default) configuration to use')

    ap.add_argument('--plot', default=True,
                    action=argparse.BooleanOptionalAction,
                    help=f'plot the runs')

    ap.add_argument('--only', type=str,
                    help='only process files containing this string')

    return ap.parse_args()

args = parse_args()

modules_csv = replication / "test-apps" / f"{args.suite}_modules.csv"
coverup_orig_output = coverup_output / args.suite
coverup_output = coverup_output / (args.suite + (f".{args.config}" if args.config else ""))

modules_list = []
with modules_csv.open() as f:
    reader = csv.reader(f)
    for d, m in reader:
        dp = Path(d)
        assert dp.parts[0] == 'test-apps'

        modules_list.append({
            'name': m,
            'base_module': m.split('.')[0],
            'source_dir': str(Path(*dp.parts[2:])) + "/" if len(dp.parts) > 2 else ''
        })

cache = dict()
def get_summ(path, m, run):
    ckpt_file  = path / m['base_module'] / f"coverup-ckpt-{run}.json"
    if not (cov := cache.get(ckpt_file)):
        with ckpt_file.open() as jsonf:
            ckpt = json.load(jsonf)
        cov = ckpt.get('final_coverage')
        cache[ckpt_file] = cov

    file = m['source_dir'] + m['name'].replace('.','/') + ".py"
    return cov['files'][file]['summary']

coverup = defaultdict(lambda: [0])
coverup_orig = defaultdict(lambda: [0])

for m in modules_list:
    base_module = m['base_module']

    if args.only and args.only not in base_module: continue
    if not (coverup_output / base_module).exists(): continue

    for run in range(1, RUNS+1):
        coverup[m['name']].append(get_summ(coverup_output, m, run)['percent_covered'])

        if args.config:
            coverup_orig[m['name']].append(get_summ(coverup_orig_output, m, run)['percent_covered'])

for m in sorted(coverup.keys()):
    print(f"{m:45} {[round(v,2) for v in coverup[m]]}")

print('')
print(len(coverup), "module(s)")

print('')
print('median: ', [round(median(coverup[m][r] for m in coverup), 2) for r in range(1,RUNS+1)])
print('mean:   ', [round(mean(coverup[m][r] for m in coverup), 2) for r in range(1,RUNS+1)])

if args.config:
    print('')
    print('original:')
    print('median: ', [round(median(coverup_orig[m][r] for m in coverup_orig), 2) for r in range(1,RUNS+1)])
    print('mean:   ', [round(mean(coverup_orig[m][r] for m in coverup_orig), 2) for r in range(1,RUNS+1)])

if args.plot:
    import matplotlib.pyplot as plt

    plt.rcParams.update({
        'font.weight': 'bold',
        'pdf.fonttype': 42  # output TrueType; bigger but scalable
    })

    fig, ax = plt.subplots()

    ax.set_title('Percentual coverage achieved (larger is better)', size=20)
    ax.set_ylabel('% coverage', size=18)
    ax.set_xticks([])

    x = range(len(coverup.keys()))
#    colors = ['grey', 'light blue', 'light red']
    import numpy as np

    for run in range(1,4):
        values = [coverup[m][run] - coverup[m][run-1] for m in coverup]
        bottom = [coverup[m][run-1] for m in coverup]
        ax.bar(x, values, bottom=bottom, label=f"run #{run}", width=1)#, color=colors[run-1], width=1)

    ax.set_xlim(-.5, len(coverup.keys())-.5)
    ax.legend(fontsize=15)

    fig.set_size_inches(18, 8)
    fig.tight_layout()
    fig.savefig('runs.png')
