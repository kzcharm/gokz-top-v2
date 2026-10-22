"""Reports remain available when pytest or the coverage gate fails."""

import os
import subprocess
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    ("test_status", "coverage_status", "expected_status"),
    [(0, 0, 0), (5, 0, 5), (0, 2, 2)],
)
def test_backend_script_preserves_failure_status_and_writes_html(
    tmp_path: Path,
    test_status: int,
    coverage_status: int,
    expected_status: int,
) -> None:
    executable = tmp_path / "coverage"
    executable.write_text("""#!/bin/bash
printf '%s\\n' "$1" >> "$FAKE_COMMAND_LOG"
case "$1" in
  run) exit "$FAKE_TEST_STATUS" ;;
  html) touch "$FAKE_HTML_PATH" ;;
  report) exit "$FAKE_COVERAGE_STATUS" ;;
esac
""")
    executable.chmod(0o755)
    command_log, report = tmp_path / "commands.txt", tmp_path / "index.html"
    environment = {
        **os.environ,
        "PATH": f"{tmp_path}:{os.environ['PATH']}",
        "FAKE_COMMAND_LOG": str(command_log),
        "FAKE_HTML_PATH": str(report),
        "FAKE_TEST_STATUS": str(test_status),
        "FAKE_COVERAGE_STATUS": str(coverage_status),
    }
    script = Path(__file__).resolve().parents[2] / "scripts/test.sh"
    result = subprocess.run(
        ["bash", str(script), "Test coverage"],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == expected_status
    assert report.exists()
    assert command_log.read_text().splitlines() == ["run", "html", "report"]
