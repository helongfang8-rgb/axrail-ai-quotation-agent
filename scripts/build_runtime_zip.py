"""Package the reviewed Linux ARM64 dependencies for AgentCore CodeZip."""
import argparse
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("package_dir", type=Path, help="pip --target directory for Python 3.13 Linux ARM64")
    parser.add_argument("--output", type=Path, default=ROOT / "runtime-package.zip")
    args = parser.parse_args()
    if not (args.package_dir / "bedrock_agentcore").is_dir():
        raise SystemExit("The dependency directory does not contain bedrock_agentcore")
    with zipfile.ZipFile(args.output, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in sorted(args.package_dir.rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc":
                archive.write(path, path.relative_to(args.package_dir))
        archive.write(ROOT / "agent_runtime.py", "agent_runtime.py")
        for path in sorted((ROOT / "src/quotation_agent").glob("*.py")):
            archive.write(path, "quotation_agent/" + path.name)
    print(f"{args.output}: {args.output.stat().st_size / 1024 / 1024:.1f} MiB")


if __name__ == "__main__":
    main()
