from pathlib import Path
from collections import defaultdict
import json
import re
import csv
from statistics import mean, median
import sys
import scipy.stats
import numpy as np
import functools

coverup_output = Path("output")
replication = Path("codamosa") / "replication"
mutap_output = Path("MuTAP-results")
mutap_benchmarks = Path("MuTAP-benchmarks")

def parse_args():
    import argparse
    ap = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    ap.add_argument('--suite', choices=['cm', '1_0', 'mutap'], default='cm',
                    help='suite of modules to compare')

    ap.add_argument('--config', type=str, default='gpt4o-v2',
                    help='specify a configuration to use for the first CoverUp')

    def other_system(value):
        coda_choices = [f'codamosa-{r}' for r in ['codex', 'gpt4', 'gpt4o']]
        mutap_choices = [f'mutap-{r}' for r in [
            'Codex_few',
            'Codex_zero',
            'gpt4o_few',
            'gpt4o_zero',
        ]]
        if not (value.startswith('coverup-') or value in coda_choices + mutap_choices):
            raise argparse.ArgumentTypeError(f'invalid choice: select coverup-..config.. or {", ".join(coda_choices + mutap_choices)}')
        return value

    ap.add_argument('--compare-to', '--to', type=other_system, default='codamosa-gpt4o',
                    help='select what to compare to')

    ap.add_argument('--ckpt', type=str,
                    help='use a given checkpoint for CoverUp coverage results')

    ap.add_argument('--plot', default=False,
                    action=argparse.BooleanOptionalAction,
                    help='plot results instead of showing a table')

    ap.add_argument('--rename-first', type=str,
                    help='Rename the first data point (CoverUp) in a plot')

    ap.add_argument('--histogram', choices=['coverage', 'delta', 'lines', 'lines+branches'],
                    help='draw a histogram')

    ap.add_argument('--array', default=False,
                    action=argparse.BooleanOptionalAction,
                    help='output main results in array format')

    ap.add_argument('--latex', default=False,
                    action=argparse.BooleanOptionalAction,
                    help='output main results in LaTeX format')

    ap.add_argument('--sigtest', default=False,
                    action=argparse.BooleanOptionalAction,
                    help='test per-module results for statistical significance')

    ap.add_argument('--title', type=str, help='specify different title for --plot')

    ap.add_argument('--out', type=Path, help='specify alternative output file for --plot')

    return ap.parse_args()

def load_suite(suite_name):
    modules_list = []

    if suite_name == 'mutap':
        for d in sorted(mutap_benchmarks.iterdir()):
            modules_list.append({
                'name': f"{d.name}.__init__",
                'base_module': d.name,
                'source_dir': ''
            })
    else:
        with (replication / "test-apps" / f"{suite_name}_modules.csv").open() as f:
            reader = csv.reader(f)
            for d, m in reader:
                dp = Path(d)
                assert dp.parts[0] == 'test-apps'

                modules_list.append({
                    'name': m,
                    'base_module': m.split('.')[0],
                    'source_dir': str(Path(*dp.parts[2:])) + "/" if len(dp.parts) > 2 else ''
                })

    return {
        "name": suite_name,
        "modules": modules_list
    }


@functools.cache
def json_load(path):
    with path.open() as f:
        return json.load(f)


def load_coverup(suite, config, ckpt):
    # per-module dictonary -> list of [coverage 'summary']
    data = defaultdict(list)

    config_output_dir = coverup_output / (suite['name'] + (f".{config}" if config else ""))

    if suite['name'] == 'cm' and not config_output_dir.exists():
        # load from "good", which is a superset of "cm"
        config_output_dir = coverup_output / ("good" + (f".{config}" if config else ""))

    if not config_output_dir.exists():
        print(f"Cannot load data: directory {config_output_dir} missing")
        sys.exit(1)

    for m in suite['modules']:
        m_name = m['name']
        m_out_dir = config_output_dir / m['base_module']

        if ckpt:
            ckpt_data = json_load(m_out_dir / f"coverup-ckpt-{ckpt}.json")
            cov = ckpt_data.get('final_coverage')
        else:
            cov_file = m_out_dir / "final.json"
            if cov_file.exists():
                cov = json_load(cov_file)
            else:
                cov = None
                ckpt_files = sorted(m_out_dir.glob("coverup-ckpt-*.json"))
                if ckpt_files:
                    if ckpt_files[-1] not in json_load_cache: print(f"Note: using {ckpt_files[-1]}")

                    ckpt_data = json_load(ckpt_files[-1])
                    cov = ckpt_data.get('final_coverage')

                if not cov:
                    continue

        file = m['source_dir'] + m_name.replace('.','/') + ".py"
        if file not in cov['files']:
            file = "/package/" + file
        assert file in cov['files'], f"{file} missing for {m_out_dir}"
        data[m_name].append(cov['files'][file]['summary'])

    return {
        "name": "CoverUp" + (f" ({config})" if config else ""),
        "data": data
    }


