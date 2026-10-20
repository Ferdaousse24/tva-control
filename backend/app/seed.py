"""Données de démonstration : reproduit le trimestre T2 2026 des maquettes à partir des factures d'exemple."""
from decimal import Decimal as D
from pathlib import Path
from sqlalchemy.orm import Session
from .models import Quarter, Invoice, Declaration
from .services import ingest, refresh_issues, audit

SAMPLES = Path(__file__).resolve().parent.parent.parent / "samples"
if not SAMPLES.exists():
    SAMPLES = Path(__file__).resolve().parent.parent / "samples"

# (fichier, sens, validée d'office ?)
FILES = [
    ("vente_0405.pdf", "vente", True), ("vente_0418.pdf", "vente", True), ("vente_0512.pdf", "vente", True),
    ("vente_0603.pdf", "vente", True), ("vente_0610.pdf", "vente", True), ("vente_0628.pdf", "vente", True),
    ("achat_0415.pdf", "achat", True), ("achat_0502.pdf", "achat", True), ("achat_0520.pdf", "achat", True),
    ("achat_electro_0420.pdf", "achat", True),
    ("scan_0618.jpg", "achat", False),  # photo laissée « à vérifier » : à valider dans la démo
]
CAT = {"achat_0520.pdf": "charge"}


def seed(db: Session) -> dict:
    if db.query(Invoice).count():
        return {"seeded": False, "message": "Des factures existent déjà"}
    for y, q in [(2025, 3), (2025, 4), (2026, 1), (2026, 2)]:
        if not db.query(Quarter).filter_by(year=y, q=q).first():
            db.add(Quarter(year=y, q=q, prorata=100, explained={}))
    db.add_all([
        Declaration(year=2025, q=2, collectee_20=D(40000), deductible_charges=D(26000), tva_due=D(14000), source="manuelle"),
        Declaration(year=2026, q=1, collectee_20=D(20000), deductible_charges=D(21000), tva_due=D(0), credit_reporte=D(1000), source="manuelle"),
        Declaration(year=2026, q=2, collectee_20=D(30000), deductible_charges=D("13200"), credit_anterieur=D(1000), tva_due=D(15800), source="manuelle"),
    ])
    db.commit()
    n = 0
    for fn, sens, validate in FILES:
        p = SAMPLES / fn
        if not p.exists():
            continue
        inv = ingest(db, fn, p.read_bytes(), sens)
        if validate:
            inv.confidence = {k: 1.0 for k in (inv.confidence or {})}
            refresh_issues(inv)
            inv.status = "validee"
            audit(db, "validation", inv.filename, id=inv.id, source="demo")
            db.commit()
        n += 1
    return {"seeded": True, "factures": n}
