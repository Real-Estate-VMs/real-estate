#!/usr/bin/env python3
"""ETL do Projeto Integrador: data/processed/*.parquet → Data Warehouse (PostgreSQL).

Extração : lê os parquets já limpos pelo pipeline (processing.R) no repositório.
Transform: deriva região, preço por m², faixas de área e idade e a dimensão tempo.
Carga    : popula o esquema estrela (dw.*). Cada arquivo é carregado uma única vez,
           numa transação, e registrado em dw.etl_carga.
"""
import glob
import os
import subprocess
import sys
from datetime import date, datetime

import pandas as pd
import psycopg

REPO_PATH = os.getenv("REPO_PATH", "/home/devops/repo")
DW_DSN = os.getenv("DW_DSN", "dbname=realestate")
SCHEMA_FILE = os.path.join(REPO_PATH, "sql", "dw_schema.sql")
PROCESSED_GLOB = os.path.join(REPO_PATH, "data", "processed", "*.parquet")
LOCK_ID = 2026_11_10  # evita duas cargas simultâneas (timer + execução manual)

# O mapeamento bairro → região vem do próprio generator, para não duplicar a regra
sys.path.insert(0, os.path.join(REPO_PATH, "scripts"))
from generator import SP_NEIGHBORHOODS  # noqa: E402

REGIAO_PT = {"noble": "Nobre", "mid": "Intermediária", "peripheral": "Periférica"}
BAIRROS = {nome: (REGIAO_PT[zona], lat, lon) for nome, lat, lon, zona in SP_NEIGHBORHOODS}

TIPO_PT = {
    "apartment": "Apartamento",
    "house": "Casa",
    "studio": "Studio",
    "commercial": "Comercial",
    "penthouse": "Cobertura",
}
MESES = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho",
         "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
DIAS = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]


def log(msg):
    print(f"[{datetime.now().isoformat(timespec='seconds')}] {msg}", flush=True)


def faixa_area(area):
    if area <= 40:
        return "até 40 m²"
    if area <= 80:
        return "41 a 80 m²"
    if area <= 120:
        return "81 a 120 m²"
    if area <= 200:
        return "121 a 200 m²"
    return "acima de 200 m²"


def faixa_idade(ano_construcao):
    if ano_construcao is None:
        return "Desconhecida"
    idade = date.today().year - ano_construcao
    if idade <= 10:
        return "até 10 anos"
    if idade <= 20:
        return "11 a 20 anos"
    if idade <= 30:
        return "21 a 30 anos"
    if idade <= 40:
        return "31 a 40 anos"
    return "mais de 40 anos"


def to_int(value):
    return None if pd.isna(value) else int(value)


def to_bool(value):
    if pd.isna(value):
        return None
    if isinstance(value, str):
        return value.strip().lower() in ("true", "1", "sim")
    return bool(value)


def transform(df):
    """Converte o parquet limpo em linhas prontas para as dimensões e a fato."""
    df = df.copy()
    df["sale_date"] = pd.to_datetime(df["sale_date"], errors="coerce")
    rows, ignoradas = [], 0
    for r in df.itertuples(index=False):
        if pd.isna(r.price) or pd.isna(r.area_m2) or r.price <= 0 or r.area_m2 <= 0:
            ignoradas += 1
            continue
        regiao, lat_c, lon_c = BAIRROS.get(r.neighborhood, ("Desconhecida", None, None))
        venda = None if pd.isna(r.sale_date) else r.sale_date.date()
        ano_construcao = to_int(r.year_built)
        rows.append({
            "record_id": str(r.record_id),
            "bairro": r.neighborhood,
            "regiao": regiao,
            "cidade": r.city,
            "estado": "SP",
            "lat_centro": lat_c,
            "lon_centro": lon_c,
            "tipo": r.property_type,
            "tipo_pt": TIPO_PT.get(r.property_type, r.property_type),
            "carac": (
                to_int(r.bedrooms),
                to_int(r.bathrooms),
                to_int(r.parking_spots),
                to_bool(r.furnished),
                faixa_area(float(r.area_m2)),
                faixa_idade(ano_construcao),
            ),
            "venda": venda,
            "preco": round(float(r.price), 2),
            "area_m2": round(float(r.area_m2), 1),
            "preco_m2": round(float(r.price) / float(r.area_m2), 2),
            "condominio": None if pd.isna(r.condo_fee) else round(float(r.condo_fee), 2),
            "ano_construcao": ano_construcao,
            "latitude": None if pd.isna(r.latitude) else float(r.latitude),
            "longitude": None if pd.isna(r.longitude) else float(r.longitude),
        })
    return rows, ignoradas


def sk_tempo(d):
    return 0 if d is None else d.year * 10000 + d.month * 100 + d.day


