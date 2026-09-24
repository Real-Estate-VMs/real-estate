#!/bin/bash
set -e

if [ ! -f .env ]; then
  echo "ERROR: .env not found. Copy .env.example and fill in the values."
  exit 1
fi

source .env

if [ -z "$GITHUB_TOKEN" ]; then
  echo "ERROR: GITHUB_TOKEN is not set in .env"
  exit 1
fi

echo "==> Applying infrastructure..."
cd iac/
tofu apply -auto-approve 2>&1 | grep -E "(name\s+=|Apply complete|Error)"
cd ..

echo "==> Waiting for VMs to get IP addresses..."
until sudo virsh net-dhcp-leases default | grep -q "generator" && \
      sudo virsh net-dhcp-leases default | grep -q "processing" && \
      sudo virsh net-dhcp-leases default | grep -q "bigdata" && \
      sudo virsh net-dhcp-leases default | grep -q "monitoring"; do
  echo "    still waiting..."
  sleep 10
done
echo "    All VMs are up."

echo "==> Updating Ansible inventory..."
bash scripts/gen_inventory.sh

echo "==> Adding SSH key to agent..."
pkill ssh-agent 2>/dev/null || true
eval "$(ssh-agent -s)" > /dev/null
ssh-add ~/.ssh/devops_lab

run_playbook() {
  local name=$1
  local playbook=$2
  echo "==> Configuring $name..."
  local log
  log=$(mktemp)
  ANSIBLE_CONFIG=ansible/ansible.cfg ansible-playbook -i ansible/inventory.ini "$playbook" \
    --extra-vars "github_token=$GITHUB_TOKEN grafana_user=${GRAFANA_USER:-devops} grafana_password=${GRAFANA_PASSWORD:-admin}" > "$log" 2>&1 &
  local pid=$!
  while kill -0 $pid 2>/dev/null; do
    printf "."
    sleep 2
  done
  local status=0
  wait $pid || status=$?
  echo ""
  if [ $status -ne 0 ] || grep -qE "(unreachable=[1-9]|failed=[1-9])" "$log"; then
    cat "$log"
    rm -f "$log"
    exit 1
  fi
  grep -E "(PLAY \[|ok=)" "$log"
  rm -f "$log"
}

run_playbook "generator"  ansible/playbooks/generator.yml
run_playbook "processing" ansible/playbooks/processing.yml
run_playbook "bigdata"    ansible/playbooks/bigdata.yml
run_playbook "monitoring" ansible/playbooks/monitoring.yml

echo "==> Done. Infrastructure is up and running."
