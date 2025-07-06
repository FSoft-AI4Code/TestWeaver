import sys
import re
from pathlib import Path
import json
from eval_coverup import load_suite

def parse_args():
    import argparse
    ap = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    ap.add_argument('logs', type=Path, nargs='+')

    ap.add_argument('--write-requirements', default=False,
                    action=argparse.BooleanOptionalAction)
    ap.add_argument('--write-json', default=False,
                    action=argparse.BooleanOptionalAction)
    return ap.parse_args()

args = parse_args()

suite = load_suite('cm')
module2suite = {
    f: suite[d]['package']
    for d in suite
    for f in suite[d]['files']
}
pkg2dir = {
    suite[d]['package']: str(Path(d) / suite[d]['src'])
    for d in suite
}

pkg2used = dict()
used = dict()

for filename in args.logs:
    with filename.open("r") as f:
        for line in f.readlines():
            if (m := re.match(r"Successfully installed (.*)", line)):
                for p in m.group(1).split():
                    m = re.match(r"(.*?)-(\d.*)$", p)
                    name, ver = m.group(1), m.group(2)
                    used[name] = ver
            elif (m := re.match(r".*?Requirement already satisfied: ([\w-]+).*\((.*?)\)$", line)):
                name, ver = m.group(1), m.group(2)
                used[name] = ver
            elif (m := re.match(r"coverup .*\s(\S+)$", line)):
                path = m.group(1)
                if path in module2suite:
                    pkg = module2suite[path]
                    if pkg not in pkg2used:
                        pkg2used[pkg] = {
                            k: used[k]
                            for k in sorted(used)
                            if k != 'CoverUp'
                        }
                used = dict()

pkg2used = {
    k: pkg2used[k]
    for k in sorted(pkg2used)
}

if args.write_json:
    jf = Path("packages.json")
    with jf.open("w") as f:
        json.dump(pkg2used, f, indent=4)
    print("wrote to {jf}")

if args.write_requirements:
    for pkg in pkg2used:
        p = Path(pkg2dir[pkg])
        assert (p / "package.txt").exists()
        p2 = p / "package2.txt"
        print(f"wrote to {p2}")
        with (p2).open("w") as f:
            for used, version in pkg2used[pkg].items():
                print(f"{used}=={version}", file=f)

