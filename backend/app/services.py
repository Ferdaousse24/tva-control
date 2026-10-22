from __future__ import annotations
import hashlib
from datetime import date
from decimal import Decimal as D
from sqlalchemy.orm import Session
from pathlib import Path
from fastapi.encoders import jsonable_encoder
from . import checks, tva, config, extraction, duplicates
from sqlalchemy.orm import selectinload
from .models import Invoice, Quarter, Declaration, AuditLog, FileBlob, Payment, Company


def audit(db: Session, action: str, target: str = "", **detail):
    db.add(AuditLog(action=action, target=target, detail=detail))


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _num(x):
    return float(x) if x is not None else None


PAY_MODES = ("", "virement", "cheque", "effet", "especes", "carte")


def payments_view(inv: Invoice) -> list[dict]:
    """Paiements de la facture. Sans ligne dédiée, on reprend le paiement unique (anciennes factures)."""
    if inv.payments:
        return [{"date": p.date, "amount": D(p.amount), "mode": p.mode or ""} for p in inv.payments]
    if inv.paid_date and D(inv.paid_amount) > 0:
        return [{"date": inv.paid_date, "amount": D(inv.paid_amount), "mode": inv.pay_mode or ""}]
    return []


def set_payments(inv: Invoice, items: list[dict]):
    """Remplace les paiements et met à jour le résumé (date du dernier paiement, total payé, mode)."""
    inv.payments.clear()
    for p in sorted(items, key=lambda p: p["date"]):
        inv.payments.append(Payment(date=p["date"], amount=D(p["amount"]), mode=p.get("mode", "")))
    last = max(items, key=lambda p: p["date"]) if items else None
    inv.paid_date = last["date"] if last else None
    inv.paid_amount = sum((D(p["amount"]) for p in items), D(0))
    inv.pay_mode = last.get("mode", "") if last else ""


def inv_dict(inv: Invoice) -> dict:
    """Format commun pour les contrôles et le moteur de calcul."""
    return {"payments": payments_view(inv),
        "id": inv.id, "direction": inv.direction, "filename": inv.filename, "number": inv.number,
        "party_name": inv.party_name, "party_ice": inv.party_ice, "date": inv.date, "categorie": inv.categorie,
        "lines": inv.lines or [], "total_ht": D(inv.total_ht), "total_tva": D(inv.total_tva), "total_ttc": D(inv.total_ttc),
        "paid_date": inv.paid_date, "paid_amount": D(inv.paid_amount), "pay_mode": inv.pay_mode,
        "status": inv.status, "confidence": inv.confidence or {},
    }


def refresh_issues(inv: Invoice):
    d = inv_dict(inv)
    issues = checks.check_invoice(d)
    if inv.dup_kind == "probable" and inv.dup_of:
        issues.append({"code": "dup_probable", "level": "warning", "field": "number",
                       "message": "Doublon probable d'une facture déjà importée"})
    inv.issues = issues


def engine_dict(inv: Invoice) -> dict:
    d = inv_dict(inv)
    ok, motifs = checks.conformity(d, inv.issues or [])
    d["conforme"], d["motifs_non_conforme"] = ok, motifs
    d["forced"] = bool(inv.forced_comment)
    d["lines"] = [{"rate": l["rate"], "base_ht": D(str(l["base_ht"])), "tva": D(str(l["tva"]))} for l in d["lines"]]
    return d


def is_non_conforme(inv: Invoice) -> bool:
    ok, _ = checks.conformity(inv_dict(inv), inv.issues or [])
    return not ok


def serialize(inv: Invoice, full: bool = False) -> dict:
    out = {
        "id": inv.id, "direction": inv.direction, "filename": inv.filename, "number": inv.number,
        "date": inv.date.isoformat() if inv.date else None, "party_name": inv.party_name, "party_ice": inv.party_ice,
        "categorie": inv.categorie, "total_ht": _num(inv.total_ht), "total_tva": _num(inv.total_tva),
        "total_ttc": _num(inv.total_ttc), "paid_date": inv.paid_date.isoformat() if inv.paid_date else None,
        "paid_amount": _num(inv.paid_amount), "pay_mode": inv.pay_mode, "status": inv.status,
        "non_conforme": is_non_conforme(inv), "forced": bool(inv.forced_comment),
        "dup_of": inv.dup_of, "dup_kind": inv.dup_kind,
        "issues": inv.issues or [], "n_issues": len([i for i in (inv.issues or [])]),
        "payments": [{"date": p["date"].isoformat(), "amount": _num(p["amount"]), "mode": p["mode"]} for p in payments_view(inv)],
        "has_file": bool(inv.file_path), "manual": inv.extraction_source == "manuelle",
    }
    if full:
        out.update({
            "lines": inv.lines or [], "confidence": inv.confidence or {}, "original_values": inv.original_values or {},
            "extraction_source": inv.extraction_source, "forced_comment": inv.forced_comment,
            "dup_justification": inv.dup_justification, "file_url": f"/api/invoices/{inv.id}/file",
            "is_pdf": inv.filename.lower().endswith(".pdf"),
        })
    return out


def display_status(inv: Invoice) -> str:
    if inv.status == "validee":
        return "validee"
    return inv.status


