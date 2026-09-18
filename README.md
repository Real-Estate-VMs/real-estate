# 🛠️ DevOps Lab — OpenTofu + Libvirt Cheat Sheet

Guia rápido dos comandos mais usados no laboratório `devops-2026`.

---

## 📦 OpenTofu

O **OpenTofu** é usado para criar e gerenciar a infraestrutura através dos arquivos `.tf`.

### 🔎 `tofu validate`

Verifica se os arquivos `.tf` estão escritos corretamente e se a configuração é válida.

```bash
tofu validate
```

Use depois de fazer alterações no código.

---

### 📋 `tofu plan`

Mostra o que o OpenTofu pretende criar, alterar ou remover.

```bash
tofu plan
```

> Não altera nada na infraestrutura. É apenas uma prévia.

---

### 🚀 `tofu apply`

Aplica as alterações planejadas e cria/modifica a infraestrutura.

```bash
tofu apply
```

O OpenTofu normalmente pede confirmação antes de executar.

Para confirmar automaticamente:

```bash
tofu apply -auto-approve
```

⚠️ Use `-auto-approve` com cuidado, principalmente em ambientes reais.

---

### 💥 `tofu destroy`

Remove a infraestrutura que foi criada pelo OpenTofu.

```bash
tofu destroy
```

Para confirmar automaticamente:

```bash
tofu destroy -auto-approve
```

⚠️ Este comando pode apagar VMs, discos e outros recursos gerenciados pelo projeto.

---

### 🔄 `tofu refresh`

Atualiza o estado do OpenTofu com o que existe atualmente na infraestrutura.

```bash
tofu refresh
```

> Em versões atuais, normalmente é preferível usar `tofu plan -refresh-only` quando a intenção é apenas atualizar/verificar o estado.

---

### 📊 `tofu show`

Mostra informações do estado atual da infraestrutura.

```bash
tofu show
```

Também pode mostrar um arquivo de estado específico:

```bash
tofu show terraform.tfstate
```

---

### 📦 `tofu state list`

Lista os recursos que o OpenTofu conhece no arquivo de estado.

```bash
tofu state list
```

Exemplo:

```text
libvirt_volume.base
libvirt_volume.disk[0]
libvirt_domain.vm[0]
libvirt_domain.vm[1]
```

---

### 🔍 `tofu state show`

Mostra detalhes de um recurso específico do estado.

```bash
tofu state show NOME_DO_RECURSO
```

Exemplo:

```bash
tofu state show libvirt_domain.vm[0]
```

---

### 🧹 `tofu fmt`

Formata automaticamente os arquivos `.tf`.

```bash
tofu fmt
```

Para formatar todos os arquivos e subdiretórios:

```bash
tofu fmt -recursive
```

---

### 🔧 `tofu init`

Inicializa o projeto.

```bash
tofu init
```

É normalmente o primeiro comando executado depois de clonar ou criar um projeto OpenTofu.

Ele prepara providers, módulos e arquivos necessários.

Se precisar atualizar providers:

```bash
tofu init -upgrade
```

---

### 📌 `tofu providers`

Mostra os providers utilizados pelo projeto.

```bash
tofu providers
```

---

### 📄 `tofu output`

Mostra os outputs definidos no projeto.

```bash
tofu output
```

Para mostrar um output específico:

```bash
tofu output nome_do_output
```

---

## 🖥️ Libvirt / virsh

O `virsh` é utilizado para administrar as máquinas virtuais e recursos do **libvirt/KVM**.

Como seu laboratório está utilizando a conexão do sistema, normalmente usamos:

```bash
sudo virsh
```

---

### 📋 `sudo virsh list --all`

Lista todas as máquinas virtuais, incluindo as desligadas.

```bash
sudo virsh list --all
```

Exemplo:

```text
 Id   Name       State
--------------------------
 -    devops-1   shut off
 -    devops-2   shut off
```

Sem `--all`, normalmente são mostradas apenas as VMs em execução:

```bash
sudo virsh list
```

---

### ▶️ Iniciar uma VM

```bash
sudo virsh start devops-1
```

---

### ⏹️ Desligar uma VM

Desligamento normal:

```bash
sudo virsh shutdown devops-1
```

---

### 💀 Forçar desligamento

Se a VM não responder:

```bash
sudo virsh destroy devops-1
```

> Apesar do nome `destroy`, ele **não apaga a VM**. Ele apenas força o desligamento.

