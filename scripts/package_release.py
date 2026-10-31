"""Source-only release; never adds the real runtime directory or secrets."""
from datetime import datetime, timezone
from pathlib import Path
import uuid
import zipfile
from config import ROOT

TOP = ["app.py", "config.py", "repository.py", "schema.sql", "requirements.txt", "requirements-lock.txt",
       "README.md", "run.cmd", "Dockerfile", "compose.yaml", ".dockerignore", ".python-version", ".gitignore", ".gitattributes",
       "requirements-dev.in", "requirements-dev-lock.txt", "mypy.ini", "pytest.ini"]
DIRECTORIES = ["services", "views", "scripts", "tests", "samples", "docs", ".github", "migrations", "prompts"]


def package_release(output_dir=None):
    output_dir = Path(output_dir or ROOT / "outputs")
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / ("qianpin-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S-") + uuid.uuid4().hex[:6] + ".zip")
    paths = [ROOT / p for p in TOP if (ROOT / p).is_file()]
    for directory in DIRECTORIES:
        paths.extend(p for p in (ROOT / directory).rglob("*") if p.is_file()
                     and p.suffix in (".py", ".md", ".csv", ".yml", ".yaml", ".sql", ".txt", ".json") and "__pycache__" not in p.parts)
    paths.extend(ROOT / ".streamlit" / name for name in ("config.toml", "secrets.example.toml"))
    with zipfile.ZipFile(output, "x", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(set(paths)):
            archive.write(path, "qianpin/" + path.relative_to(ROOT).as_posix())
    return output


if __name__ == "__main__":
    print(package_release())