def load_mutap(suite, config):
    # per-module dictonary -> list of [coverage 'summary']
    data = defaultdict(list)
    assert config

    config_output_dir = mutap_output / f"{config}_augmented_test"

    if not config_output_dir.exists():
        print(f"Cannot load data: directory {config_output_dir} missing")
        sys.exit(1)

    for m in suite['modules']:
        m_name = m['name']

        m = re.match('f(\d+)\.__init__', m_name)
        m_num = m.group(1)

        cov_file = config_output_dir / f"{m_num}.json"
        if not cov_file.exists():
            continue

        cov = json_load(cov_file)
        file = [n for n in cov['files'] if Path(n).name == 'm.py']
        assert len(file) < 2

        if not (config_output_dir / f"{m_num}.failure").exists():
            assert file, f"m.py missing in {cov_file}"
        if file:
            file = file[0]
            data[m_name].append(cov['files'][file]['summary'])

    return {
        "name": "MuTAP" + (f" ({config})" if config else ""),
        "data": data
    }


def load_codamosa(suite, coda_config):
    assert suite['name'] in ('good', 'cm')

    config_output_dir = replication / f"output-{coda_config}"

    if not config_output_dir.exists():
        print(f"Cannot load data: directory {config_output_dir} missing")
        sys.exit(1)

    # list of per-file summaries
    data = defaultdict(list)

    for m in suite['modules']:
        module = m['name']

        for f in config_output_dir.glob(f"{module}-*.json"):
            file = module.replace('.','/') + ".py"

            with f.open() as jsonf:
                try:
                    cov = json.load(jsonf)
                except json.decoder.JSONDecodeError as e:
                    print(f"*** Error reading {str(f)}: {e}")
                    continue

            assert file in cov['files']
            if file in cov['files']:
                data[module].append(cov['files'][file]['summary'])

    return {
        "name": f"CodaMosa ({coda_config})",
        "data": data
    }


def fake_full_coverage(loaded_dataset, name):
    # fake 100% coverage
    fake_data = defaultdict(list)

    for m in loaded_dataset:
        summ = loaded_dataset[m][0]
        fake_data[m].append({
            'covered_lines': summ['covered_lines'] + summ['missing_lines'],
            'covered_branches': summ['covered_branches'] + summ['missing_branches'],
            'missing_lines': 0,
            'missing_branches': 0
        })

    return {
        "name": name,
        "data": fake_data,
        "is_fake": True
    }


def cover_pct(summ, cov_types):
    """Computes the percentage of coverage.

       summ: JSON "summary" from coverage measurement
       cov_types: either ['lines'], ['branches'] or ['lines','branches']
       return: percentage, or None if the denominator is 0.
    """
    nom = sum(summ[f"covered_{c}"] for c in cov_types)
    den = nom + sum(summ[f"missing_{c}"] for c in cov_types)
    return 100*nom/den if den > 0 else None


def mean_of(values):
    """Returns the mean of a list of values, ignoring any that are None.
       Returns None if there are no values to take the mean of.

       This is useful because some statistics may not be possible, such
       such as branch coverage when a module has no branches
    """
    clean = [v for v in values if v is not None]
    return mean(clean) if clean else None


