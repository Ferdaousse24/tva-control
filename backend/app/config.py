import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("DATA_DIR", BASE_DIR / "data"))
UPLOAD_DIR = DATA_DIR / "uploads"
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DATA_DIR / 'tva.db'}").strip()
# Supabase / Render fournissent « postgres:// » ou « postgresql:// » : on précise le pilote installé
for _p in ("postgres://", "postgresql://"):
    if DATABASE_URL.startswith(_p):
        DATABASE_URL = "postgresql+psycopg2://" + DATABASE_URL[len(_p):]

# Copie des fichiers importés dans la base (à activer si le disque du serveur est temporaire)
STORE_FILES_IN_DB = os.getenv("STORE_FILES_IN_DB", "0") == "1"

# Identité de l'entreprise (pour ne pas confondre son ICE avec celui du tiers)
COMPANY_NAME = os.getenv("COMPANY_NAME", "CBS TECH MAROC")
COMPANY_ICE = os.getenv("COMPANY_ICE", "002345678000012")

# Paramètres de contrôle (modifiables)
CONFIDENCE_THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", "0.85"))
TOTALS_TOLERANCE = 1  # MAD
CASH_CAP_DAY = 5000
CASH_CAP_MONTH = 50000
YOY_ALERT = 0.30
DEDUCTION_DEADLINE_DAYS = 365

DATA_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
