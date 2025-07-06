from pathlib import Path
import re
from collections import defaultdict
import json
from coverup.logreader import parse_log, TERMINAL_EVENTS
from compare import load_suite
from tqdm import tqdm


def parse_args():
    import argparse
    ap = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    ap.add_argument('--suite', choices=['cm', 'good', '1_0', 'mutap'], default='cm',
                    help='suite of modules to compare')

    ap.add_argument('--config', type=str, default='gpt4o-v2', help='specify a (non-default) configuration to use')


    ap.add_argument('--show', type=str,
                    help='print out instances of a given sequence')

    ap.add_argument('--check-c-p', action="store_true",
                    help='check for C prompts that are equivalent to a C prompt')

    ap.add_argument('--skip', type=str,
                    help='skip files containing this string')

    ap.add_argument('--ckpt', type=str,
                    help='use a given checkpoint/run')

    return ap.parse_args()


def get_coverup_logs(suite, config):
    base_modules = {m['base_module'] for m in load_suite(suite)['modules']}

    path = Path('output') / (suite + (f".{config}" if config else ""))
    if not path.exists() and suite == 'cm':
        path = Path('output') / ('good' + (f".{config}" if config else ""))

    if not path.exists():
        print(f"{path} doesn't exist")
        return

    for file in path.glob("*/coverup-log-*"):
        rel = file.relative_to(path)
        if rel.parts[0] not in base_modules:
            print(f"Skipping {rel}")
            continue

        yield file, rel


def get_sequences(log_content: str, check_c_p_equivalence=False):
    seqs = defaultdict(str)
    seq_ts = defaultdict(lambda:[])

    def yield_sequences():
        for seg, seq in seqs.items():
            # Only include sequences that reached a terminal
            # state, or else we'd count partial executions,
            # when CoverUp gets interrupted.
            if seq[-1] in TERMINAL_EVENTS:
                yield seg, seq, seq_ts[seg]
        seqs.clear()

    for ts, ev, details, _ in parse_log(log_content, check_c_p_equivalence):
        if ev == 'startup':
            yield from yield_sequences()
            continue

        if ev in ('N', 'n'):
            continue

        (py, begin, end) = details

        if ev not in ('R', '?'):
            seg = f"{py}:{begin}-{end}"
            seqs[seg] += ev
            seq_ts[seg].append(ts)

    yield from yield_sequences()


if __name__ == '__main__':
    from tabulate import tabulate

    args = parse_args()

    seq_count = defaultdict(int)
    for file, rel in tqdm(list(get_coverup_logs(args.suite, args.config))):
        if args.skip and args.skip in str(file):
            continue

        if args.ckpt and not str(file).endswith(f"-{args.ckpt}"):
            print(f"Skipping {file}")
            continue

#        print(rel)

        for seg, seq, _ in get_sequences(file.read_text(), check_c_p_equivalence=args.check_c_p):
            if args.show and args.show == seq:
                print(f"{seg} {seq}")

            seq_count[seq] += 1


    def mktable(data):
        total = sum(data.values())
        for seq, count in sorted(data.items(), key=lambda item: item[1], reverse=True):
            yield seq, count, round(100*count/total, 1)

        yield '(total)', total, None

# all sequences
#    print(tabulate(mktable(seq_count), headers=["seq", "count", "%"]))

# P and C seqs
#    for start in (('P','p'), ('C',)):
#        p_count = defaultdict(int)
#        for seq, count in seq_count.items():
#            if seq[0] in start:
#                seq = start[0] + seq[1:] # p -> P
#                if seq[-1] in ('-', 'T', 'M'):
#                    seq = seq[0] + '..' + seq[-1]
#                p_count[seq] += count
#        print('')
#        print(tabulate(mktable(p_count), headers=["seq", "count", "%"]))

# final states
    end_count = defaultdict(int)
    for seq, count in seq_count.items():
        # When installing missing modules, M isn't a terminal state;
        # don't let it be interpreted as another retry.
        seq = seq.replace("M", "")
        if seq[-1] == 'G':
            end_count[('.' * (len(seq)-1)) + 'G'] += count

    print('')
    print(tabulate(mktable(end_count), headers=["seq", "count", "%"]))

#    end_count = defaultdict(int)
#    for seq, count in seq_count.items():
#        if seq[-1] == 'G':
#            end_count[seq[0] + ('.' * (len(seq)-2)) + 'G'] += count
#
#    print('')
#    print(tabulate(mktable(end_count), headers=["seq", "count", "%"]))
#
#    end_count = defaultdict(int)
#    for seq, count in seq_count.items():
#        if seq[-1] == '*':
#            seq = seq[:-1]
#
#        if seq[-1] in ('F', 'G', 'M'):
#            end_count["~" + seq[-1]] += count
#        else:
#            end_count["." + seq[1:]] += count
#
#    print('')
#    print(tabulate(mktable(end_count), headers=["seq", "count", "%"]))
#
#    end_count = defaultdict(int)
#    for seq, count in seq_count.items():
#        end_count[('~' + seq[-1])] += count
#    print('')
#    print(tabulate(mktable(end_count), headers=["seq", "count", "%"]))

## coverage prompts
#    cov_count = defaultdict(int)
#    for seq, count in seq_count.items():
#        if seq[0] == 'C':
#            cov_count[seq] += count
#
#    print('')
#    print(tabulate(mktable(cov_count), headers=["seq", "count", "%"]))
#
## where 'U' was followed by success
#    pug_count = defaultdict(int)
#    for seq, count in seq_count.items():
#        if 'U' in seq and seq[-1] == 'G':
#            pug_count[seq] += count
#
#    print('')
#    print(tabulate(mktable(pug_count), headers=["seq", "count", "%"]))
#
## where 'U' was followed by failure
#    pux_count = defaultdict(int)
#    for seq, count in seq_count.items():
#        if 'U' in seq and seq[-1] != 'G':
#            pux_count[seq] += count
#
#    print('')
#    print(tabulate(mktable(pux_count), headers=["seq", "count", "%"]))
