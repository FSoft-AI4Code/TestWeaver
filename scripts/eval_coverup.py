import csv
from pathlib import Path
from collections import defaultdict
import subprocess
import os

test_apps = Path("codamosa/replication/test-apps")
mutap_benchmarks = Path("MuTAP-benchmarks")
pip_cache = Path("pip-cache")  # set to None to disable
eval_path = Path(__file__).parent.parent

def parse_args():
    import argparse
    ap = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    
    ap.add_argument('package', type=str, nargs='?',
                    help='only process the given package')

    ap.add_argument('--dry-run', dest='dry_run', action='store_true',
                help="only print out the command(s), but don't execute them")
    ap.add_argument('--no-dry-run', dest='dry_run', action='store_false',
                    help="execute the commands instead of just printing them")
    ap.set_defaults(dry_run=False)


    ap.add_argument('--suite', choices=['cm', '1_0', 'mutap'], default='cm',
                    help='suite of modules to compare')

    ap.add_argument('--skip-package', action='append', default=[], help='skip given package')

    ap.add_argument('--config', type=str, help='specify a (non-default) configuration to use')

    # ap.add_argument('--get-test-coverage', default=False,
    #                 action=argparse.BooleanOptionalAction,
    #                 help='measure per-test coverage (rather than run CoverUp)')
    ap.add_argument('--get-test-coverage', dest='get_test_coverage', action='store_true',
                help='measure per-test coverage (rather than run CoverUp)')
    ap.add_argument('--no-get-test-coverage', dest='get_test_coverage', action='store_false',
                    help='run CoverUp instead of measuring per-test coverage')
    ap.set_defaults(get_test_coverage=True)


    ap.add_argument('--interactive', dest='interactive', action='store_true',
                help='interactive')
    ap.add_argument('--no-interactive', dest='interactive', action='store_false',
                    help='interactive')
    ap.set_defaults(interactive=True)

    ap.add_argument('--only', dest='only', action='store_true',
                help='only run the specified test(s)')
    ap.add_argument('--no-only', dest='only', action='store_false',
                    help='run all tests (not just specified ones)')
    ap.set_defaults(only=False)  # or True, depending on desired default

    # ap.add_argument('-i', '--interactive', default=False,
    #                 action=argparse.BooleanOptionalAction,
    #                 help='start interactive docker (rather than run CoverUp)')

    ap.add_argument('--pip-cache', dest='pip_cache', action='store_true',
                help='mount pip cache volume in Docker container')
    ap.add_argument('--no-pip-cache', dest='pip_cache', action='store_false',
                    help='do not mount pip cache volume in Docker container')
    ap.set_defaults(pip_cache=True)  # or False, depending on what you want by default

    
    # ap.add_argument('--pip-cache', default=True,
    #                 action=argparse.BooleanOptionalAction,
    #                 help=f'whether to pass in the pip cache')

    args = ap.parse_args()

    if args.interactive and not args.package:
        ap.error("package is required when using --interactive.")

    return args

def load_suite(suite):
    pkg = dict()

    if suite == 'mutap':
        for d in sorted(mutap_benchmarks.iterdir()):
            pkg[d] = {
                'package': d.name,
                'src': Path(),
                'files': [str(Path(d.name) / "__init__.py")]
            }
    else:
        modules_csv = test_apps / f"{suite}_modules.csv"
        with modules_csv.open() as f:
            reader = csv.reader(f)
            for d, m in reader:
                d = Path(d)
                assert d.parts[0] == 'test-apps'
                pkg_top = test_apps / d.parts[1] # package topdir
                pkg_name = m.split('.')[0] # package/module name
                src = Path(*d.parts[2:]) # relative path to 'src' or similar

                if pkg_top not in pkg:
                    pkg[pkg_top] = {
                        'package': pkg_name,
                        'src': src,
                        'files': []
                    }
                else:
                    assert pkg[pkg_top]['package'] == pkg_name
                    assert pkg[pkg_top]['src'] == src

                pkg[pkg_top]['files'].append(str(src / (m.replace('.','/') + ".py")))

    return pkg

if __name__ == "__main__":
    args = parse_args()
    pkg = load_suite(args.suite)
    max_packages = 2
    pkg = dict(list(pkg.items())[:max_packages])
    for pkg_top in pkg:
        if args.package and args.package not in str(pkg_top):
            continue

        package = pkg[pkg_top]['package']
        src = pkg[pkg_top]['src']
        files = pkg[pkg_top]['files']

        if package in args.skip_package:
            continue

        if args.only:
            if args.only not in files:
                print(f"{args.only} not among {package} suite files.")
                continue
            files = [args.only]

        output = Path("output") / (args.suite + (f".{args.config}" if args.config else "")) / package

        if (output / "final.json").exists() and not (args.dry_run or args.interactive or args.get_test_coverage):
            if args.package : print(f"{str(output/'final.json')} exists, skipping.")
            continue

        if not args.dry_run:
            output.mkdir(parents=True, exist_ok=True)

        config = args.config if args.config else 'default'

        # topmost directory for sources
        src_topdir = src.parts[0] if src.parts else package

        script = 'get_test_coverage.sh' if args.get_test_coverage else 'run_coverup.sh'

        cmd = f"docker run --rm " +\
              f"-v {str(eval_path.absolute())}:/eval:ro " +\
              f"-v {str(output.absolute())}:/output " +\
              f"-v {str(pkg_top.absolute())}:/package:ro " +\
              f"-v {str((pkg_top / src_topdir).resolve())}:/output/{src_topdir}:ro " +\
              (f"-v {str((eval_path / 'pip-cache').absolute())}:/root/.cache/pip " if args.pip_cache else "") +\
              ("-ti " if args.interactive else "-t ") +\
               "coverup-runner bash " +\
              (f"/eval/scripts/{script} {config} {src} {package} {' '.join(files)}" if not args.interactive else "")

        print(cmd, flush=True)
        if not args.dry_run:
            subprocess.run(cmd, shell=True, check=True)