if __name__ == "__main__":
    args = parse_args()

    suite = load_suite(args.suite)
    datasets = [load_coverup(suite, args.config, args.ckpt)]

    second_config = args.compare_to[args.compare_to.index('-')+1:]
    if args.compare_to.startswith('codamosa-'):
        if args.suite == '1_0':
            datasets.append(fake_full_coverage(datasets[0]['data'], "CodaMosa (fake)"))
        else:
            datasets.append(load_codamosa(suite, second_config))
    elif args.compare_to.startswith('mutap-'):
        datasets.append(load_mutap(suite, second_config))
    else:
        datasets.append(load_coverup(suite, second_config, args.ckpt))

    module_names = set(datasets[0]['data'].keys() | datasets[1]['data'].keys())
    if (missing_in_0 := module_names - datasets[0]['data'].keys()):
        print(f"Dataset lacks some modules: {missing_in_0}")
        sys.exit(1)

    if (missing_in_1 := module_names - datasets[1]['data'].keys()):
        for module in missing_in_1:
            print(f"Apparent test generation failure for {module}")
            ds_0 = datasets[0]['data'][module][0]
            datasets[1]['data'][module].append({
                'covered_lines': 0,
                'covered_branches': 0,
                'missing_lines': ds_0['covered_lines'] + ds_0['missing_lines'],
                'missing_branches': ds_0['covered_branches'] + ds_0['missing_branches'],
            })

    module_names = sorted(module_names)

    # compute lines+branches coverage for easy access
    coverage_lb = []
    for ds in datasets:
        coverage_lb.append([mean_of(cover_pct(sample, ['lines','branches']) for sample in ds['data'][m]) for m in module_names])

    # compute delta between the two coverage_lb
    cov_delta = [a - b for a, b in zip(coverage_lb[0], coverage_lb[1]) if a is not None and b is not None]

    # compute lines and branches for each module, for easy access
    module_info = defaultdict(dict)
    for module, summ in datasets[0]['data'].items():
        summ = summ[0] # use 1st sample
        module_info[module]['lines'] = summ['covered_lines'] + summ['missing_lines']
        module_info[module]['branches'] = summ['covered_branches'] + summ['missing_branches']

    # show missing modules
    for i in range(len(datasets)):
        missing = set(mod['name'] for mod in suite['modules']) - set(datasets[i]['data'].keys())
        if missing:
            print(f"Missing in {datasets[i]['name']}: {', '.join(sorted(missing))}")
            print()

    if args.plot or args.histogram:
        import matplotlib.pyplot as plt
        import numpy as np

        import seaborn as sns
        sns.set_theme(palette=None)

        plt.rcParams.update({
            'font.weight': 'bold',
            'pdf.fonttype': 42  # output TrueType; bigger but scalable
        })

        codamosa_label = datasets[1]['name']

        if args.histogram:
            fig, ax = plt.subplots()
            ax.set_ylabel('Frequency', size=18)

            fig.set_size_inches(16, 8)

            if args.histogram == 'coverage':
                ax.set_title('Combined (translucent) Lines+Branches Coverage Histogram', size=20)
                ax.set_xlabel('% Coverage', size=18)

                bins = 40
                ax.hist(coverage_lb[0], bins=bins, alpha=.5, label=datasets[0]['name'], color='blue')
                ax.hist(coverage_lb[1], bins=bins, alpha=.5, label=datasets[1]['name'], color='yellow')

                ax.legend(loc='upper left', fontsize=15)

                fig.tight_layout()

            elif args.histogram == 'delta':
                ax.set_title('Delta Coverage Histogram', size=20)
                ax.set_xlabel(f'({datasets[0]["name"]} - {datasets[1]["name"]}) % Coverage', size=18)
                ax.hist(cov_delta, bins=40)

            elif args.histogram == 'lines':
                ax.set_title('Lines per Module Histogram', size=20)
                ax.set_xlabel('# Lines in Module', size=18)
                ax.hist([module_info[m]['lines'] for m in module_names], bins=100)

            elif args.histogram == 'lines+branches':
                ax.set_title('Lines+Branches per Module Histogram', size=20)
                ax.set_xlabel('# Lines + # Branches in Module', size=18)
                ax.hist([module_info[m]['lines']+module_info[m]['branches'] for m in module_names], bins=100)

            fig.savefig('histogram.pdf')
        else:
            cov_delta = sorted(cov_delta, reverse=True)

            first_label = args.rename_first if args.rename_first else datasets[0]["name"]

            fig, ax = plt.subplots()
            if args.title:
                ax.set_title(args.title, size=20, weight='bold')
            else:
                ax.set_title(f'Coverage increase {first_label} vs. {datasets[1]["name"]} (larger is better)', size=20, weight='bold')

            ax.set_xlabel('modules', fontsize=18, weight='bold')
            ax.set_ylabel('Coverage increase (%)', fontsize=18)

            colors = ['green' if d>0 else 'black' for d in cov_delta]
            bars_x = np.arange(len(cov_delta))

            ax.bar(bars_x, cov_delta, .7, color=colors, lw=0.)  # lw=0. disables white shadow with seaborn
            ax.set_xticks([])

            fig.set_size_inches(10, 6)
            fig.tight_layout()

            if args.out:
                fig.savefig(args.out)
            else:
                fig.savefig('plot.pdf')

    else:
        from tabulate import tabulate

        headers=["Module", "Lines", "Branches", datasets[0]['name'] + " %", datasets[1]['name'] + " %", "samples", "delta %"]
        def table():
            if sys.stdout.isatty():
                from simple_colors import red, green
            else:
                red = green = lambda v: v

            for m, a, b in zip(module_names, coverage_lb[0], coverage_lb[1]):
                if a is not None: a = round(a, 2)
                if b is not None: b = round(b, 2)

                delta = ''
                if a is not None and b is not None:
                    delta = a - b
                    v = f"{a:5.2f}"
                    if a > b:
                        a = green(v)
                    elif a < b:
                        a = red(v)
                    else:
                        a = v

                yield m, module_info[m]['lines'], module_info[m]['branches'], a, b, len(datasets[1]['data'][m]), delta

        print('')
