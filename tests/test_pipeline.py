"""Testes do gerador e da transformação do ETL, sem PostgreSQL."""
import csv
import os
import random
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import etl  # noqa: E402
import generator  # noqa: E402


def linha(**kwargs):
    base = {
        "record_id": "11111111-1111-1111-1111-111111111111",
        "neighborhood": "Moema",
        "city": "São Paulo",
        "property_type": "apartment",
        "bedrooms": 2,
        "bathrooms": 1,
        "parking_spots": 1,
        "furnished": True,
        "year_built": 2010,
        "condo_fee": 800,
        "price": 500_000,
        "area_m2": 60,
        "sale_date": "2024-05-01",
        "latitude": -23.6,
        "longitude": -46.66,
    }
    base.update(kwargs)
    return base


class TestTransform(unittest.TestCase):
    def setUp(self):
        etl.BAIRROS.clear()
        etl.BAIRROS["Moema"] = ("Nobre", -23.5983, -46.6659)

    def test_faixas_e_tempo(self):
        self.assertEqual(etl.faixa_area(40), "até 40 m²")
        self.assertEqual(etl.faixa_area(80), "41 a 80 m²")
        self.assertEqual(etl.faixa_area(250), "acima de 200 m²")
        self.assertEqual(etl.faixa_idade(None), "Desconhecida")
        self.assertEqual(etl.sk_tempo(None), 0)
        self.assertEqual(etl.sk_tempo(date(2024, 1, 2)), 20240102)

    def test_imovel_valido(self):
        rows, ignoradas = etl.transform(pd.DataFrame([linha()]))
        self.assertEqual(ignoradas, 0)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["regiao"], "Nobre")
        self.assertEqual(rows[0]["tipo_pt"], "Apartamento")
        self.assertEqual(rows[0]["preco_m2"], round(500_000 / 60, 2))
        self.assertTrue(rows[0]["venda"])

    def test_descarta_preco_area_bairro_e_duplicata(self):
        df = pd.DataFrame([
            linha(price=0),
            linha(area_m2=-5, price=1000),
            linha(neighborhood="  "),
            linha(record_id="abc"),
            linha(record_id="abc", price=900_000),
            linha(price=50, area_m2=10),  # R$ 5/m², fora da faixa
        ])
        rows, ignoradas = etl.transform(df)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["record_id"], "abc")
        self.assertEqual(ignoradas, 5)

    def test_coordenada_fora_de_sp_vira_nula(self):
        rows, ignoradas = etl.transform(pd.DataFrame([linha(latitude=10, longitude=10)]))
        self.assertEqual(ignoradas, 0)
        self.assertIsNone(rows[0]["latitude"])
        self.assertIsNone(rows[0]["longitude"])

    def test_ano_absurdo_nao_entra_na_faixa(self):
        rows, _ = etl.transform(pd.DataFrame([linha(year_built=1200)]))
        self.assertIsNone(rows[0]["ano_construcao"])
        self.assertEqual(rows[0]["carac"][5], "Desconhecida")


class TestGerador(unittest.TestCase):
    def test_registro_tem_as_vinte_colunas(self):
        random.seed(7)
        rec = generator.generate_record()
        self.assertEqual(list(rec.keys()), generator.CSV_FIELDS)
        self.assertEqual(len(generator.CSV_FIELDS), 20)
        self.assertIn(rec["neighborhood"], {n[0] for n in generator.SP_NEIGHBORHOODS})

    def test_carga_historica(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "historico.csv")
            generator.generate_history(5, path, 2026)
            with open(path, encoding="utf-8", newline="") as f:
                linhas = list(csv.DictReader(f))
        self.assertEqual(len(linhas), 5)
        self.assertEqual(list(linhas[0].keys()), generator.CSV_FIELDS)

    def test_historico_vazio_falha(self):
        with self.assertRaises(ValueError):
            generator.generate_history(0, "nao.csv", 1)

    def test_lote_invertido(self):
        original = (generator.BATCH_SIZE_MIN, generator.BATCH_SIZE_MAX)
        generator.BATCH_SIZE_MIN, generator.BATCH_SIZE_MAX = 10, 2
        try:
            erros = generator.validar_config()
        finally:
            generator.BATCH_SIZE_MIN, generator.BATCH_SIZE_MAX = original
        self.assertTrue(any("BATCH_SIZE_MAX" in erro for erro in erros))


if __name__ == "__main__":
    unittest.main()
