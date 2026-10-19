"""Evaluate one 1.1.1.e STL or existing job directory."""
import argparse
from datetime import datetime
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path,
                        help="Job folder containing target.stl/config.yaml, dataset folder, or one STL file")
    parser.add_argument("--config", type=Path, default=ROOT / "train" / "01" / "config.yaml",
                        help="Config used when --input is an STL file")
    parser.add_argument("--checkpoint", type=Path, required=True,
                        help="1.1.1.e trained checkpoint (new layer-priority action schema)")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--official-validator", action="store_true")
    args = parser.parse_args()

    source = args.input.resolve()
    if not source.exists():
        parser.error(f"Input does not exist: {source}")
    checkpoint = args.checkpoint.resolve()
    if not checkpoint.is_file():
        parser.error(f"Checkpoint does not exist: {checkpoint}")

    temp_context = None
    if source.is_file():
        if source.suffix.lower() != ".stl":
            parser.error("A file input must be an STL")
        config = args.config.resolve()
        if not config.is_file():
            parser.error(f"Config does not exist: {config}")
        temp_context = tempfile.TemporaryDirectory(prefix="waam_111e_input_")
        job = Path(temp_context.name) / source.stem
        job.mkdir()
        shutil.copy2(source, job / "target.stl")
        shutil.copy2(config, job / "config.yaml")
        source = job

    output = (args.output or ROOT / "output" / f"test_{source.stem}_{datetime.now():%Y%m%d_%H%M%S}").resolve()
    command = [sys.executable, str(ROOT / "train.py"), "--mode", "eval",
               "--checkpoint", str(checkpoint), "--input", str(source),
               "--output", str(output), "--device", args.device]
    if args.official_validator:
        command.append("--official-validator")
    try:
        print("Running:", subprocess.list2cmdline(command), flush=True)
        return subprocess.run(command, cwd=ROOT, check=False).returncode
    finally:
        if temp_context is not None:
            temp_context.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
