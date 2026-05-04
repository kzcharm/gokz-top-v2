#!/usr/bin/env bash

set -euo pipefail

semver_tag_regex='^v[0-9]+\.[0-9]+\.[0-9]+$'

if [ -n "${VITE_APP_VERSION:-}" ]; then
  printf '%s\n' "${VITE_APP_VERSION}"
  exit 0
fi

exact_tag="$(
  git tag --points-at HEAD --list 'v*.*.*' \
    | grep -E "${semver_tag_regex}" \
    | head -n 1 \
    || true
)"

if [ -n "${exact_tag}" ]; then
  printf '%s\n' "${exact_tag}"
  exit 0
fi

latest_tag="$(
  git tag --merged HEAD --list 'v*.*.*' --sort=-v:refname \
    | grep -E "${semver_tag_regex}" \
    | head -n 1 \
    || true
)"

short_sha="$(git rev-parse --short=7 HEAD)"

if [ -n "${latest_tag}" ]; then
  printf '%s+%s\n' "${latest_tag}" "${short_sha}"
  exit 0
fi

printf '%s\n' "${short_sha}"
