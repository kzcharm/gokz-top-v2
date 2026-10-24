"""Exercise launcher prompts with mocked Docker commands, without a database."""

import os
import subprocess
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[3]

MOCK_STARTUP = r"""
set -euo pipefail
source "$ROOT_DIR/scripts/dev-common.sh"
ensure_compose_local_defaults() { :; }
ensure_docker_cli() { return 0; }
read_dotenv_value() { :; }
kill_port_processes_with_confirmation() { :; }
check_backend_migrations() { echo 'MIGRATIONS_CHECKED'; }
docker() {
  case "$*" in
    info) return 0 ;;
    'compose ps -q db') printf '%s\n' "$LOCAL_DB" ;;
    'ps --no-trunc -q --filter publish=5432')
      printf '%s\n' "$CONFLICTS"
      ;;
    'inspect --format {{.Name}} '*) printf '/other-project-%s\n' "${@: -1}" ;;
    'inspect --format {{ index .Config.Labels "com.docker.compose.service" }} '*)
      echo db
      ;;
    'inspect --format {{ index .Config.Labels "com.docker.compose.project.working_dir" }} '*)
      echo /other-project
      ;;
    'inspect --format {{ index .Config.Labels "com.docker.compose.project" }} '*)
      echo other-project
      ;;
    'inspect --format {{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}} '* )
      echo healthy
      ;;
    'stop --time 20 '*) echo "STOPPED:${@: -1}" >&2 ;;
    'compose up -d db') LOCAL_DB=local-db; echo 'STARTED_LOCAL_DB' >&2 ;;
    *) echo "Unexpected Docker call: $*" >&2; return 1 ;;
  esac
}
DEV_BACKEND_PORT=8000
prepare_backend_dev
echo STARTUP_COMPLETE
"""


class DevCommonTests(unittest.TestCase):
    def run_startup(
        self, answers: str, *, conflicts: str = "foreign-db", local_db: str = ""
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", "-c", MOCK_STARTUP],
            input=answers,
            capture_output=True,
            text=True,
            timeout=5,
            env={
                **os.environ,
                "ROOT_DIR": str(ROOT_DIR),
                "LOCAL_DB": local_db,
                "CONFLICTS": conflicts,
                "GEOIPUPDATE_ACCOUNT_ID": "",
                "GEOIPUPDATE_LICENSE_KEY": "",
            },
        )

    def test_accepting_conflict_stops_container_and_continues(self) -> None:
        result = self.run_startup("y\n", local_db="local-db")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("STOPPED:foreign-db", result.stderr)
        self.assertIn("STARTUP_COMPLETE", result.stdout)

    def test_each_conflict_reads_a_separate_answer(self) -> None:
        result = self.run_startup(
            "invalid\nyes\ny\n", conflicts="foreign-one\nforeign-two"
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Please answer y or n.", result.stdout)
        self.assertIn("STOPPED:foreign-one", result.stderr)
        self.assertIn("STOPPED:foreign-two", result.stderr)
        self.assertIn("STARTED_LOCAL_DB", result.stderr)
        self.assertIn("STARTUP_COMPLETE", result.stdout)

    def test_declining_second_conflict_leaves_it_running(self) -> None:
        result = self.run_startup("y\nn\n", conflicts="foreign-one\nforeign-two")
        self.assertEqual(result.returncode, 1)
        self.assertIn("STOPPED:foreign-one", result.stderr)
        self.assertNotIn("STOPPED:foreign-two", result.stderr)
        self.assertNotIn("STARTED_LOCAL_DB", result.stderr)

    def test_declining_or_missing_input_aborts_without_stopping(self) -> None:
        for answers in ("n\n", "\n", ""):
            with self.subTest(answers=answers):
                result = self.run_startup(answers)
                self.assertEqual(result.returncode, 1)
                self.assertIn("Aborting because port 5432", result.stdout)
                self.assertNotIn("STOPPED:", result.stderr)
                self.assertNotIn("STARTED_LOCAL_DB", result.stderr)

    def test_existing_local_database_needs_no_confirmation(self) -> None:
        result = self.run_startup("", conflicts="local-db", local_db="local-db")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Local db already running.", result.stdout)
        self.assertIn("STARTUP_COMPLETE", result.stdout)
        self.assertNotIn("STOPPED:", result.stderr)


MOCK_MIGRATIONS = r"""
set -euo pipefail
source "$ROOT_DIR/scripts/dev-common.sh"
worker_running=yes
ps() {
  printf '%s\n' \
    '101 1 /project/.venv/bin/python3 -c from multiprocessing.spawn import spawn_main; spawn_main() --multiprocessing-fork' \
    '102 50 /project/.venv/bin/python3 -c from multiprocessing.spawn import spawn_main; spawn_main() --multiprocessing-fork' \
    '103 1 /other/.venv/bin/python3 -c from multiprocessing.spawn import spawn_main; spawn_main() --multiprocessing-fork' \
    '104 1 /project/.venv/bin/python3 unrelated.py'
}
lsof() {
  if [[ "$*" == *'-p 103 '* ]]; then
    echo n/other/backend
  else
    echo "n$ROOT_DIR/backend"
  fi
}
sleep() { :; }
kill() {
  if [[ "${1-}" == '-0' ]]; then
    [[ "$worker_running" == yes ]]
    return
  fi
  echo "SIGNAL:$*"
  if [[ "$STUBBORN" != yes || "${1-}" == '-KILL' ]]; then
    worker_running=no
  fi
}
uv() {
  case "$*" in
    'run alembic current --check-heads') [[ "$UP_TO_DATE" == yes ]] ;;
    'run alembic upgrade head') echo UPGRADED ;;
    *) return 1 ;;
  esac
}
check_backend_migrations
echo STARTUP_COMPLETE
"""


class MigrationStartupTests(unittest.TestCase):
    def run_migrations(
        self, answers: str, *, stubborn: bool = False, up_to_date: bool = False
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", "-c", MOCK_MIGRATIONS],
            input=answers,
            capture_output=True,
            text=True,
            timeout=5,
            env={
                **os.environ,
                "ROOT_DIR": str(ROOT_DIR),
                "STUBBORN": "yes" if stubborn else "no",
                "UP_TO_DATE": "yes" if up_to_date else "no",
            },
        )

    def test_stops_only_this_projects_orphan_before_upgrade(self) -> None:
        result = self.run_migrations("y\ny\n")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("SIGNAL:101", result.stdout)
        for pid in (102, 103, 104):
            self.assertNotIn(f"SIGNAL:{pid}", result.stdout)
        self.assertLess(
            result.stdout.index("SIGNAL:101"), result.stdout.index("UPGRADED")
        )

    def test_force_stops_unresponsive_orphan(self) -> None:
        result = self.run_migrations("y\ny\n", stubborn=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("SIGNAL:-KILL 101", result.stdout)
        self.assertIn("UPGRADED", result.stdout)

    def test_declining_or_eof_aborts_before_upgrade_or_startup(self) -> None:
        for answers in ("n\n", "", "y\nn\n", "y\n"):
            with self.subTest(answers=answers):
                result = self.run_migrations(answers)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn("SIGNAL:", result.stdout)
                self.assertNotIn("UPGRADED", result.stdout)
                self.assertNotIn("STARTUP_COMPLETE", result.stdout)

    def test_current_database_needs_no_worker_cleanup(self) -> None:
        result = self.run_migrations("", up_to_date=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("SIGNAL:", result.stdout)
        self.assertNotIn("UPGRADED", result.stdout)
        self.assertIn("STARTUP_COMPLETE", result.stdout)


if __name__ == "__main__":
    unittest.main()
