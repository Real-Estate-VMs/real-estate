#!/bin/bash
# Atalhos para usar o notebook PI_BigData na VM bigdata.
#
#   bash scripts/notebook.sh abrir   Abre o túnel SSH, espera o Jupyter e mostra o link (padrão)
#   bash scripts/notebook.sh html    Executa o notebook na VM e baixa um HTML com todos os resultados
#   bash scripts/notebook.sh status  Mostra se a VM, o Jupyter e o túnel estão de pé
set -u

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SSH_KEY="$HOME/.ssh/devops_lab"
PORTA="${JUPYTER_PORTA:-8888}"

# Token e IP: do .env e do inventário do Ansible (gerado pelo setup.sh)
JUPYTER_TOKEN="realestate-lab"
if [ -f "$ROOT/.env" ]; then
  valor=$(grep -E '^JUPYTER_TOKEN=' "$ROOT/.env" | cut -d= -f2- | tr -d '\r"'"'"'')
  [ -n "$valor" ] && JUPYTER_TOKEN="$valor"
fi
IP=$(grep -A1 '^\[bigdata\]' "$ROOT/ansible/inventory.ini" 2>/dev/null | tail -1 | awk '{print $1}')
if [ -z "$IP" ] || [ "$IP" = "MISSING" ]; then
  echo "ERRO: não achei o IP da VM bigdata em ansible/inventory.ini. Rode 'bash setup.sh' primeiro."
  exit 1
fi

SSH_OPTS=(-i "$SSH_KEY" -o BatchMode=yes -o ConnectTimeout=8 -o StrictHostKeyChecking=no
          -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR)
URL="http://localhost:${PORTA}/?token=${JUPYTER_TOKEN}"

vm_de_pe() { ssh "${SSH_OPTS[@]}" "devops@$IP" true 2>/dev/null; }
tunel_aberto() { curl -s -o /dev/null --max-time 3 "http://localhost:${PORTA}/api"; }

exige_vm() {
  if ! vm_de_pe; then
    echo "ERRO: a VM bigdata ($IP) não responde por SSH."
    echo "      Veja se ela está ligada: virsh -c qemu:///system list --all"
    exit 1
  fi
}

case "${1:-abrir}" in
  status)
    vm_de_pe && echo "VM bigdata ($IP): ok" || echo "VM bigdata ($IP): SEM RESPOSTA"
    vm_de_pe && ssh "${SSH_OPTS[@]}" "devops@$IP" 'echo "Jupyter: $(systemctl is-active jupyter)"; echo "PostgreSQL: $(systemctl is-active postgresql)"'
    tunel_aberto && echo "Túnel local (porta $PORTA): aberto" || echo "Túnel local (porta $PORTA): fechado"
    ;;

  abrir)
    exige_vm
    if tunel_aberto; then
      echo "O túnel já está aberto na porta $PORTA."
    else
      ssh "${SSH_OPTS[@]}" -f -N -o ExitOnForwardFailure=yes -L "${PORTA}:localhost:8888" "devops@$IP" || {
        echo "ERRO: não consegui abrir o túnel (a porta $PORTA já está em uso?)."
        echo "      Use outra porta: JUPYTER_PORTA=8899 bash scripts/notebook.sh abrir"
        exit 1
      }
      for _ in $(seq 1 15); do tunel_aberto && break; sleep 1; done
      tunel_aberto || { echo "ERRO: o túnel abriu, mas o Jupyter não respondeu."; exit 1; }
    fi
    cat <<EOF

Pronto! O Jupyter da VM bigdata está disponível em:

  Navegador : $URL
  Colab     : Conectar > "Conectar a um ambiente de execução local" > cole o link acima
              https://colab.research.google.com/github/Real-Estate-VMs/real-estate/blob/main/notebooks/PI_BigData.ipynb

O túnel fica rodando em segundo plano. Para fechá-lo:  pkill -f "L ${PORTA}:localhost:8888"
EOF
    command -v xdg-open >/dev/null 2>&1 && [ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ] && xdg-open "$URL" >/dev/null 2>&1 &
    ;;

  html)
    exige_vm
    SAIDA="${2:-$ROOT/notebooks/PI_BigData.html}"
    echo "Executando o notebook na VM (leva alguns minutos; o ML roda em ~1 min)..."
    ssh "${SSH_OPTS[@]}" "devops@$IP" '
      set -e
      cd ~/repo && git pull --ff-only -q
      cd ~/workspace && git pull --ff-only -q 2>/dev/null || echo "(workspace com alterações locais: usando a versão que está lá)"
      export DW_DSN=dbname=realestate REPO_LOCAL=$HOME/repo SPARK_DRIVER_MEMORY=1g
      ~/venv/bin/jupyter nbconvert --to html --execute --ExecutePreprocessor.timeout=1800 \
        --output /tmp/PI_BigData.html notebooks/PI_BigData.ipynb >/tmp/nbconvert.log 2>&1 || { tail -20 /tmp/nbconvert.log; exit 1; }
    ' || { echo "ERRO: a execução do notebook falhou."; exit 1; }
    scp -q "${SSH_OPTS[@]}" "devops@$IP:/tmp/PI_BigData.html" "$SAIDA" && echo "HTML gerado: $SAIDA"
    ;;

  *)
    sed -n '2,7p' "$0" | sed 's/^# \{0,1\}//'
    exit 1
    ;;
esac
