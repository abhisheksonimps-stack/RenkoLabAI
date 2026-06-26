#!/usr/bin/env bash

set -euo pipefail

if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env from example"
else
  echo ".env already exists"
fi

echo "Bootstrap complete"
