"""A stand-in for LitScout's `abstracts` command, run by the tests as ABSTRACTS_COMMAND.

Reads JSON Lines from stdin ({"id", "doi"?, "arxiv"?, "title"?}) and prints one
line per input, in order: {"id", "abstract", "source"}. $FAKE_ABSTRACTS names a
JSON file {id: [abstract, source]}; ids not in it get null and null.
$FAKE_ABSTRACTS_LOG, when set, gets the input lines as they came.
$FAKE_ABSTRACTS_FAIL makes the call fail with that text on stderr;
$FAKE_ABSTRACTS_GARBLE replaces the second output line with that text.
"""

import json
import os
import sys
from pathlib import Path


def main():
    text = sys.stdin.read()
    if os.environ.get("FAKE_ABSTRACTS_LOG"):
        with open(os.environ["FAKE_ABSTRACTS_LOG"], "a", encoding="utf-8") as log:
            log.write(text)
    if os.environ.get("FAKE_ABSTRACTS_FAIL"):
        print(os.environ["FAKE_ABSTRACTS_FAIL"], file=sys.stderr)
        return 2
    known_file = os.environ.get("FAKE_ABSTRACTS")
    known = json.loads(Path(known_file).read_text(encoding="utf-8")) if known_file else {}
    for n, line in enumerate(text.splitlines()):
        paper_id = json.loads(line)["id"]
        abstract, source = known.get(paper_id, [None, None])
        garble = os.environ.get("FAKE_ABSTRACTS_GARBLE")
        print(garble if garble and n == 1 else json.dumps({"id": paper_id, "abstract": abstract, "source": source}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
