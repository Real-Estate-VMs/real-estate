#!/bin/bash
# Roda os testes do gerador e da transformação do ETL (não sobe o PostgreSQL).
set -euo pipefail
cd "$(dirname "$0")/.."
python -m unittest discover -s tests -v
