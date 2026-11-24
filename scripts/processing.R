library(dplyr)
library(readr)
library(stringr)
library(arrow)

args       <- commandArgs(trailingOnly = TRUE)
input_file <- if (length(args) >= 1) args[[1]] else ""
repo_path  <- Sys.getenv("REPO_PATH", unset = "/home/devops/repo")

if (!nzchar(input_file)) {
  stop("Uso: Rscript scripts/processing.R <arquivo.csv>")
}
if (!file.exists(input_file)) {
  stop("Arquivo não encontrado: ", input_file)
}

cat("==> Lendo arquivo:", input_file, "\n")
dados <- read.csv(input_file, na.strings = c("", "NA"), fileEncoding = "UTF-8")

obrigatorias <- c(
  "record_id", "neighborhood", "city", "state", "property_type",
  "bedrooms", "price", "area_m2", "sale_date"
)
faltando <- setdiff(obrigatorias, names(dados))
if (length(faltando) > 0) {
  stop("Colunas faltantes: ", paste(faltando, collapse = ", "))
}

# ── Exploração inicial (roteiro de aula) ────────────────────────────────────
cat("\n-- Estrutura do dataset --\n")
cat("Dimensão:", dim(dados), "\n")
cat("Variáveis:", names(dados), "\n")
str(dados)
summary(dados)

cat("\n-- Valores ausentes por variável --\n")
print(colSums(is.na(dados)))

cat("\n-- Valores únicos de state --\n")
print(unique(dados$state))

cat("\n-- Distribuição por property_type --\n")
print(table(dados$property_type))

cat("\n-- Distribuição por neighborhood --\n")
print(table(dados$neighborhood))

# ── Análise antes da limpeza ────────────────────────────────────────────────
cat("\n-- Estatísticas de price antes da limpeza --\n")
cat("  Mínimo :", min(dados$price, na.rm = TRUE), "\n")
cat("  Máximo :", max(dados$price, na.rm = TRUE), "\n")
cat("  Média  :", mean(dados$price, na.rm = TRUE), "\n")

cat("\n-- Registros com price inválido (≤ 0 ou nulo) --\n")
print(dados |> filter(is.na(price) | price <= 0) |> nrow())

cat("\n-- Registros com area_m2 inválida (≤ 0 ou nulo) --\n")
print(dados |> filter(is.na(area_m2) | area_m2 <= 0) |> nrow())

cat("\n-- Registros com bedrooms inválido (< 0 ou > 20) --\n")
print(dados |> filter(!is.na(bedrooms) & (bedrooms < 0 | bedrooms > 20)) |> nrow())

# ── Limpeza ─────────────────────────────────────────────────────────────────
cat("\n==> Iniciando limpeza...\n")
total_antes <- nrow(dados)

dados_limpos <- dados |>
  # padroniza state → "SP"
  mutate(state = "SP") |>
  # converte sale_date para Date
  mutate(sale_date = as.Date(sale_date)) |>
  # remove price inválido
  filter(!is.na(price) & price > 0) |>
  # remove area_m2 inválida
  filter(!is.na(area_m2) & area_m2 > 0) |>
  # remove bedrooms inválido
  filter(is.na(bedrooms) | (bedrooms >= 0 & bedrooms <= 20)) |>
  # ordena por neighborhood e price
  arrange(neighborhood, desc(price))

total_depois <- nrow(dados_limpos)
removidos <- total_antes - total_depois

cat("  Registros antes :", total_antes, "\n")
cat("  Registros depois:", total_depois, "\n")
cat("  Removidos       :", removidos, "\n")

# ── Análise após limpeza ─────────────────────────────────────────────────────
if (total_depois == 0L) {
  cat("\n==> Nenhum registro restou após a limpeza. O parquet sai vazio.\n")
} else {
  cat("\n-- Estatísticas de price após limpeza --\n")
  cat("  Mínimo :", min(dados_limpos$price), "\n")
  cat("  Máximo :", max(dados_limpos$price), "\n")
  cat("  Média  :", mean(dados_limpos$price), "\n")

  cat("\n-- Maior price por neighborhood --\n")
  dados_limpos |>
    group_by(neighborhood) |>
    summarise(preco_medio = mean(price), total = n(), .groups = "drop") |>
    arrange(desc(preco_medio)) |>
    print()
}

# ── Exportação ───────────────────────────────────────────────────────────────
output_dir <- file.path(dirname(dirname(input_file)), "processed")
dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)

basename_input <- tools::file_path_sans_ext(basename(input_file))
output_file    <- file.path(output_dir, paste0(basename_input, "_clean.parquet"))

write_parquet(dados_limpos, output_file)
cat("\n==> Exportado:", output_file, "\n")