def load_dimensions(cur, rows):
    """Insere os membros novos de cada dimensão e devolve os mapas chave natural → chave substituta."""
    for bairro, regiao, cidade, estado, lat, lon in {
        (r["bairro"], r["regiao"], r["cidade"], r["estado"], r["lat_centro"], r["lon_centro"])
        for r in rows
    }:
        cur.execute(
            "INSERT INTO dw.dim_localizacao (bairro, regiao, cidade, estado, latitude, longitude) "
            "VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (bairro) DO NOTHING",
            (bairro, regiao, cidade, estado, lat, lon),
        )
    for tipo, tipo_pt in {(r["tipo"], r["tipo_pt"]) for r in rows}:
        cur.execute(
            "INSERT INTO dw.dim_tipo_imovel (tipo, tipo_pt) VALUES (%s, %s) ON CONFLICT (tipo) DO NOTHING",
            (tipo, tipo_pt),
        )
    for carac in {r["carac"] for r in rows}:
        cur.execute(
            "INSERT INTO dw.dim_caracteristicas "
            "(quartos, banheiros, vagas, mobiliado, faixa_area, faixa_idade) "
            "VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
            carac,
        )
    for d in {r["venda"] for r in rows if r["venda"] is not None}:
        cur.execute(
            "INSERT INTO dw.dim_tempo (sk_tempo, data, ano, trimestre, mes, nome_mes, dia_semana) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s) ON CONFLICT (sk_tempo) DO NOTHING",
            (sk_tempo(d), d, d.year, (d.month - 1) // 3 + 1, d.month, MESES[d.month - 1], DIAS[d.weekday()]),
        )

    cur.execute("SELECT bairro, sk_localizacao FROM dw.dim_localizacao")
    loc = dict(cur.fetchall())
    cur.execute("SELECT tipo, sk_tipo FROM dw.dim_tipo_imovel")
    tipo = dict(cur.fetchall())
    cur.execute(
        "SELECT quartos, banheiros, vagas, mobiliado, faixa_area, faixa_idade, sk_caracteristicas "
        "FROM dw.dim_caracteristicas"
    )
    carac = {tuple(row[:6]): row[6] for row in cur.fetchall()}
    return loc, tipo, carac


def load_file(conn, path):
    arquivo = os.path.basename(path)
    df = pd.read_parquet(path)
    rows, ignoradas = transform(df)

    with conn.transaction(), conn.cursor() as cur:
        cur.execute("INSERT INTO dw.etl_carga (arquivo) VALUES (%s) RETURNING id", (arquivo,))
        id_carga = cur.fetchone()[0]

        loc, tipo, carac = load_dimensions(cur, rows)

        cur.execute("SELECT count(*) FROM dw.fato_imovel")
        antes = cur.fetchone()[0]
        cur.executemany(
            "INSERT INTO dw.fato_imovel (record_id, sk_localizacao, sk_tempo, sk_tipo, sk_caracteristicas, "
            "id_carga, vendido, preco, area_m2, preco_m2, condominio, ano_construcao, latitude, longitude) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
            "ON CONFLICT (record_id) DO NOTHING",
            [
                (
                    r["record_id"], loc[r["bairro"]], sk_tempo(r["venda"]), tipo[r["tipo"]], carac[r["carac"]],
                    id_carga, r["venda"] is not None, r["preco"], r["area_m2"], r["preco_m2"],
                    r["condominio"], r["ano_construcao"], r["latitude"], r["longitude"],
                )
                for r in rows
            ],
        )
        cur.execute("SELECT count(*) FROM dw.fato_imovel")
        inseridas = cur.fetchone()[0] - antes
        ignoradas += len(rows) - inseridas

        cur.execute(
            "UPDATE dw.etl_carga SET finalizado_em = now(), linhas_lidas = %s, linhas_inseridas = %s, "
            "linhas_ignoradas = %s, status = 'concluída' WHERE id = %s",
            (len(df), inseridas, ignoradas, id_carga),
        )
    log(f"{arquivo}: {len(df)} lidas, {inseridas} inseridas, {ignoradas} ignoradas")


def git_pull():
    result = subprocess.run(["git", "-C", REPO_PATH, "pull", "--ff-only", "-q"], capture_output=True, text=True)
    if result.returncode != 0:
        log(f"[AVISO] git pull falhou, usando arquivos locais: {result.stderr.strip()}")


def main():
    git_pull()
    with psycopg.connect(DW_DSN, autocommit=True) as conn:
        if not conn.execute("SELECT pg_try_advisory_lock(%s)", (LOCK_ID,)).fetchone()[0]:
            log("Outra carga está em andamento; saindo.")
            return 0

        with open(SCHEMA_FILE, encoding="utf-8") as f:
            conn.execute(f.read())

        carregados = {row[0] for row in conn.execute("SELECT arquivo FROM dw.etl_carga WHERE status = 'concluída'")}
        pendentes = [p for p in sorted(glob.glob(PROCESSED_GLOB)) if os.path.basename(p) not in carregados]
        if not pendentes:
            log("Nenhum arquivo novo.")
            return 0

        falhas = 0
        for path in pendentes:
            try:
                load_file(conn, path)
            except Exception as exc:  # um arquivo ruim não impede os demais
                falhas += 1
                log(f"[ERRO] {os.path.basename(path)}: {exc}")
        total = conn.execute("SELECT count(*) FROM dw.fato_imovel").fetchone()[0]
        log(f"Carga finalizada: {len(pendentes) - falhas} arquivo(s), {falhas} falha(s). Fato com {total} linhas.")
        return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
