#!/bin/bash
# Generates ansible/inventory.ini from current DHCP leases.
# Run this after `tofu apply` to update the inventory automatically.

INVENTORY="$(dirname "$0")/../ansible/inventory.ini"
SSH_KEY="~/.ssh/devops_lab"

get_ip() {
  sudo virsh net-dhcp-leases default \
    | awk -v host="$1" '$6 == host || $7 == host"*" {print $5}' \
    | cut -d'/' -f1 \
    | tail -1
}

GENERATOR_IP=$(get_ip "generator")
PROCESSING_IP=$(get_ip "processing")
BIGDATA_IP=$(get_ip "bigdata")
MONITORING_IP=$(get_ip "monitoring")

for name in GENERATOR PROCESSING BIGDATA MONITORING; do
  var="${name}_IP"
  if [ -z "${!var}" ]; then
    echo "[WARN] Could not find IP for ${name,,} — is the VM running?"
  fi
done

cat > "$INVENTORY" <<EOF
[generator]
${GENERATOR_IP:-MISSING} ansible_user=devops ansible_ssh_private_key_file=${SSH_KEY}

[processing]
${PROCESSING_IP:-MISSING} ansible_user=devops ansible_ssh_private_key_file=${SSH_KEY}

[bigdata]
${BIGDATA_IP:-MISSING} ansible_user=devops ansible_ssh_private_key_file=${SSH_KEY}

[monitoring]
${MONITORING_IP:-MISSING} ansible_user=devops ansible_ssh_private_key_file=${SSH_KEY}
EOF

echo "Inventory written to $INVENTORY"
cat "$INVENTORY"
