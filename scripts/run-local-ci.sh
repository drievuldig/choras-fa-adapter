#!/usr/bin/env bash
set -euo pipefail

if ! command -v act >/dev/null 2>&1; then
  echo "Error: act is not installed."
  exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "Error: docker is not installed."
  exit 1
fi

if ! docker info >/dev/null 2>&1; then
  echo "Error: docker daemon is not running."
  exit 1
fi

act -j test
