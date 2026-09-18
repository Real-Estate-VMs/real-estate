import csv
import os
import random
import subprocess
import time
import uuid
from datetime import datetime

from dotenv import load_dotenv

load_dotenv()

OUTPUT_DIR       = os.getenv("OUTPUT_DIR", "/home/devops/data/raw")
REPO_PATH        = os.getenv("REPO_PATH", "/home/devops/repo")
INTERVAL_SECONDS = int(os.getenv("INTERVAL_SECONDS", 1800))
BATCH_SIZE_MIN   = int(os.getenv("BATCH_SIZE_MIN", 50))
BATCH_SIZE_MAX   = int(os.getenv("BATCH_SIZE_MAX", 200))

SP_NEIGHBORHOODS = [
    ("Moema",               -23.5983, -46.6659),
    ("Pinheiros",           -23.5629, -46.6932),
    ("Vila Madalena",       -23.5567, -46.6914),
    ("Jardins",             -23.5726, -46.6553),
    ("Itaim Bibi",          -23.5867, -46.6755),
    ("Brooklin",            -23.6177, -46.6946),
    ("Santo André",         -23.6639, -46.5383),
    ("Tatuapé",             -23.5389, -46.5729),
    ("Santana",             -23.5031, -46.6267),
    ("Lapa",                -23.5221, -46.7065),
    ("Vila Prudente",       -23.5875, -46.5697),
    ("Perdizes",            -23.5352, -46.6611),
    ("Morumbi",             -23.6203, -46.7195),
    ("Campo Belo",          -23.6221, -46.6657),
    ("Butantã",             -23.5712, -46.7310),
    ("Aclimação",           -23.5680, -46.6320),
    ("Bela Vista",          -23.5578, -46.6441),
    ("Bom Retiro",          -23.5261, -46.6371),
    ("Brás",                -23.5450, -46.6170),
    ("Cambuci",             -23.5701, -46.6194),
    ("Consolação",          -23.5510, -46.6580),
    ("Higienópolis",        -23.5423, -46.6572),
    ("Ipiranga",            -23.5908, -46.6053),
    ("Liberdade",           -23.5583, -46.6352),
    ("Mooca",               -23.5508, -46.6025),
    ("Paraíso",             -23.5751, -46.6479),
    ("Saúde",               -23.5966, -46.6324),
    ("Vila Mariana",        -23.5876, -46.6380),
    ("Água Funda",          -23.6214, -46.6108),
    ("Alto de Pinheiros",   -23.5446, -46.7148),
    ("Barra Funda",         -23.5266, -46.6650),
    ("Casa Verde",          -23.5063, -46.6560),
    ("Cidade Ademar",       -23.6639, -46.6611),
    ("Cidade Dutra",        -23.7008, -46.6611),
    ("Jabaquara",           -23.6448, -46.6422),
    ("Penha",               -23.5264, -46.5431),
    ("Pirituba",            -23.4869, -46.7197),
    ("Sapopemba",           -23.6058, -46.5197),
    ("Vila Andrade",        -23.6418, -46.7248),
    ("Vila Guilherme",      -23.5086, -46.5986),
    ("Vila Leopoldina",     -23.5261, -46.7381),
    ("Vila Sônia",          -23.5942, -46.7402),
    ("Sacomã",              -23.6097, -46.5928),
    ("Cursino",             -23.6117, -46.6197),
    ("Mandaqui",            -23.4878, -46.6378),
]

PROPERTY_TYPES = ["apartment", "house", "studio", "commercial", "penthouse"]

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
    None,
    None,
]


def random_coords(lat_base, lon_base):
    return (
        round(lat_base + random.uniform(-0.008, 0.008), 6),
        round(lon_base + random.uniform(-0.008, 0.008), 6),
    )


def generate_record():
    neighborhood, lat_base, lon_base = random.choice(SP_NEIGHBORHOODS)
    lat, lon = random_coords(lat_base, lon_base)
    prop_type = random.choice(PROPERTY_TYPES)

    area = round(random.uniform(35, 280), 1)

    if prop_type == "studio":
        bedrooms, bathrooms = 0, 1
        price = round(random.uniform(200_000, 500_000), 2)
    elif prop_type == "apartment":
        bedrooms = random.randint(1, 4)
        bathrooms = random.randint(1, bedrooms + 1)
        price = round(random.uniform(350_000, 2_500_000), 2)
    elif prop_type == "house":
        bedrooms = random.randint(2, 5)
        bathrooms = random.randint(1, bedrooms)
        price = round(random.uniform(600_000, 5_000_000), 2)
    elif prop_type == "penthouse":
        bedrooms = random.randint(3, 5)
        bathrooms = random.randint(2, 4)
        price = round(random.uniform(1_500_000, 8_000_000), 2)
    else:  # commercial
        bedrooms, bathrooms = 0, 1
        price = round(random.uniform(400_000, 3_000_000), 2)

    parking = random.randint(0, 3)
    condo_fee = round(random.uniform(300, 2500), 2) if prop_type != "house" else 0.0
    year_built = random.randint(1975, 2024)
    furnished = random.choice([True, False])

    seller_id = f"S-{uuid.uuid4().hex[:8].upper()}"
    buyer_id = f"B-{uuid.uuid4().hex[:8].upper()}" if random.random() > 0.3 else None
    buyer_note = random.choice(BUYER_NOTES) if buyer_id else None

    return {
        "record_id":        str(uuid.uuid4()),
        "timestamp":        datetime.utcnow().isoformat(),
        "seller_id":        seller_id,
        "buyer_id":         buyer_id or "",
        "property_type":    prop_type,
        "neighborhood":     neighborhood,
        "city":             "São Paulo",
        "state":            "SP",
        "latitude":         lat,
        "longitude":        lon,
        "area_m2":          area,
        "bedrooms":         bedrooms,
        "bathrooms":        bathrooms,
        "parking_spots":    parking,
        "year_built":       year_built,
        "furnished":        furnished,
        "condo_fee_brl":    condo_fee,
        "price_brl":        price,
        "buyer_notes":      buyer_note or "",
    }


def push_to_github(filepath):
    filename = os.path.basename(filepath)
    commands = [
        ["git", "-C", REPO_PATH, "pull", "--rebase"],
        ["cp", filepath, os.path.join(REPO_PATH, "data", "raw", filename)],
        ["git", "-C", REPO_PATH, "add", f"data/raw/{filename}"],
        ["git", "-C", REPO_PATH, "commit", "-m", f"data: add {filename}"],
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

    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename = f"listings_{timestamp}.csv"
    filepath = os.path.join(OUTPUT_DIR, filename)

    records = [generate_record() for _ in range(batch_size)]
    fieldnames = list(records[0].keys())

    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)

    print(f"[{datetime.utcnow().isoformat()}] Generated {batch_size} records → {filename}")

    if push_to_github(filepath):
        print(f"[{datetime.utcnow().isoformat()}] Pushed {filename} to GitHub")
    else:
        print(f"[{datetime.utcnow().isoformat()}] Push failed — file kept locally at {filepath}")


if __name__ == "__main__":
    print(f"Generator started. Interval: {INTERVAL_SECONDS}s")
    while True:
        run()
        time.sleep(INTERVAL_SECONDS)
