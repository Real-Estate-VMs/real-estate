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
until sudo virsh net-dhcp-leases default | grep -q "generator"; do
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

echo "==> Configuring VMs..."
ANSIBLE_LOG=$(mktemp)
ANSIBLE_CONFIG=ansible/ansible.cfg ansible-playbook -i ansible/inventory.ini ansible/playbooks/generator.yml \
  --extra-vars "github_token=$GITHUB_TOKEN" > "$ANSIBLE_LOG" 2>&1 &
ANSIBLE_PID=$!
while kill -0 $ANSIBLE_PID 2>/dev/null; do
  printf "."
  sleep 2
done
wait $ANSIBLE_PID
ANSIBLE_STATUS=$?
echo ""
if [ $ANSIBLE_STATUS -ne 0 ]; then
  cat "$ANSIBLE_LOG"
  rm -f "$ANSIBLE_LOG"
  exit 1
fi
grep -E "(PLAY \[|ok=)" "$ANSIBLE_LOG"
rm -f "$ANSIBLE_LOG"

echo "==> Done. Infrastructure is up and running."