#        print(tabulate(sorted(table(), key=lambda x: x[1]*x[-1]), headers=headers)) # sort worst to best performance
        print(tabulate(table(), headers=headers))

        first_system = None

        table_rows = []
        for ds in datasets:
            name = ds['name']
            dataset = ds['data']

            if args.ckpt:
                name += f" ckpt {args.ckpt}"

            if 'is_fake' in ds and ds['is_fake']:
                continue

            numbers_1 = []
            numbers_2 = []

            row = [name]

            for metrics in [['lines'], ['branches'], ['lines','branches']]:
                covered = sum(sample[f'covered_{metric}'] for metric in metrics for m in module_names for sample in dataset[m])
                total = covered + sum(sample[f'missing_{metric}'] for metric in metrics for m in module_names for sample in dataset[m])

                row.append(f"{100*covered/total:.1f}")
                numbers_1.append(100*covered/total)

            for metrics in [['lines'], ['branches'], ['lines','branches']]:
                data = [mean_of(cover_pct(sample, metrics) for sample in dataset[m]) for m in module_names]
                data = [d for d in data if d is not None]

                row.append(f"{median(data):.1f}")
                numbers_2.append(median(data))

            table_rows.append(row)

            if args.latex:
                print()
                print(' & '.join([f"\\pct{{{v:.1f}}}" for v in numbers_1 + numbers_2]), "\\\\")
                if first_system:
                    print(' & '.join([f"\\pct{{{b-a:.1f}}}" for a, b in zip(first_system, numbers_1 + numbers_2)]), "\\\\")

            if args.array:
                print(f"'{name}': {[round(n,1) for n in numbers_1 + numbers_2]}")

            if not first_system:
                first_system = numbers_1 + numbers_2

        print()
        print(tabulate(table_rows, headers=["generator", "overall l %", "overall b %", "overall l+b %", "per-mod l %", "per-mod b %", "per-mod l+b %"]))

        better_count = sum([v > 0 for v in cov_delta])
        worse_count = sum([v < 0 for v in cov_delta])

        print()
        print(f"{datasets[0]['name']} did better on {better_count} ({100*better_count/len(cov_delta):.1f}%) " +\
                           f"and worse on {worse_count} benchmarks out of {len(cov_delta)}.")


        if args.sigtest:
            print()
            print(f"Statistical significance tests for module coverage ({datasets[0]['name']} - {datasets[1]['name']}):")
            print()
            for metrics in [['lines'], ['branches'], ['lines','branches']]:
                label = '+'.join(metrics)
                short_label = '+'.join(m[0] for m in metrics)

                data = []
                for ds in datasets:
                    tmp = [mean_of(cover_pct(sample, metrics) for sample in ds['data'][m]) for m in module_names]
                    tmp = [d for d in tmp if d is not None]
                    data.append(tmp)

                assert len(data[0]) == len(data[1])
                for i in range(2):
                    data[i] = np.array(data[i])
                    assert not np.any(np.isnan(data[i]))

                #ttest = scipy.stats.ttest_rel(*data)
                ptest = scipy.stats.permutation_test(
                    (*data,),
                    statistic=lambda x, y: np.mean(x-y),
                    alternative='greater',
                    permutation_type='samples',
                    n_resamples=50000,
                    random_state=42
                )

                print(f"{short_label + ':':10} ptest stat={ptest.statistic:.1f}, p-value={ptest.pvalue:.1e}")
