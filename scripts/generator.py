import csv
import os
import random
import subprocess
import time
import uuid
from datetime import datetime, date

from dotenv import load_dotenv

load_dotenv()

OUTPUT_DIR       = os.getenv("OUTPUT_DIR", "/home/devops/data/raw")
REPO_PATH        = os.getenv("REPO_PATH", "/home/devops/repo")
INTERVAL_SECONDS = int(os.getenv("INTERVAL_SECONDS", 1800))
BATCH_SIZE_MIN   = int(os.getenv("BATCH_SIZE_MIN", 50))
BATCH_SIZE_MAX   = int(os.getenv("BATCH_SIZE_MAX", 200))

SP_NEIGHBORHOODS = [
    ("Moema",               -23.5983, -46.6659, "noble"),
    ("Pinheiros",           -23.5629, -46.6932, "noble"),
    ("Vila Madalena",       -23.5567, -46.6914, "noble"),
    ("Jardins",             -23.5726, -46.6553, "noble"),
    ("Itaim Bibi",          -23.5867, -46.6755, "noble"),
    ("Perdizes",            -23.5352, -46.6611, "noble"),
    ("Morumbi",             -23.6203, -46.7195, "noble"),
    ("Campo Belo",          -23.6221, -46.6657, "noble"),
    ("Alto de Pinheiros",   -23.5446, -46.7148, "noble"),
    ("Higienópolis",        -23.5423, -46.6572, "noble"),
    ("Consolação",          -23.5510, -46.6580, "noble"),
    ("Paraíso",             -23.5751, -46.6479, "noble"),
    ("Vila Mariana",        -23.5876, -46.6380, "noble"),
    ("Bela Vista",          -23.5578, -46.6441, "noble"),
    ("Brooklin",            -23.6177, -46.6946, "mid"),
    ("Tatuapé",             -23.5389, -46.5729, "mid"),
    ("Santana",             -23.5031, -46.6267, "mid"),
    ("Lapa",                -23.5221, -46.7065, "mid"),
    ("Aclimação",           -23.5680, -46.6320, "mid"),
    ("Liberdade",           -23.5583, -46.6352, "mid"),
    ("Mooca",               -23.5508, -46.6025, "mid"),
    ("Saúde",               -23.5966, -46.6324, "mid"),
    ("Butantã",             -23.5712, -46.7310, "mid"),
    ("Bom Retiro",          -23.5261, -46.6371, "mid"),
    ("Ipiranga",            -23.5908, -46.6053, "mid"),
    ("Barra Funda",         -23.5266, -46.6650, "mid"),
    ("Casa Verde",          -23.5063, -46.6560, "mid"),
    ("Jabaquara",           -23.6448, -46.6422, "mid"),
    ("Penha",               -23.5264, -46.5431, "mid"),
    ("Vila Guilherme",      -23.5086, -46.5986, "mid"),
    ("Vila Leopoldina",     -23.5261, -46.7381, "mid"),
    ("Cursino",             -23.6117, -46.6197, "mid"),
    ("Mandaqui",            -23.4878, -46.6378, "mid"),
    ("Brás",                -23.5450, -46.6170, "mid"),
    ("Cambuci",             -23.5701, -46.6194, "mid"),
    ("Água Funda",          -23.6214, -46.6108, "mid"),
    ("Santo André",         -23.6639, -46.5383, "peripheral"),
    ("Vila Prudente",       -23.5875, -46.5697, "peripheral"),
    ("Pirituba",            -23.4869, -46.7197, "peripheral"),
    ("Sapopemba",           -23.6058, -46.5197, "peripheral"),
    ("Vila Andrade",        -23.6418, -46.7248, "peripheral"),
    ("Vila Sônia",          -23.5942, -46.7402, "peripheral"),
    ("Sacomã",              -23.6097, -46.5928, "peripheral"),
    ("Cidade Ademar",       -23.6639, -46.6611, "peripheral"),
    ("Cidade Dutra",        -23.7008, -46.6611, "peripheral"),
]

PRICE_PER_M2 = {
    "noble":      (12_000, 25_000),
    "mid":        (6_000,  12_000),
    "peripheral": (3_000,   6_000),
}

AREA_RANGE = {
    "studio":     (20,  55),
    "apartment":  (45, 200),
    "house":      (80, 350),
    "penthouse":  (120, 350),
    "commercial": (25, 400),
}

PROPERTY_TYPES = ["apartment", "house", "studio", "commercial", "penthouse"]

SELLERS = [
    {"id": "S-001", "name": "Carlos Mendes"},
    {"id": "S-002", "name": "Ana Paula Lima"},
    {"id": "S-003", "name": "Roberto Souza"},
    {"id": "S-004", "name": "Fernanda Costa"},
    {"id": "S-005", "name": "Marcelo Ferreira"},
    {"id": "S-006", "name": "Juliana Martins"},
    {"id": "S-007", "name": "Diego Alves"},
    {"id": "S-008", "name": "Patrícia Nunes"},
    {"id": "S-009", "name": "Rafael Cardoso"},
    {"id": "S-010", "name": "Camila Rodrigues"},
    {"id": "S-011", "name": "Bruno Oliveira"},
    {"id": "S-012", "name": "Larissa Santos"},
    {"id": "S-013", "name": "Gustavo Pereira"},
    {"id": "S-014", "name": "Vanessa Teixeira"},
    {"id": "S-015", "name": "Thiago Barbosa"},
    {"id": "S-016", "name": "Aline Gomes"},
    {"id": "S-017", "name": "Felipe Nascimento"},
    {"id": "S-018", "name": "Renata Freitas"},
    {"id": "S-019", "name": "Eduardo Cunha"},
    {"id": "S-020", "name": "Isabela Moreira"},
]

