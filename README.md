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
│   ├── playbooks/        # Configuração automatizada das VMs
│   └── templates/        # Serviços systemd, Grafana (datasources e dashboards)
├── scripts/
│   ├── generator.py      # Geração de dados imobiliários (São Paulo)
│   ├── processing.R      # Limpeza dos dados (roda no GitHub Actions)
│   └── etl.py            # ETL: parquets tratados → Data Warehouse (VM bigdata)
├── sql/
│   └── dw_schema.sql     # Esquema estrela e views OLAP do Data Warehouse
├── notebooks/
│   └── PI_BigData.ipynb  # EDA, OLAP, Machine Learning e Spark (Google Colab)
├── data/
│   ├── raw/              # CSVs gerados pelo generator
│   └── processed/        # Parquets tratados pelo R
├── .gitignore
├── .env.example
└── README.md
```

## Fluxo de dados

```
generator ──CSV──▶ GitHub (data/raw) ──Actions──▶ processing (R) ──parquet──▶ GitHub (data/processed)
                                                                                   │ git pull (a cada 10 min)
                                                                                   ▼
                                Grafana (monitoring) ◀── PostgreSQL ◀── ETL (bigdata) ──▶ Jupyter / Colab
```

1. O **generator** cria de 50 a 200 imóveis a cada 30 minutos e faz push do CSV.
2. O **GitHub Actions** roda no runner da VM processing: o R limpa o CSV e publica um parquet.
3. O **ETL** da VM bigdata roda a cada 10 minutos, carrega os parquets novos no Data Warehouse (esquema estrela em PostgreSQL) e registra cada carga em `dw.etl_carga`.
4. O **Grafana** consulta o Data Warehouse e o **notebook** faz a análise completa.

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

**Ubuntu (AppArmor):** se as VMs não iniciarem com `Failed to lock byte 100`, libere o lock das imagens:

```bash
echo '/var/lib/libvirt/images/** rwk,' | sudo tee -a /etc/apparmor.d/local/abstractions/libvirt-qemu
sudo systemctl reload apparmor
```

## Subir a infraestrutura

```bash
cp .env.example .env
# Preencha GITHUB_TOKEN no .env
bash setup.sh
```

Ao final, acesse o Grafana em `http://<IP da VM monitoring>:3000` com as credenciais definidas em `GRAFANA_USER` e `GRAFANA_PASSWORD`. Há dois dashboards:

- **DevOps Metrics**: CPU, memória, disco e rede das VMs.
- **Mercado Imobiliário SP (Data Warehouse)**: indicadores, mapa de preço por m², roll-up, drill-down, cubo tipo × região, oportunidades e o histórico de cargas do ETL. Os filtros do topo (região, tipo e situação) fazem slice e dice.

## Notebook (Google Colab)

[![Abrir no Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/Real-Estate-VMs/real-estate/blob/main/notebooks/PI_BigData.ipynb)

O notebook `notebooks/PI_BigData.ipynb` segue as 6 etapas da disciplina de Big Data e roda em dois modos, escolhidos automaticamente:

- **Modo `github`** (Colab comum): lê os arquivos do repositório e monta o Data Warehouse em memória (DuckDB). Não precisa das VMs.
- **Modo `dw`** (Colab conectado à VM bigdata): lê o Data Warehouse real em PostgreSQL.

### Conectar o Colab à VM bigdata

O Jupyter da VM bigdata escuta só em `localhost:8888`. Abra um túnel SSH e deixe o terminal aberto:

```bash
ssh -i ~/.ssh/devops_lab -N -L 8888:localhost:8888 devops@<IP da VM bigdata>
```

No Colab, clique em **Conectar ▸ Conectar a um ambiente de execução local** e informe:

```
http://localhost:8888/?token=<JUPYTER_TOKEN do .env>
```

Com o túnel aberto, o Jupyter também pode ser usado direto no navegador, no mesmo endereço. Os notebooks da VM ficam em `/home/devops/workspace`, um clone separado do usado pelo ETL.

## Data Warehouse

Esquema estrela em PostgreSQL na VM bigdata (banco `realestate`, schema `dw`):

| Tabela | Conteúdo |
| --- | --- |
| `fato_imovel` | um registro por imóvel: preço, área, preço por m², condomínio, vendido |
| `dim_localizacao` | bairro → região → cidade → estado |
| `dim_tempo` | data → mês → trimestre → ano (membro "Sem data" para não vendidos) |
| `dim_tipo_imovel` | tipo do imóvel |
| `dim_caracteristicas` | quartos, banheiros, vagas, mobiliado, faixas de área e idade |
| `etl_carga` | histórico de cargas do ETL |

Views OLAP: `vw_imoveis` (cubo achatado), `vw_rollup_localizacao`, `vw_drilldown_tempo` e `vw_cubo_tipo_regiao`.

```bash
# Log do ETL
ssh -i ~/.ssh/devops_lab devops@<IP da VM bigdata> 'journalctl -u etl.service -n 20 -o cat'

# Forçar uma carga agora
ssh -i ~/.ssh/devops_lab devops@<IP da VM bigdata> 'sudo systemctl start etl.service'

# Consultar o DW
ssh -i ~/.ssh/devops_lab devops@<IP da VM bigdata> 'psql -d realestate -c "SELECT * FROM dw.vw_cubo_tipo_regiao"'
```

## Carga histórica

Para gerar um volume maior de uma vez (sem push), use o modo histórico do generator:

```bash
python scripts/generator.py --historico 20000 --saida data/raw/listings_AAAAMMDD_000000.csv
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
