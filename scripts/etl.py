#!/usr/bin/env python3
"""ETL do Projeto Integrador: data/processed/listings_*_clean.parquet → Data Warehouse (PostgreSQL).

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
PROCESSED_DIR = os.path.join(REPO_PATH, "data", "processed")
PROCESSED_GLOB = os.path.join(PROCESSED_DIR, "listings_*_clean.parquet")
LOCK_ID = 2026_11_10  # evita duas cargas simultâneas (timer + execução manual)

# Colunas que o parquet limpo precisa ter. Dados pessoais (seller_*, buyer_*) não entram no DW.
COLUNAS_OBRIGATORIAS = (
    "record_id", "neighborhood", "city", "property_type",
    "bedrooms", "bathrooms", "parking_spots", "furnished",
    "year_built", "condo_fee", "price", "area_m2",
    "sale_date", "latitude", "longitude",
)

REGIAO_PT = {"noble": "Nobre", "mid": "Intermediária", "peripheral": "Periférica"}
BAIRROS = {}

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


def validar_ambiente():
    """REPO_PATH e DW_DSN precisam existir antes de qualquer leitura ou conexão."""
    erros = []
    if not str(REPO_PATH).strip():
        erros.append("variável de ambiente REPO_PATH está vazia")
    elif not os.path.isdir(REPO_PATH):
        erros.append(f"REPO_PATH não existe ou não é diretório: {REPO_PATH}")
    if not str(DW_DSN).strip():
        erros.append("variável de ambiente DW_DSN está vazia")
    for msg in erros:
        log(f"[ERRO] {msg}")
    if not erros:
        log(f"Ambiente ok: REPO_PATH={REPO_PATH}")
    return not erros


def validar_repositorio():
    """Schema e pasta de parquets, conferidos depois do git pull."""
    erros = []
    if not os.path.isfile(SCHEMA_FILE):
        erros.append(f"schema do DW não encontrado: {SCHEMA_FILE}")
    elif os.path.getsize(SCHEMA_FILE) == 0:
        erros.append(f"schema do DW está vazio: {SCHEMA_FILE}")
    if not os.path.isdir(PROCESSED_DIR):
        erros.append(f"pasta de parquets não encontrada: {PROCESSED_DIR}")
    gerador = os.path.join(REPO_PATH, "scripts", "generator.py")
    if not os.path.isfile(gerador):
        erros.append(f"generator.py não encontrado: {gerador}")
    for msg in erros:
        log(f"[ERRO] {msg}")
    return not erros


def carregar_bairros():
    """Bairro → região vem do generator, para não duplicar a regra."""
    scripts = os.path.join(REPO_PATH, "scripts")
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    from generator import SP_NEIGHBORHOODS  # noqa: E402

    BAIRROS.clear()
    BAIRROS.update({nome: (REGIAO_PT[zona], lat, lon) for nome, lat, lon, zona in SP_NEIGHBORHOODS})
    if not BAIRROS:
        log("[ERRO] generator.SP_NEIGHBORHOODS está vazio")
        return False
    return True


def ler_parquet(path):
    """Recusa arquivo vazio, ilegível ou sem as colunas do pipeline."""
    arquivo = os.path.basename(path)
    if not os.path.isfile(path):
        raise ValueError("arquivo não encontrado")
    if os.path.getsize(path) == 0:
        raise ValueError("arquivo vazio")
    try:
        df = pd.read_parquet(path)
    except Exception as exc:
        raise ValueError(f"arquivo corrompido ou ilegível: {exc}") from exc
    faltando = [coluna for coluna in COLUNAS_OBRIGATORIAS if coluna not in df.columns]
    if faltando:
        raise ValueError("colunas faltantes: " + ", ".join(faltando))
    if df.empty:
        log(f"[AVISO] {arquivo}: parquet sem linhas")
    return df


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


def coordenada_sp(valor, minimo, maximo):
    """Coordenada fora da Grande São Paulo vira nula, sem descartar o imóvel."""
    if pd.isna(valor):
        return None
    numero = float(valor)
    if numero < minimo or numero > maximo:
        return None
    return numero


def ano_plausivel(ano):
    if ano is None:
        return None
    if ano < 1900 or ano > date.today().year + 1:
        return None
    return ano


def transform(df):
    """Converte o parquet limpo em linhas prontas para as dimensões e a fato."""
    df = df.copy()
    df["sale_date"] = pd.to_datetime(df["sale_date"], errors="coerce")
    rows, ignoradas = [], 0
    vistos = set()
    for r in df.itertuples(index=False):
        if pd.isna(r.price) or pd.isna(r.area_m2) or r.price <= 0 or r.area_m2 <= 0:
            ignoradas += 1
            continue
        bairro = "" if pd.isna(r.neighborhood) else str(r.neighborhood).strip()
        tipo = "" if pd.isna(r.property_type) else str(r.property_type).strip()
        record_id = "" if pd.isna(r.record_id) else str(r.record_id).strip()
        if not bairro or not tipo or not record_id:
            ignoradas += 1
            continue
        # Duas linhas com o mesmo id no mesmo INSERT derrubam a carga inteira no PostgreSQL.
        if record_id in vistos:
            ignoradas += 1
            continue
        preco = round(float(r.price), 2)
        area = round(float(r.area_m2), 1)
        preco_m2 = round(preco / area, 2)
        # Fora da faixa realista de São Paulo: dado sujo que passou da limpeza do R.
        if preco_m2 < 200 or preco_m2 > 150_000:
            ignoradas += 1
            continue
        vistos.add(record_id)
        regiao, lat_c, lon_c = BAIRROS.get(bairro, ("Desconhecida", None, None))
        venda = None if pd.isna(r.sale_date) else r.sale_date.date()
        ano_construcao = ano_plausivel(to_int(r.year_built))
        cidade = "São Paulo" if pd.isna(r.city) or not str(r.city).strip() else str(r.city).strip()
        condominio = None if pd.isna(r.condo_fee) else round(float(r.condo_fee), 2)
        if condominio is not None and condominio < 0:
            condominio = None
        rows.append({
            "record_id": record_id,
            "bairro": bairro,
            "regiao": regiao,
            "cidade": cidade,
            "estado": "SP",
            "lat_centro": lat_c,
            "lon_centro": lon_c,
            "tipo": tipo,
            "tipo_pt": TIPO_PT.get(tipo, tipo),
            "carac": (
                to_int(r.bedrooms),
                to_int(r.bathrooms),
                to_int(r.parking_spots),
                to_bool(r.furnished),
                faixa_area(area),
                faixa_idade(ano_construcao),
            ),
            "venda": venda,
            "preco": preco,
            "area_m2": area,
            "preco_m2": preco_m2,
            "condominio": condominio,
            "ano_construcao": ano_construcao,
            "latitude": coordenada_sp(r.latitude, -25.5, -22.5),
            "longitude": coordenada_sp(r.longitude, -47.8, -45.5),
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


def arquivos_pendentes(carregados):
    validos = sorted(glob.glob(PROCESSED_GLOB))
    nomes_validos = {os.path.basename(p) for p in validos}
    for path in sorted(glob.glob(os.path.join(PROCESSED_DIR, "*.parquet"))):
        nome = os.path.basename(path)
        if nome not in nomes_validos:
            log(f"[AVISO] {nome}: nome fora do padrão listings_*_clean.parquet; arquivo ignorado")
    return [p for p in validos if os.path.basename(p) not in carregados]


def load_file(conn, path):
    arquivo = os.path.basename(path)
    df = ler_parquet(path)
    rows, ignoradas = transform(df)

    with conn.transaction(), conn.cursor() as cur:
        cur.execute("INSERT INTO dw.etl_carga (arquivo) VALUES (%s) RETURNING id", (arquivo,))
        id_carga = cur.fetchone()[0]

        loc, tipo, carac = load_dimensions(cur, rows)

        cur.execute("SELECT count(*) FROM dw.fato_imovel")
        antes = cur.fetchone()[0]
        if rows:
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
    try:
        result = subprocess.run(
            ["git", "-C", REPO_PATH, "pull", "--ff-only", "-q"],
            capture_output=True, text=True, timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        log(f"[AVISO] git pull falhou, usando arquivos locais: {exc}")
        return
    if result.returncode != 0:
        log(f"[AVISO] git pull falhou, usando arquivos locais: {result.stderr.strip()}")


def main():
    if not validar_ambiente():
        return 1
    git_pull()
    if not validar_repositorio() or not carregar_bairros():
        return 1

    try:
        conn_cm = psycopg.connect(DW_DSN, autocommit=True)
    except psycopg.Error as exc:
        log(f"[ERRO] falha ao conectar no Data Warehouse; confira DW_DSN: {exc}")
        return 1

    with conn_cm as conn:
        if not conn.execute("SELECT pg_try_advisory_lock(%s)", (LOCK_ID,)).fetchone()[0]:
            log("Outra carga está em andamento; saindo.")
            return 0

        try:
            try:
                with open(SCHEMA_FILE, encoding="utf-8") as f:
                    conn.execute(f.read())
            except Exception as exc:
                log(f"[ERRO] falha ao aplicar o schema do DW ({SCHEMA_FILE}): {exc}")
                return 1

            carregados = {row[0] for row in conn.execute("SELECT arquivo FROM dw.etl_carga WHERE status = 'concluída'")}
            pendentes = arquivos_pendentes(carregados)
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
        finally:
            conn.execute("SELECT pg_advisory_unlock(%s)", (LOCK_ID,))


if __name__ == "__main__":
    sys.exit(main())