def invoices_of_quarter(db: Session, year: int, q: int) -> list[Invoice]:
    start, end = tva.quarter_bounds(year, q)
    rows = db.query(Invoice).options(selectinload(Invoice.payments)).all()
    return [i for i in rows if (i.date and start <= i.date <= end)
            or any(start <= p["date"] <= end for p in payments_view(i))]


def credit_anterieur(db: Session, year: int, q: int) -> D:
    py, pq = tva.previous_quarter(year, q)
    d = db.query(Declaration).filter_by(year=py, q=pq).first()
    return D(d.credit_reporte) if d else D(0)


def calc_for(db: Session, quarter: Quarter) -> dict:
    invs = [engine_dict(i) for i in invoices_of_quarter(db, quarter.year, quarter.q)]
    return tva.compute_quarter(invs, quarter.year, quarter.q, quarter.prorata, quarter.ras_subie,
                               credit_anterieur(db, quarter.year, quarter.q))


def ingest(db: Session, filename: str, content: bytes, direction: str) -> Invoice:
    """Importe une facture : enregistre le fichier, lit les champs, contrôle, détecte les doublons.
    La facture reste « à vérifier » : rien n'entre dans le calcul sans validation humaine."""
    if direction not in ("vente", "achat"):
        raise ValueError("Sens invalide (vente ou achat)")
    ext = Path(filename).suffix.lower()
    if ext not in (".pdf", ".jpg", ".jpeg", ".png"):
        raise ValueError("Format non accepté (PDF, JPG ou PNG)")
    if not content:
        raise ValueError("Fichier vide")
    sha = sha256_bytes(content)
    path = config.UPLOAD_DIR / f"{sha}{ext}"
    path.write_bytes(content)
    if config.STORE_FILES_IN_DB and not db.get(FileBlob, sha):
        db.add(FileBlob(sha256=sha, content=content))
    try:
        res = extraction.extract(path, direction)
    except Exception as e:  # un fichier illisible ne doit pas bloquer les autres
        audit(db, "import_erreur", filename, motif=str(e))
        db.commit()
        raise ValueError(f"Lecture impossible : {e}")
    f = res["fields"]
    filename = filename[:255]
    lines = [{"rate": l["rate"], "base_ht": str(l["base_ht"]), "tva": str(l["tva"])} for l in f.get("lines", [])]
    ttc = f.get("total_ttc", D(0))
    inv = Invoice(
        direction=direction, filename=filename, file_path=str(path), sha256=sha,
        number=f.get("number", "")[:80], date=f.get("date"), party_name=f.get("party_name", "")[:200], party_ice=f.get("party_ice", "")[:30],
        lines=lines, total_ht=f.get("total_ht", D(0)), total_tva=f.get("total_tva", D(0)), total_ttc=ttc,
        paid_date=f.get("paid_date"), paid_amount=f.get("paid_amount", ttc if f.get("paid_date") else D(0)),
        pay_mode=f.get("pay_mode", ""), confidence=res["confidence"], extraction_source=res["source"], status="a_verifier",
    )
    inv.original_values = jsonable_encoder(dict(f), custom_encoder={D: str})
    if inv.paid_date and D(inv.paid_amount) > 0:
        set_payments(inv, [{"date": inv.paid_date, "amount": inv.paid_amount, "mode": inv.pay_mode}])
    dup, kind = duplicates.find_duplicate(db.query(Invoice).all(), {**inv_dict(inv), "sha256": sha})
    if dup:
        inv.dup_of, inv.dup_kind = dup.id, kind
        if kind == "certain":
            inv.status = "doublon_detecte"
    refresh_issues(inv)
    db.add(inv)
    db.flush()
    audit(db, "import", inv.filename, id=inv.id, sens=direction, source=res["source"], doublon=kind or None)
    db.commit()
    return inv


# ------------------------------------------------------------- fiche entreprise
COMPANY_FIELDS = ("raison_sociale", "forme_juridique", "adresse", "if_fiscal", "ice", "rc", "tribunal", "taxe_pro", "cnss")
COMPANY_MAX = {"raison_sociale": 200, "forme_juridique": 50, "adresse": 300, "if_fiscal": 20, "ice": 15,
               "rc": 40, "tribunal": 80, "taxe_pro": 30, "cnss": 30}


def company_dict(db: Session) -> dict:
    c = db.get(Company, 1)
    if c:
        out = {k: getattr(c, k) for k in COMPANY_FIELDS}
        out["configured"] = True
    else:  # valeurs par défaut (variables d'environnement) tant que la fiche n'est pas enregistrée
        out = {k: "" for k in COMPANY_FIELDS}
        out.update(raison_sociale=config.COMPANY_NAME, ice=config.COMPANY_ICE)
        out["configured"] = False
    out["complete"] = all(out[k].strip() for k in COMPANY_FIELDS)
    return out


def validate_company(body: dict) -> dict:
    data = {k: str(body.get(k) or "").strip() for k in COMPANY_FIELDS}
    errs = {}
    for k, n in COMPANY_MAX.items():
        if len(data[k]) > n:
            errs[k] = f"{n} caractères maximum"
    if not data["raison_sociale"]:
        errs["raison_sociale"] = "La raison sociale est obligatoire"
    if not (data["ice"].isdigit() and len(data["ice"]) == 15):
        errs["ice"] = "L'ICE doit comporter exactement 15 chiffres"
    if data["if_fiscal"] and not data["if_fiscal"].isdigit():
        errs["if_fiscal"] = "L'identifiant fiscal doit être numérique"
    return data, errs
