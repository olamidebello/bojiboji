#!/usr/bin/env bash
set -euo pipefail
if [[ ${EUID} -ne 0 ]]; then
  echo 'Run this script as root or with sudo on the Olamidepanel server.' >&2
  exit 1
fi
if ! command -v ansible-playbook >/dev/null 2>&1; then
  echo 'Install Ansible first: apt-get update && apt-get install -y ansible-core' >&2
  exit 1
fi
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
exec ansible-playbook -i "$script_dir/inventory.local.yml" -c local "$script_dir/playbook.yml" --limit localhost "$@"
