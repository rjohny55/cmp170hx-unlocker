#!/usr/bin/env python3
"""Check optional P2P patches against real NVIDIA files, not kernel compilation.

--source supplies an existing pristine NVIDIA source tree. Only files touched
by P2P and the intersecting base BAR0 patch are copied into a temporary tree.
The caller's source tree, running driver and host configuration stay unchanged.
"""
import argparse
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
DRIVER = ROOT / "vendor/cmpunlocker/driver"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--version", required=True, choices=(DRIVER / "VERSION").read_text().splitlines())
    args = parser.parse_args()
    if not shutil.which("patch"):
        parser.error("GNU patch is required")
    text = (DRIVER / "build.sh").read_text()
    match = re.search(r"P2P_PATCH_ORDER=\(\n(.*?)\n\)", text, re.S)
    if not match:
        parser.error("P2P_PATCH_ORDER is missing")
    names = ["bar0-pramin-clamp.patch", *match[1].split()]
    patches = [DRIVER / "patches" / name for name in names]
    paths = sorted({line.split()[1][2:] for p in patches for line in p.read_text().splitlines()
                    if line.startswith("+++ b/")})
    with tempfile.TemporaryDirectory(prefix="cmp170-p2p-context-") as tmp:
        target = Path(tmp)
        for name in paths:
            relative = Path(name)
            if relative.is_absolute() or ".." in relative.parts:
                parser.error("unsafe patch target")
            source = args.source / relative
            if not source.is_file():
                parser.error(f"missing pristine NVIDIA file: {source}")
            dest = target / relative
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, dest)
        for patch in patches:
            result = subprocess.run(["patch", "--batch", "--forward", "--fuzz=0", "-p1", "-i", str(patch)],
                                    cwd=target, text=True, capture_output=True, timeout=30)
            if result.returncode:
                raise SystemExit(f"FAIL {patch.name} on declared version {args.version}:\n{result.stdout}{result.stderr}")
        if args.version.startswith("615."):
            code = (target / "src/nvidia/src/kernel/gpu/gpu.c").read_text()
            if "bPcieP2PSkipChipsetCheck = p2pCapsParams.bSkipChipsetCheck" not in code:
                raise SystemExit("615 chipset-check assignment was lost; wrong source or patch")
        print(f"PASS: {args.version}: {len(paths)} real NVIDIA files, {len(patches)} exact-context patches")
        print("Context composition only: no kernel module build, boot or GPU transfer validation.")


if __name__ == "__main__":
    main()
