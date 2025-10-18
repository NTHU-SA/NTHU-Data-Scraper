#!/usr/bin/env bash
# Helper script to run Scrapy spiders locally or inside CI.

set -u

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="python"

declare -a REQUESTED_SPIDERS=()

UBUNTU_GROUP=(
  "nthu_announcements"
  "nthu_buses"
  "nthu_courses"
  "nthu_dining"
)

SELF_HOSTED_GROUP=(
  "nthu_directory"
  "nthu_maps"
  "nthu_newsletters"
)

usage() {
  cat <<'EOF'
Usage: crawl.sh [options] [SPIDER...]

Options:
  --group <name>     Run a predefined group: ubuntu | self-hosted | all
  --python <bin>     Python interpreter to use when invoking Scrapy (default: python)
  -h, --help         Show this help message and exit

If no spiders or groups are provided, the script runs all spiders.
Multiple groups and explicit spider names can be combined.
EOF
}

append_group() {
  case "$1" in
    ubuntu)
      REQUESTED_SPIDERS+=("${UBUNTU_GROUP[@]}")
      ;;
    self-hosted|self_hosted|selfhosted)
      REQUESTED_SPIDERS+=("${SELF_HOSTED_GROUP[@]}")
      ;;
    all)
      REQUESTED_SPIDERS+=("${UBUNTU_GROUP[@]}" "${SELF_HOSTED_GROUP[@]}")
      ;;
    *)
      echo "Unknown group: $1" >&2
      exit 1
      ;;
  esac
}

while (($#)); do
  case "$1" in
    --group)
      shift || { echo "Missing value for --group" >&2; exit 1; }
      append_group "$1"
      ;;
    --python)
      shift || { echo "Missing value for --python" >&2; exit 1; }
      PYTHON_BIN="$1"
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    --*)
      echo "Unknown option: $1" >&2
      exit 1
      ;;
    *)
      REQUESTED_SPIDERS+=("$1")
      ;;
  esac
  shift
done

if [ ${#REQUESTED_SPIDERS[@]} -eq 0 ]; then
  REQUESTED_SPIDERS+=("${UBUNTU_GROUP[@]}" "${SELF_HOSTED_GROUP[@]}")
fi

# Deduplicate while keeping order.
declare -A SEEN=()
declare -a SPIDERS=()
for spider in "${REQUESTED_SPIDERS[@]}"; do
  if [[ -z ${SEEN[$spider]+x} ]]; then
    SPIDERS+=("$spider")
    SEEN[$spider]=1
  fi
done

SUCCESS_COUNT=0
FAIL_COUNT=0
declare -a FAILED_SPIDERS=()

echo "Running ${#SPIDERS[@]} spider(s)"

for spider in "${SPIDERS[@]}"; do
  printf '\n=== Crawling %s ===\n' "$spider"
  if "$PYTHON_BIN" -m scrapy crawl "$spider"; then
    ((SUCCESS_COUNT++))
  else
    ((FAIL_COUNT++))
    FAILED_SPIDERS+=("$spider")
  fi
done

if [ $FAIL_COUNT -gt 0 ]; then
  printf '\nCompleted with %d failure(s): %s\n' "$FAIL_COUNT" "${FAILED_SPIDERS[*]}" >&2
  exit 1
fi

printf '\nAll spiders completed successfully (%d run).\n' "$SUCCESS_COUNT"
