#!/usr/bin/env bash
# Launch recipes/stage_cogs.yaml as a SkyPilot managed job.
# EARTHDATA_TOKEN comes from .env; the kopah keys from the `kopah` AWS profile.
# Extra arguments are passed to `sky jobs launch`, e.g. --env PERIODS=3
set -euo pipefail
cd "$(dirname "$0")/.."

set -a; source .env; set +a
export AWS_ACCESS_KEY_ID=$(aws configure get aws_access_key_id --profile "${AWS_PROFILE:-kopah}")
export AWS_SECRET_ACCESS_KEY=$(aws configure get aws_secret_access_key --profile "${AWS_PROFILE:-kopah}")
unset AWS_PROFILE

pixi run -e sky sky jobs launch recipes/stage_cogs.yaml -y -d \
  --secret EARTHDATA_TOKEN --secret AWS_ACCESS_KEY_ID --secret AWS_SECRET_ACCESS_KEY \
  "$@"
