#!/usr/bin/env bash

set -e
set -x

test_status=0
coverage run -m pytest tests/ || test_status=$?
coverage html --fail-under=0 --title "${*:-coverage}"
coverage report
exit "$test_status"
