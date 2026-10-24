"""Module boundaries (section 5.4) enforced with import-linter."""

import configparser
import os
import shutil
import subprocess
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[2]
CONFIG = API_ROOT / ".importlinter"
MODULES_DIR = API_ROOT / "src" / "trovelya" / "modules"
LINT_IMPORTS = shutil.which("lint-imports") or "lint-imports"


def _lint_imports(cwd: Path, pythonpath: Path) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "PYTHONPATH": str(pythonpath)}
    return subprocess.run(  # noqa: S603 — fixed command, test-controlled arguments
        [LINT_IMPORTS, "--config", str(cwd / ".importlinter"), "--no-cache"],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_import_contracts_pass() -> None:
    result = _lint_imports(API_ROOT, API_ROOT / "src")
    assert result.returncode == 0, result.stdout + result.stderr


def test_violation_detected(tmp_path: Path) -> None:
    shutil.copytree(API_ROOT / "src", tmp_path / "src")
    shutil.copy(CONFIG, tmp_path / ".importlinter")
    service = tmp_path / "src" / "trovelya" / "modules" / "orders" / "service.py"
    service.write_text(
        service.read_text() + "\nfrom trovelya.modules.ledger.models import EntryInput  # noqa\n"
    )
    result = _lint_imports(tmp_path, tmp_path / "src")
    assert result.returncode != 0
    assert "BROKEN" in result.stdout


def test_every_module_has_a_contract() -> None:
    parser = configparser.ConfigParser()
    parser.read(CONFIG)
    modules = sorted(
        p.name for p in MODULES_DIR.iterdir() if p.is_dir() and (p / "__init__.py").exists()
    )
    contracts = sorted(
        section.removeprefix("importlinter:contract:module-")
        for section in parser.sections()
        if section.startswith("importlinter:contract:module-")
    )
    assert contracts == modules
