from pathlib import Path
from coverup.logreader import parse_log_raw
from sequences import get_coverup_logs
from datetime import datetime
import re

def parse_args():
    import argparse
    ap = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    ap.add_argument('--suite', choices=['good', 'cm', '1_0', 'mutap'], default='cm',
                    help='suite of modules to compare')

    ap.add_argument('--config', type=str, default='gpt4o-v2', help='specify a (non-default) configuration to use')
    return ap.parse_args()


def coverup_log(log_content: str):
    file_time = 0
    start = end = None
    for ts, ctx, content in parse_log_raw(log_content):
        if ctx == 'startup':
            if start and end:
                diff = datetime.fromisoformat(end) - datetime.fromisoformat(start)
                file_time += diff.total_seconds()
            start = ts
            end = None
            continue

        end = ts

    if start and end:
        diff = datetime.fromisoformat(end) - datetime.fromisoformat(start)
        file_time += diff.total_seconds()

    return file_time


def count_beans():
    args = parse_args()

    total_time = 0
    for file, rel in sorted(get_coverup_logs(args.suite, args.config)):
        file_time = coverup_log(file.read_text())
        print(f"{str(rel):<70} {file_time=:,}")

        total_time += file_time

    print(f"{total_time:,}s = {total_time/3600:,.1f}h total")

if __name__ == '__main__':
    count_beans()
