"""A stand-in for LitScout's `watch` command, run by the tests as FEED_COMMAND.

Prints the lines of $FAKE_FEED_PAPERS (JSON Lines) whose `published` is on or
after --since; lines that are not JSON objects are printed as they are, so
tests can feed invalid lines through. $FAKE_FEED_LOG, when set, gets one JSON
line per call with the arguments; $FAKE_FEED_FAIL makes the call fail with
that text on stderr.
"""

import argparse
import json
import os
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--since", required=True)
    parser.add_argument("--venues", required=True)
    args = parser.parse_args()
    if os.environ.get("FAKE_FEED_LOG"):
        with open(os.environ["FAKE_FEED_LOG"], "a", encoding="utf-8") as log:
            log.write(json.dumps({"since": args.since, "venues": args.venues}) + "\n")
    if os.environ.get("FAKE_FEED_FAIL"):
        print(os.environ["FAKE_FEED_FAIL"], file=sys.stderr)
        return 2
    json.loads(Path(args.venues).read_text(encoding="utf-8"))
    for line in Path(os.environ["FAKE_FEED_PAPERS"]).read_text(encoding="utf-8").splitlines():
        try:
            paper = json.loads(line)
        except ValueError:
            print(line)
            continue
        if not isinstance(paper, dict) or str(paper.get("published", "")) >= args.since:
            print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
