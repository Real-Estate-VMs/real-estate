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

echo "==> Provisioning VMs..."
cd iac/
tofu apply -auto-approve
cd ..

echo "==> Waiting for VMs to get IP addresses..."
until sudo virsh net-dhcp-leases default | grep -q "generator"; do
  echo "    still waiting..."
  sleep 10
done
echo "    All VMs are up."

echo "==> Generating Ansible inventory..."
bash scripts/gen_inventory.sh

echo "==> Adding SSH key to agent..."
eval "$(ssh-agent -s)"
ssh-add ~/.ssh/devops_lab

echo "==> Configuring generator VM..."
ANSIBLE_CONFIG=ansible/ansible.cfg ansible-playbook -i ansible/inventory.ini ansible/playbooks/generator.yml \
  --extra-vars "github_token=$GITHUB_TOKEN"

echo "==> Done. Generator is running."