BUYER_NOTES = [
    "Interested in the view, wants to negotiate price.",
    "Looking for a property near public transport.",
    "Prefers ground floor due to mobility issues.",
    "Asked about pet policy in the building.",
    "Wants to schedule a second visit with spouse.",
    "Concerned about noise from nearby avenue.",
    "Requested details on condo fees.",
    "Very interested, likely to make an offer.",
    "Needs parking for two cars.",
    "Prefers newly renovated units only.",
]

STATE_VARIATIONS = ["SP", "Sp", "sp", "São Paulo", "Sao Paulo", "S.Paulo"]

DIRTY_VALUES = {
    "bedrooms": [-1, -2, 99, None],
    "price":    [-500, -1000, 0, None],
    "area_m2":  [-10, -5, 0, None],
}


def random_coords(lat_base, lon_base):
    return (
        round(lat_base + random.uniform(-0.008, 0.008), 6),
        round(lon_base + random.uniform(-0.008, 0.008), 6),
    )


def random_sale_date():
    year  = random.randint(2023, 2026)
    month = random.randint(1, 12)
    day   = random.randint(1, 28)
    return date(year, month, day).isoformat()


def generate_record():
    neighborhood, lat_base, lon_base, zone = random.choice(SP_NEIGHBORHOODS)
    lat, lon = random_coords(lat_base, lon_base)
    prop_type = random.choice(PROPERTY_TYPES)
    seller = random.choice(SELLERS)

    area_min, area_max = AREA_RANGE[prop_type]
    area = round(random.uniform(area_min, area_max), 1)

    price_min, price_max = PRICE_PER_M2[zone]
    price = round(area * random.uniform(price_min, price_max), 2)

    if prop_type == "studio":
        bedrooms, bathrooms = 0, 1
    elif prop_type == "apartment":
        bedrooms = random.randint(1, 4)
        bathrooms = random.randint(1, bedrooms + 1)
    elif prop_type == "house":
        bedrooms = random.randint(2, 5)
        bathrooms = random.randint(1, bedrooms)
    elif prop_type == "penthouse":
        bedrooms = random.randint(3, 5)
        bathrooms = random.randint(2, 4)
    else:  # commercial
        bedrooms, bathrooms = 0, 1

    # inject dirty data ~10% of the time
    if random.random() < 0.10:
        field = random.choice(list(DIRTY_VALUES.keys()))
        if field == "bedrooms":
            bedrooms = random.choice(DIRTY_VALUES["bedrooms"])
        elif field == "price":
            price = random.choice(DIRTY_VALUES["price"])
        elif field == "area_m2":
            area = random.choice(DIRTY_VALUES["area_m2"])

    parking   = random.randint(0, 3)
    condo_fee = round(random.uniform(300, 2500), 2) if prop_type != "house" else 0.0
    year_built = random.randint(1975, 2024)
    furnished  = random.choice([True, False])

    has_buyer  = random.random() > 0.3
    buyer_id   = f"B-{uuid.uuid4().hex[:8].upper()}" if has_buyer else ""
    buyer_notes = random.choice(BUYER_NOTES) if has_buyer else ""
    sale_date  = random_sale_date() if has_buyer else ""

    return {
        "record_id":     str(uuid.uuid4()),
        "seller_id":     seller["id"],
        "seller_name":   seller["name"],
        "buyer_id":      buyer_id,
        "property_type": prop_type,
        "neighborhood":  neighborhood,
        "city":          "São Paulo",
        "state":         random.choice(STATE_VARIATIONS),
        "latitude":      lat,
        "longitude":     lon,
        "area_m2":       area,
        "bedrooms":      bedrooms,
        "bathrooms":     bathrooms,
        "parking_spots": parking,
        "year_built":    year_built,
        "furnished":     furnished,
        "condo_fee":     condo_fee,
        "price":         price,
        "sale_date":     sale_date,
        "buyer_notes":   buyer_notes,
    }


def push_to_github(filepath):
    filename = os.path.basename(filepath)
    commands = [
        ["git", "-C", REPO_PATH, "pull", "--rebase"],
        ["cp", filepath, os.path.join(REPO_PATH, "data", "raw", filename)],
        ["git", "-C", REPO_PATH, "add", f"data/raw/{filename}"],
        ["git", "-C", REPO_PATH, "commit", "-m", f"raw data: add {filename}"],
        ["git", "-C", REPO_PATH, "push"],
    ]
    for cmd in commands:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"[ERROR] {' '.join(cmd)}\n{result.stderr}")
            return False
    return True


def run():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    batch_size = random.randint(BATCH_SIZE_MIN, BATCH_SIZE_MAX)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename  = f"listings_{timestamp}.csv"
    filepath  = os.path.join(OUTPUT_DIR, filename)

    records   = [generate_record() for _ in range(batch_size)]
    fieldnames = list(records[0].keys())

    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)

    print(f"[{datetime.now().isoformat()}] Generated {batch_size} records → {filename}")

    if push_to_github(filepath):
        print(f"[{datetime.now().isoformat()}] Pushed {filename} to GitHub")
        os.remove(filepath)
    else:
        print(f"[{datetime.now().isoformat()}] Push failed — file kept locally at {filepath}")


if __name__ == "__main__":
    print(f"Generator started. Interval: {INTERVAL_SECONDS}s")
    while True:
        run()
        time.sleep(INTERVAL_SECONDS)
