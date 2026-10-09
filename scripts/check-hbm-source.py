#!/usr/bin/env python3
"""Compose HBM opt-in with relevant base patches on pristine NVIDIA GSP code.

Only kernel_gsp.c is copied to a temporary tree. This validates source context,
not a full kernel module build, register behavior or hardware stability.
"""
import argparse
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

DRIVER = Path(__file__).resolve().parents[1] / "vendor/cmpunlocker/driver"
GSP = Path("src/nvidia/src/kernel/gpu/gsp/kernel_gsp.c")


def gsp_sections(patch):
    sections = re.split(r"(?m)(?=^--- [ab]/)", patch.read_text())
    return "\n".join(section for section in sections if section.startswith("--- ")
                     and f"+++ b/{GSP}" in section.split("@@", 1)[0])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--version", required=True, choices=(DRIVER / "VERSION").read_text().splitlines())
    args = parser.parse_args()
    if not shutil.which("patch"):
        parser.error("GNU patch is required")
    text = (DRIVER / "build.sh").read_text()
    order = re.search(r"PATCH_ORDER=\(\n(.*?)\n\)", text, re.S)[1].split()
    optional = re.search(r"HBM_PATCH_ORDER=\(\n(.*?)\n\)", text, re.S)[1].split()
    patches = [(name, gsp_sections(DRIVER / "patches" / name)) for name in order + optional]
    with tempfile.TemporaryDirectory(prefix="cmp170-hbm-context-") as tmp:
        target = Path(tmp)
        (target / GSP).parent.mkdir(parents=True)
        shutil.copyfile(args.source / GSP, target / GSP)
        count = 0
        for name, content in patches:
            if not content:
                continue
            command = ["patch", "--batch", "--forward", "-p1"]
            # Preserve the existing base build's context policy; the new
            # optional HBM patch must apply with zero fuzz.
            if name in optional:
                command.append("--fuzz=0")
            result = subprocess.run(command,
                                    input=content, cwd=target, text=True, capture_output=True, timeout=30)
            if result.returncode:
                raise SystemExit(f"FAIL {name} on {args.version}:\n{result.stdout}{result.stderr}")
            count += 1
        code = (target / GSP).read_text()
        for name in ("FBPA_MEM", "FBPA_PLL0", "FBPA_PLL1", "FBPA_PLL2", "FBPA0_PLL"):
            if f'"{name}"' not in code:
                raise SystemExit(f"Missing HBM PLM: {name}")
        if "plmIdx < NV_ARRAY_ELEMENTS(plmTable)" not in code:
            raise SystemExit("HBM loop does not cover all PLM entries")
        print(f"PASS: {args.version}: real kernel_gsp.c, {count} base/optional patch sections; optional HBM fuzz=0")
        print("Context composition only; no kernel build, register writes or GPU memory tests.")


if __name__ == "__main__":
    main()
