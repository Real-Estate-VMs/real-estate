#!/usr/bin/env python3
"""Modelo de preço em produção: treina uma Random Forest com os dados do Data Warehouse e
grava o preço previsto de cada imóvel em dw.previsao_preco.

É o mesmo modelo do notebook (seção 4.3). Roda uma vez por dia na VM bigdata (systemd timer)
e alimenta o painel "Oportunidades (modelo de ML)" do Grafana.

Cada imóvel é previsto por um modelo que NÃO o viu no treino (validação cruzada em 5 partes),
então o desconto calculado não é inflado pelo ajuste aos próprios dados.
"""
import os
import sys
import time
from datetime import datetime

import pandas as pd
import psycopg
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_absolute_percentage_error, mean_squared_error, r2_score
from sklearn.model_selection import cross_val_predict
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

DW_DSN = os.getenv("DW_DSN", "dbname=realestate")
MINIMO_LINHAS = int(os.getenv("ML_MINIMO_LINHAS", 500))  # abaixo disso o modelo não é confiável
NUMERICAS = ["area_m2", "quartos", "banheiros", "vagas", "condominio", "ano_construcao"]
CATEGORICAS = ["tipo_pt", "regiao", "bairro", "mobiliado"]
NOME_MODELO = "RandomForest(100, leaf=5, max_features=0.5)"


def log(msg):
    print(f"[{datetime.now().isoformat(timespec='seconds')}] {msg}", flush=True)


def construir_modelo():
    preparo = ColumnTransformer([
        ("num", "passthrough", NUMERICAS),
        ("cat", OneHotEncoder(handle_unknown="ignore"), CATEGORICAS),
    ])
    floresta = RandomForestRegressor(n_estimators=100, min_samples_leaf=5, max_features=0.5,
                                     n_jobs=-1, random_state=42)
    return Pipeline([("prep", preparo), ("modelo", floresta)])


def main():
    inicio = time.time()
    with psycopg.connect(DW_DSN) as conn:
        df = pd.read_sql("SELECT * FROM dw.vw_imoveis", conn)
        df = df.dropna(subset=NUMERICAS + CATEGORICAS + ["preco"]).reset_index(drop=True)
        if len(df) < MINIMO_LINHAS:
            log(f"Apenas {len(df)} imóveis no DW (mínimo {MINIMO_LINHAS}); nada a fazer.")
            return 0
        df["mobiliado"] = df["mobiliado"].astype(str)

        X, y = df[NUMERICAS + CATEGORICAS], df["preco"].astype(float)
        previsto = cross_val_predict(construir_modelo(), X, y, cv=5, n_jobs=1)
        desconto = (1 - y / previsto).clip(-9.9999, 9.9999)
        segundos = time.time() - inicio

        linhas = [(r, float(p), float(d), NOME_MODELO) for r, p, d in zip(df["record_id"], previsto, desconto)]
        with conn.transaction():
            conn.execute("DELETE FROM dw.previsao_preco")
            with conn.cursor() as cur:
                cur.executemany(
                    "INSERT INTO dw.previsao_preco (record_id, preco_previsto, desconto, modelo) "
                    "VALUES (%s, %s, %s, %s)", linhas)
            conn.execute(
                "INSERT INTO dw.modelo_metricas (modelo, linhas, mae, rmse, mape, r2, segundos) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (NOME_MODELO, len(df), mean_absolute_error(y, previsto),
                 mean_squared_error(y, previsto) ** 0.5, mean_absolute_percentage_error(y, previsto),
                 r2_score(y, previsto), round(segundos, 1)))
        abaixo = int(((~df["vendido"]) & (desconto >= 0.2)).sum())
        log(f"{len(df)} imóveis previstos em {segundos:.0f}s | R² {r2_score(y, previsto):.3f} | "
            f"{abaixo} disponíveis ≥ 20% abaixo do previsto")
    return 0


if __name__ == "__main__":
    sys.exit(main())
