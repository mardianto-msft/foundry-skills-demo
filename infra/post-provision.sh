#!/usr/bin/env sh
# Export the latest azd environment values after infrastructure provisioning.

set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
PROJECT_DIR="$(CDPATH= cd -- "${SCRIPT_DIR}/.." && pwd)"
ENV_FILE="${PROJECT_DIR}/.env"
TEMP_FILE="$(mktemp "${PROJECT_DIR}/.env.tmp.XXXXXX")"

cleanup() {
  rm -f "${TEMP_FILE}"
}
trap cleanup EXIT INT TERM

if [ -n "${AZURE_ENV_NAME:-}" ]; then
  echo "Exporting azd environment '${AZURE_ENV_NAME}' to ${ENV_FILE}"
  azd env get-values -e "${AZURE_ENV_NAME}" > "${TEMP_FILE}"
else
  echo "Exporting current azd environment to ${ENV_FILE}"
  azd env get-values > "${TEMP_FILE}"
fi

mv "${TEMP_FILE}" "${ENV_FILE}"
trap - EXIT INT TERM

echo "Wrote ${ENV_FILE}"
echo ""
echo "Foundry infrastructure is provisioned and .env has been refreshed."
echo ""
echo "Publish the skills and run the demo:"
echo "  python -m src.skills.publish_skill"
echo "  python -m src.agent.run_agent --log sample_logs/web.log"
echo "  python -m src.agent.run_agent --log sample_logs/k8s.log"