---

### 🔄 Reiniciar uma VM

```bash
sudo virsh reboot devops-1
```

---

### 🗑️ Remover a definição da VM

Remove a VM do libvirt:

```bash
sudo virsh undefine devops-1
```

⚠️ Isso remove a definição da máquina, mas **não necessariamente remove os discos `.qcow2`**.

---

## 💾 Storage Pools

### 📋 Listar os pools

```bash
sudo virsh pool-list --all
```

No seu laboratório:

```text
Name      State    Autostart
-------------------------------
default   active   yes
```

---

### 📦 Listar volumes

```bash
sudo virsh vol-list default
```

Exemplo:

```text
devops-1-cloudinit.iso
devops-1.qcow2
devops-2-cloudinit.iso
devops-2.qcow2
ubuntu-24.04-base.qcow2
```

---

### 🗑️ Remover um volume

```bash
sudo virsh vol-delete NOME_DO_VOLUME --pool default
```

Exemplo:

```bash
sudo virsh vol-delete devops-2-cloudinit.iso --pool default
```

---

## 🧨 Limpar uma VM completamente

Se quiser remover uma VM `devops-X` junto com seu disco e Cloud-Init:

### 1. Desligar

```bash
sudo virsh destroy devops-1
```

### 2. Remover a definição

```bash
sudo virsh undefine devops-1
```

### 3. Remover o disco

```bash
sudo virsh vol-delete devops-1.qcow2 --pool default
```

### 4. Remover o Cloud-Init

```bash
sudo virsh vol-delete devops-1-cloudinit.iso --pool default
```

---

## 🧹 Remover TODAS as VMs `devops-*`

⚠️ **CUIDADO:** os comandos abaixo removem todas as VMs cujo nome começa com `devops-`.

### Desligar:

```bash
for vm in $(sudo virsh list --all --name | grep '^devops-'); do
    sudo virsh destroy "$vm" 2>/dev/null
done
```

### Remover as definições:

```bash
for vm in $(sudo virsh list --all --name | grep '^devops-'); do
    sudo virsh undefine "$vm"
done
```

### Remover discos e Cloud-Init:

```bash
for vol in $(sudo virsh vol-list default --name | grep '^devops-'); do
    sudo virsh vol-delete "$vol" --pool default
done
```

⚠️ Isso também remove os arquivos `.qcow2` das VMs `devops-*`.

A imagem base:

```text
ubuntu-24.04-base.qcow2
```

não será removida porque não começa com `devops-`.

---

# 🔄 Fluxo recomendado do laboratório

Quando alterar algum arquivo `.tf`:

```bash
tofu fmt
```

Depois:

```bash
tofu validate
```

Depois:

```bash
tofu plan
```

Se estiver tudo correto:

```bash
tofu apply
```

Fluxo resumido:

```text
┌─────────────┐
│  Editar .tf │
└──────┬──────┘
       ↓
┌─────────────┐
│  tofu fmt   │
└──────┬──────┘
       ↓
┌─────────────┐
│tofu validate│
└──────┬──────┘
       ↓
┌─────────────┐
│  tofu plan  │
└──────┬──────┘
       ↓
┌─────────────┐
│ tofu apply  │
└─────────────┘
```

---

# 🚨 Quando algo der errado

### Ver as VMs

```bash
sudo virsh list --all
```

### Ver os volumes

```bash
sudo virsh vol-list default
```

### Ver os pools

```bash
sudo virsh pool-list --all
```

### Ver o estado do OpenTofu

```bash
tofu show
```

### Ver os recursos conhecidos pelo OpenTofu

```bash
tofu state list
```

---

# ⭐ Comandos para decorar

### OpenTofu

```bash
tofu init
tofu fmt
tofu validate
tofu plan
tofu apply
tofu destroy
tofu show
tofu state list
```

### Libvirt

```bash
sudo virsh list --all
sudo virsh start NOME
sudo virsh shutdown NOME
sudo virsh destroy NOME
sudo virsh undefine NOME
sudo virsh pool-list --all
sudo virsh vol-list default
sudo virsh vol-delete VOLUME --pool default
```

---

## 💡 Regra prática

Antes de apagar qualquer coisa:

```bash
sudo virsh list --all
sudo virsh vol-list default
```

Antes de aplicar mudanças:

```bash
tofu validate
tofu plan
```

E somente depois:

```bash
tofu apply
```
