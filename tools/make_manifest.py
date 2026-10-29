"""Write the load time manifest for a new HTS revision drop.

Usage: python3 -m tools.make_manifest [REVISION]
Review the printed counts against the build script output before committing the manifest.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dutydrop import data  # noqa: E402

if __name__ == "__main__":
    d = data.load(revision=sys.argv[1] if len(sys.argv) > 1 else None, check=False)
    print(d.revision, d.counts, data.section301_list_counts(d))
    print("wrote", data.write_manifest(d))
