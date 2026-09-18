# Real Estate

Projeto interdisciplinar de faculdade com foco no mercado imobiliário.
Infraestrutura provisionada via OpenTofu + KVM, configurada via Ansible.

## Arquitetura

| VM         | Papel                             | Stack        |
| ---------- | --------------------------------- | ------------ |
| generator  | Gera dados imobiliários simulados | Python       |
| processing | Limpa e trata os dados            | R            |
| bigdata    | Data Warehouse / Data Lake        | Python       |
| monitoring | Monitoramento do ambiente         | Docker + k3s |

## Pré-requisitos

- KVM/libvirt instalado e rodando
- OpenTofu instalado
- Chave SSH em `~/.ssh/devops_lab`
- UFW: regra para virbr0 em `/etc/ufw/before.rules`
- libvirt: `firewall_backend = "nftables"` em `/etc/libvirt/network.conf`

## Subir a infraestrutura

```bash
cd iac/
tofu init
tofu apply
```

## Ver IPs das VMs

```bash
sudo virsh net-dhcp-leases default
```

## Acessar uma VM

```bash
ssh -i ~/.ssh/devops_lab devops@<IP>
```

## Gerenciar VMs

```bash
# Listar
sudo virsh list --all

# Iniciar
sudo virsh start generator

# Desligar
sudo virsh shutdown generator

# Iniciar automaticamente no boot
sudo virsh autostart generator
```

## Destruir a infraestrutura

```bash
tofu destroy
```
