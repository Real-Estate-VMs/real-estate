-- Data Warehouse do Projeto Integrador (esquema estrela)
-- Idempotente: o ETL executa este arquivo no início de toda carga.

CREATE SCHEMA IF NOT EXISTS dw;

-- ── Controle de cargas (evidência do ETL) ────────────────────────────────────
CREATE TABLE IF NOT EXISTS dw.etl_carga (
    id                SERIAL PRIMARY KEY,
    arquivo           TEXT        NOT NULL UNIQUE,
    iniciado_em       TIMESTAMPTZ NOT NULL DEFAULT now(),
    finalizado_em     TIMESTAMPTZ,
    linhas_lidas      INTEGER     NOT NULL DEFAULT 0,
    linhas_inseridas  INTEGER     NOT NULL DEFAULT 0,
    linhas_ignoradas  INTEGER     NOT NULL DEFAULT 0,
    status            TEXT        NOT NULL DEFAULT 'em andamento'
);

-- ── Dimensões ────────────────────────────────────────────────────────────────
-- Hierarquia: bairro → região → cidade → estado
CREATE TABLE IF NOT EXISTS dw.dim_localizacao (
    sk_localizacao  SERIAL PRIMARY KEY,
    bairro          TEXT NOT NULL UNIQUE,
    regiao          TEXT NOT NULL,
    cidade          TEXT NOT NULL,
    estado          TEXT NOT NULL,
    latitude        NUMERIC(9, 6),
    longitude       NUMERIC(9, 6)
);

-- Hierarquia: data → mês → trimestre → ano. sk_tempo = AAAAMMDD; 0 = sem data (não vendido)
CREATE TABLE IF NOT EXISTS dw.dim_tempo (
    sk_tempo    INTEGER PRIMARY KEY,
    data        DATE,
    ano         INTEGER,
    trimestre   INTEGER,
    mes         INTEGER,
    nome_mes    TEXT,
    dia_semana  TEXT
);
INSERT INTO dw.dim_tempo (sk_tempo, nome_mes, dia_semana)
VALUES (0, 'Sem data', 'Sem data')
ON CONFLICT (sk_tempo) DO NOTHING;

CREATE TABLE IF NOT EXISTS dw.dim_tipo_imovel (
    sk_tipo  SERIAL PRIMARY KEY,
    tipo     TEXT NOT NULL UNIQUE,
    tipo_pt  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS dw.dim_caracteristicas (
    sk_caracteristicas  SERIAL PRIMARY KEY,
    quartos             INTEGER,
    banheiros           INTEGER,
    vagas               INTEGER,
    mobiliado           BOOLEAN,
    faixa_area          TEXT NOT NULL,
    faixa_idade         TEXT NOT NULL,
    UNIQUE NULLS NOT DISTINCT (quartos, banheiros, vagas, mobiliado, faixa_area, faixa_idade)
);

-- ── Fato ─────────────────────────────────────────────────────────────────────
-- Grão: um imóvel anunciado. Imóveis sem comprador ficam com vendido = false e sk_tempo = 0.
CREATE TABLE IF NOT EXISTS dw.fato_imovel (
    record_id           UUID PRIMARY KEY,
    sk_localizacao      INTEGER NOT NULL REFERENCES dw.dim_localizacao,
    sk_tempo            INTEGER NOT NULL REFERENCES dw.dim_tempo,
    sk_tipo             INTEGER NOT NULL REFERENCES dw.dim_tipo_imovel,
    sk_caracteristicas  INTEGER NOT NULL REFERENCES dw.dim_caracteristicas,
    id_carga            INTEGER NOT NULL REFERENCES dw.etl_carga,
    vendido             BOOLEAN NOT NULL,
    preco               NUMERIC(14, 2) NOT NULL,
    area_m2             NUMERIC(10, 1) NOT NULL,
    preco_m2            NUMERIC(12, 2) NOT NULL,
    condominio          NUMERIC(10, 2),
    ano_construcao      INTEGER,
    latitude            NUMERIC(9, 6),
    longitude           NUMERIC(9, 6)
);
CREATE INDEX IF NOT EXISTS ix_fato_localizacao ON dw.fato_imovel (sk_localizacao);
CREATE INDEX IF NOT EXISTS ix_fato_tempo       ON dw.fato_imovel (sk_tempo);
CREATE INDEX IF NOT EXISTS ix_fato_tipo        ON dw.fato_imovel (sk_tipo);

-- ── Views analíticas (OLAP) ──────────────────────────────────────────────────
-- Visão "achatada" do cubo: base para slice e dice (filtros) no Grafana e no notebook
CREATE OR REPLACE VIEW dw.vw_imoveis AS
SELECT f.record_id,
       l.bairro, l.regiao, l.cidade, l.estado,
       t.tipo, t.tipo_pt,
       c.quartos, c.banheiros, c.vagas, c.mobiliado, c.faixa_area, c.faixa_idade,
       tp.data AS data_venda, tp.ano, tp.trimestre, tp.mes, tp.nome_mes,
       f.vendido, f.preco, f.area_m2, f.preco_m2, f.condominio, f.ano_construcao,
       f.latitude, f.longitude, f.id_carga
FROM dw.fato_imovel f
JOIN dw.dim_localizacao     l  USING (sk_localizacao)
JOIN dw.dim_tipo_imovel     t  USING (sk_tipo)
JOIN dw.dim_caracteristicas c  USING (sk_caracteristicas)
JOIN dw.dim_tempo           tp USING (sk_tempo);

-- Roll-up: bairro → região → total geral
CREATE OR REPLACE VIEW dw.vw_rollup_localizacao AS
SELECT COALESCE(regiao, 'TOTAL GERAL')                                   AS regiao,
       COALESCE(bairro, CASE WHEN regiao IS NULL THEN '' ELSE 'TOTAL DA REGIÃO' END) AS bairro,
       COUNT(*)                     AS imoveis,
       ROUND(AVG(preco), 2)         AS preco_medio,
       ROUND(AVG(preco_m2), 2)      AS preco_m2_medio,
       GROUPING(regiao, bairro)     AS nivel
FROM dw.vw_imoveis
GROUP BY ROLLUP (regiao, bairro);

-- Drill-down: ano → trimestre → mês (apenas imóveis vendidos)
CREATE OR REPLACE VIEW dw.vw_drilldown_tempo AS
SELECT ano, trimestre, mes,
       COUNT(*)                 AS vendas,
       ROUND(SUM(preco), 2)     AS valor_total,
       ROUND(AVG(preco_m2), 2)  AS preco_m2_medio,
       GROUPING(ano, trimestre, mes) AS nivel
FROM dw.vw_imoveis
WHERE vendido
GROUP BY ROLLUP (ano, trimestre, mes);

-- Cubo: tipo de imóvel × região, com todos os subtotais
CREATE OR REPLACE VIEW dw.vw_cubo_tipo_regiao AS
SELECT COALESCE(tipo_pt, 'TODOS') AS tipo,
       COALESCE(regiao, 'TODAS')  AS regiao,
       COUNT(*)                   AS imoveis,
       ROUND(AVG(preco_m2), 2)    AS preco_m2_medio
FROM dw.vw_imoveis
GROUP BY CUBE (tipo_pt, regiao);

-- ── Acesso somente leitura (Grafana e notebook) ──────────────────────────────
GRANT USAGE ON SCHEMA dw TO dw_leitura;
GRANT SELECT ON ALL TABLES IN SCHEMA dw TO dw_leitura;
ALTER DEFAULT PRIVILEGES IN SCHEMA dw GRANT SELECT ON TABLES TO dw_leitura;
