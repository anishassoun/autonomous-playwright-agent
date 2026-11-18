"""Module for saving and executing generated Playwright pytest suites."""

from pathlib import Path
import subprocess
import sys
from typing import Any


def get_venv_python() -> str:
    """Resolve the .venv Python executable path, falling back to sys.executable."""
    project_root = Path(__file__).resolve().parent.parent
    win_python = project_root / ".venv" / "Scripts" / "python.exe"
    unix_python = project_root / ".venv" / "bin" / "python"

    if win_python.exists():
        return str(win_python)
    if unix_python.exists():
        return str(unix_python)
    return sys.executable


def run_playwright_test(
    test_code: str,
    filename: str = "generated_tests/test_spec.py",
    timeout: int = 60,
) -> dict[str, Any]:
    """
    Save Python Playwright test code to `filename` and run pytest on it.

    Returns a dictionary containing:
      - passed (bool): True if pytest exited with code 0
      - exit_code (int): Process return code
      - stdout (str): Captured standard output
      - stderr (str): Captured standard error
      - file_path (str): Path to the saved test file
    """
    project_root = Path(__file__).resolve().parent.parent
    file_path = project_root / filename
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(test_code, encoding="utf-8")

    python_exe = get_venv_python()
    cmd = [
        python_exe,
        "-m",
        "pytest",
        str(file_path),
        "--tb=short",
        "-q",
    ]

    try:
        result = subprocess.run(
            cmd,
            cwd=str(project_root),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return {
            "passed": result.returncode == 0,
            "exit_code": result.returncode,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
            "file_path": str(file_path),
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "passed": False,
            "exit_code": -1,
            "stdout": (exc.stdout or "") if isinstance(exc.stdout, str) else "",
            "stderr": f"Test execution timed out after {timeout} seconds.",
            "file_path": str(file_path),
        }
