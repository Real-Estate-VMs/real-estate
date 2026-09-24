# Real Estate

Projeto interdisciplinar de faculdade com foco no mercado imobiliário.
Infraestrutura provisionada via OpenTofu + KVM, configurada via Ansible.

## Arquitetura

| VM         | Papel                             | Stack        |
| ---------- | --------------------------------- | ------------ |
| generator  | Gera dados imobiliários simulados | Python       |
| processing | Limpa e trata os dados            | R            |
| bigdata    | Data Warehouse / Data Lake        | Python       |
| monitoring | Monitoramento do ambiente         | Grafana + Prometheus |

## Estrutura do repositório

```
real-estate/
├── iac/
│   ├── main.tf           # Provisionamento das VMs (OpenTofu)
│   └── cloud_init.cfg    # Inicialização das VMs (cloud-init)
├── ansible/
│   └── playbooks/        # Configuração automatizada das VMs
├── scripts/
│   └── generator.py      # Geração de dados imobiliários (São Paulo)
├── data/
│   ├── raw/              # CSVs gerados pelo generator
│   └── processed/        # CSVs tratados pelo R
├── .gitignore
├── .env.example
└── README.md
```

## Pré-requisitos

| Dependência | Versão mínima | Finalidade                    |
| ----------- | ------------- | ----------------------------- |
| OpenTofu    | 1.6+          | IaC — provisionamento das VMs |
| KVM/libvirt | 10.0+         | Hypervisor local              |
| QEMU        | 8.0+          | Emulação de hardware          |
| SSH         | —             | Acesso às VMs                 |

**Configurações de sistema necessárias (Arch Linux / UFW):**

- UFW: adicionar regra para `virbr0` em `/etc/ufw/before.rules`
- UFW: `sudo ufw default allow FORWARD` para as VMs acessarem a internet
- libvirt: definir `firewall_backend = "nftables"` em `/etc/libvirt/network.conf`

## Subir a infraestrutura

```bash
cp .env.example .env
# Preencha GITHUB_TOKEN no .env
bash setup.sh
```

Ao final, acesse o Grafana em `http://<IP da VM monitoring>:3000` com as credenciais definidas em `GRAFANA_USER` e `GRAFANA_PASSWORD`.

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
