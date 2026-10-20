from __future__ import annotations
import json
import os
from datetime import date, datetime
from decimal import Decimal as D
from pathlib import Path
from fastapi import FastAPI, Depends, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse, Response, JSONResponse
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session
from . import config, extraction, tva, compare as cmp_mod, report, duplicates
from .db import Base, engine, get_db
from .models import Quarter, Invoice, Declaration, AuditLog
from .services import (audit, ingest, serialize, refresh_issues, invoices_of_quarter, calc_for,
                       credit_anterieur, inv_dict)

Base.metadata.create_all(engine)
app = FastAPI(title="Contrôle TVA trimestrielle", version="0.1")


@app.middleware("http")
async def basic_auth(request, call_next):
    """Mot de passe d'accès (HTTP Basic) si APP_PASSWORD est défini. Indispensable en ligne."""
    password = os.getenv("APP_PASSWORD")
    if password and request.url.path != "/api/health":
        import base64, hmac
        header = request.headers.get("authorization", "")
        ok = False
        if header.lower().startswith("basic "):
            try:
                user, _, pwd = base64.b64decode(header[6:]).decode().partition(":")
                ok = hmac.compare_digest(pwd, password) and hmac.compare_digest(user, os.getenv("APP_USER", "hamza"))
            except Exception:
                ok = False
        if not ok:
            return Response("Accès protégé", status_code=401, headers={"WWW-Authenticate": 'Basic realm="Controle TVA"'})
    return await call_next(request)


def _json(data):
    return JSONResponse(jsonable_encoder(data, custom_encoder={D: lambda v: float(v)}))


def _quarter(db, qid) -> Quarter:
    q = db.get(Quarter, qid)
    if not q:
        raise HTTPException(404, "Trimestre introuvable")
    return q


def _invoice(db, iid) -> Invoice:
    i = db.get(Invoice, iid)
    if not i:
        raise HTTPException(404, "Facture introuvable")
    return i


@app.get("/api/health")
def health():
    return {"ok": True}


# ----------------------------------------------------------------- trimestres
@app.get("/api/quarters")
def list_quarters(db: Session = Depends(get_db)):
    out = []
    for q in db.query(Quarter).order_by(Quarter.year.desc(), Quarter.q.desc()).all():
        invs = invoices_of_quarter(db, q.year, q.q)
        start, end = tva.quarter_bounds(q.year, q.q)
        out.append({"id": q.id, "year": q.year, "q": q.q, "label": f"T{q.q} {q.year}", "debut": start, "fin": end,
                    "echeance": tva.deadline(q.year, q.q), "nb_factures": len(invs),
                    "nb_a_verifier": sum(1 for i in invs if i.status in ("a_verifier", "doublon_detecte"))})
    return _json(out)


@app.post("/api/quarters")
def create_quarter(body: dict, db: Session = Depends(get_db)):
    year, qn = int(body.get("year", 0)), int(body.get("q", 0))
    if not (2000 <= year <= 2100 and qn in (1, 2, 3, 4)):
        raise HTTPException(422, "Année ou trimestre invalide")
    if db.query(Quarter).filter_by(year=year, q=qn).first():
        raise HTTPException(409, "Ce trimestre existe déjà")
    q = Quarter(year=year, q=qn, prorata=int(body.get("prorata", 100)), explained={})
    db.add(q)
    audit(db, "trimestre_cree", f"T{qn} {year}")
    db.commit()
    return _json({"id": q.id, "year": year, "q": qn, "label": f"T{qn} {year}"})


# ------------------------------------------------------------------- factures
@app.get("/api/quarters/{qid}/invoices")
def quarter_invoices(qid: int, direction: str | None = None, db: Session = Depends(get_db)):
    q = _quarter(db, qid)
    rows = invoices_of_quarter(db, q.year, q.q)
    if direction:
        rows = [r for r in rows if r.direction == direction]
    rows.sort(key=lambda r: (r.date or date.min, r.id), reverse=True)
    return _json([serialize(r) for r in rows])


@app.post("/api/invoices/upload")
async def upload(direction: str = Form(...), file: UploadFile = File(...), db: Session = Depends(get_db)):
    content = await file.read()
    try:
        inv = ingest(db, file.filename or "facture", content, direction)
    except ValueError as e:
        raise HTTPException(422, str(e))
    return _json(serialize(inv, full=True))


@app.get("/api/invoices/{iid}")
def get_invoice(iid: int, db: Session = Depends(get_db)):
    inv = _invoice(db, iid)
    out = serialize(inv, full=True)
    if inv.dup_of:
        orig = db.get(Invoice, inv.dup_of)
        if orig:
            out["dup_original"] = serialize(orig)
            out["dup_original"]["sha256"] = orig.sha256
            out["dup_sha_identique"] = orig.sha256 == inv.sha256
    return _json(out)


@app.get("/api/invoices/{iid}/file")
def invoice_file(iid: int, db: Session = Depends(get_db)):
    inv = _invoice(db, iid)
    p = Path(inv.file_path)
    if not p.exists():
        raise HTTPException(404, "Fichier source introuvable")
    media = {".pdf": "application/pdf", ".png": "image/png"}.get(p.suffix.lower(), "image/jpeg")
    return FileResponse(p, media_type=media, headers={"Content-Disposition": f'inline; filename="{inv.filename}"'})


EDITABLE = ("number", "date", "party_name", "party_ice", "categorie", "pay_mode", "paid_date", "paid_amount",
            "total_ht", "total_tva", "total_ttc", "lines", "direction")


def _apply(inv: Invoice, body: dict):
    before, after = {}, {}
    for k in EDITABLE:
        if k not in body:
            continue
        v = body[k]
        if k in ("date", "paid_date"):
            v = date.fromisoformat(v) if v else None
        elif k in ("paid_amount", "total_ht", "total_tva", "total_ttc"):
            v = D(str(v or 0))
        elif k == "lines":
            v = [{"rate": int(l["rate"]), "base_ht": str(D(str(l["base_ht"] or 0))), "tva": str(D(str(l["tva"] or 0)))} for l in v]
        elif k == "categorie" and v not in ("charge", "immobilisation", "non_deductible"):
            raise HTTPException(422, "Catégorie invalide")
        elif k == "direction" and v not in ("vente", "achat"):
            raise HTTPException(422, "Sens invalide")
        old = getattr(inv, k)
        if old != v:
            before[k], after[k] = old, v
            setattr(inv, k, v)
            if k in ("total_ht", "total_tva", "total_ttc", "lines"):
                conf = dict(inv.confidence or {})
                for c in ("total_ht", "total_tva", "total_ttc", "lines"):
                    if c in conf and k == c:
                        conf[c] = 1.0
                inv.confidence = conf
            elif k in (inv.confidence or {}):
                conf = dict(inv.confidence)
                conf[k] = 1.0
                inv.confidence = conf
    return before, after


@app.patch("/api/invoices/{iid}")
def patch_invoice(iid: int, body: dict, db: Session = Depends(get_db)):
    inv = _invoice(db, iid)
    if inv.status in ("doublon_ignore", "remplacee"):
        raise HTTPException(409, "Cette facture est écartée")
    before, after = _apply(inv, body)
    if before:
        if inv.status == "validee":
            inv.status = "a_verifier"  # toute modification impose une nouvelle validation
        refresh_issues(inv)
        audit(db, "correction", inv.filename, id=inv.id,
              avant=jsonable_encoder(before, custom_encoder={D: str}), apres=jsonable_encoder(after, custom_encoder={D: str}))
    db.commit()
    return _json(serialize(inv, full=True))


@app.post("/api/invoices/{iid}/validate")
def validate_invoice(iid: int, body: dict | None = None, db: Session = Depends(get_db)):
    inv = _invoice(db, iid)
    if inv.status == "doublon_detecte":
        raise HTTPException(409, "Résolvez d'abord le doublon")
    if body:
        _apply(inv, body)
    # la validation vaut vérification humaine de tous les champs lus
    inv.confidence = {k: 1.0 for k in (inv.confidence or {})}
    refresh_issues(inv)
    inv.status = "validee"
    audit(db, "validation", inv.filename, id=inv.id, non_conforme=any(i["level"] == "error" for i in inv.issues))
    db.commit()
    return _json(serialize(inv, full=True))


@app.post("/api/invoices/{iid}/force")
def force_include(iid: int, body: dict, db: Session = Depends(get_db)):
    inv = _invoice(db, iid)
    comment = (body.get("comment") or "").strip()
    if len(comment) < 5:
        raise HTTPException(422, "Un commentaire est obligatoire pour forcer l'inclusion")
    inv.forced_comment = comment
    audit(db, "inclusion_forcee", inv.filename, id=inv.id, commentaire=comment)
    db.commit()
    return _json(serialize(inv, full=True))


@app.post("/api/invoices/{iid}/unforce")
def unforce(iid: int, db: Session = Depends(get_db)):
    inv = _invoice(db, iid)
    inv.forced_comment = ""
    audit(db, "inclusion_forcee_retiree", inv.filename, id=inv.id)
    db.commit()
    return _json(serialize(inv, full=True))


@app.post("/api/invoices/{iid}/duplicate")
def resolve_duplicate(iid: int, body: dict, db: Session = Depends(get_db)):
    inv = _invoice(db, iid)
    if inv.status != "doublon_detecte":
        raise HTTPException(409, "Cette facture n'est pas un doublon en attente")
    action = body.get("action")
    just = (body.get("justification") or "").strip()
    orig = db.get(Invoice, inv.dup_of) if inv.dup_of else None
    if action == "ignorer":
        inv.status = "doublon_ignore"
    elif action == "remplacer":
        if orig:
            orig.status = "remplacee"
        inv.status = "a_verifier"
        inv.dup_kind = ""
    elif action == "conserver":
        if len(just) < 5:
            raise HTTPException(422, "Une justification est obligatoire pour conserver les deux factures")
        inv.status = "a_verifier"
        inv.dup_justification = just
    else:
        raise HTTPException(422, "Action inconnue (ignorer, remplacer, conserver)")
    refresh_issues(inv)
    audit(db, "doublon_" + action, inv.filename, id=inv.id, original=inv.dup_of, justification=just)
    db.commit()
    return _json(serialize(inv, full=True))


# --------------------------------------------------------------------- calcul
@app.get("/api/quarters/{qid}/calcul")
def calcul(qid: int, db: Session = Depends(get_db)):
    q = _quarter(db, qid)
    out = calc_for(db, q)
    out["statut"] = "Brouillon"
    out["label"] = f"T{q.q} {q.year}"
    py, pq = tva.previous_quarter(q.year, q.q)
    out["trimestre_precedent"] = f"T{pq} {py}"
    return _json(out)


# ---------------------------------------------------------------- déclaration
DECL_FIELDS = ("collectee_20", "collectee_10", "deductible_charges", "deductible_immo", "credit_anterieur", "tva_due", "credit_reporte")


def _decl_out(d: Declaration | None, year, q):
    if not d:
        return {"exists": False, "year": year, "q": q, **{k: 0 for k in DECL_FIELDS}, "source": "manuelle"}
    return {"exists": True, "year": year, "q": q, **{k: float(getattr(d, k)) for k in DECL_FIELDS}, "source": d.source}


@app.get("/api/quarters/{qid}/declaration")
def get_declaration(qid: int, db: Session = Depends(get_db)):
    q = _quarter(db, qid)
    d = db.query(Declaration).filter_by(year=q.year, q=q.q).first()
    out = _decl_out(d, q.year, q.q)
    out["credit_anterieur_calcule"] = float(credit_anterieur(db, q.year, q.q))
    return _json(out)


@app.put("/api/quarters/{qid}/declaration")
def put_declaration(qid: int, body: dict, db: Session = Depends(get_db)):
    q = _quarter(db, qid)
    d = db.query(Declaration).filter_by(year=q.year, q=q.q).first()
    if not d:
        d = Declaration(year=q.year, q=q.q)
        db.add(d)
    for k in DECL_FIELDS:
        if k in body:
            v = D(str(body[k] or 0))
            if v < 0:
                raise HTTPException(422, f"{k} ne peut pas être négatif")
            setattr(d, k, v)
    if D(d.tva_due) < 0:
        raise HTTPException(422, "La TVA due ne peut pas être négative (utilisez le crédit à reporter)")
    audit(db, "declaration_saisie", f"T{q.q} {q.year}", **{k: str(getattr(d, k)) for k in DECL_FIELDS})
    db.commit()
    return _json(_decl_out(d, q.year, q.q))


# ----------------------------------------------------------------- comparaison
def _comparison(db, q: Quarter):
    decl = db.query(Declaration).filter_by(year=q.year, q=q.q).first()
    if not decl:
        raise HTTPException(409, "Saisissez d'abord la déclaration du comptable")
    prev = db.query(Declaration).filter_by(year=q.year - 1, q=q.q).first()
    calc = calc_for(db, q)
    return calc, cmp_mod.compare(calc, decl, prev, q.explained or {})


@app.get("/api/quarters/{qid}/comparaison")
def comparaison(qid: int, db: Session = Depends(get_db)):
    q = _quarter(db, qid)
    calc, c = _comparison(db, q)
    c["label"] = f"T{q.q} {q.year}"
    return _json(c)


@app.post("/api/quarters/{qid}/ecarts/{key}/expliquer")
def explain(qid: int, key: str, body: dict, db: Session = Depends(get_db)):
    q = _quarter(db, qid)
    if key not in ("collectee", "deductible", "credit", "tva_due"):
        raise HTTPException(404, "Rubrique inconnue")
    comment = (body.get("comment") or "").strip()
    ex = dict(q.explained or {})
    if comment:
        ex[key] = comment
    else:
        ex.pop(key, None)
    q.explained = ex
    audit(db, "ecart_explique", f"T{q.q} {q.year}", rubrique=key, commentaire=comment)
    db.commit()
    return _json({"explained": ex})


@app.get("/api/quarters/{qid}/rapport")
def rapport_json(qid: int, db: Session = Depends(get_db)):
    q = _quarter(db, qid)
    calc, c = _comparison(db, q)
    return _json({"label": f"T{q.q} {q.year}", "calcul": calc, "comparaison": c,
                  "nb_factures": len(invoices_of_quarter(db, q.year, q.q))})


@app.get("/api/quarters/{qid}/rapport.pdf")
def rapport_pdf(qid: int, db: Session = Depends(get_db)):
    q = _quarter(db, qid)
    calc, c = _comparison(db, q)
    audit(db, "rapport_genere", f"T{q.q} {q.year}")
    db.commit()
    pdf = report.build_pdf(calc, c)
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="rapport_controle_T{q.q}_{q.year}.pdf"'})


@app.post("/api/demo/seed")
def demo_seed(db: Session = Depends(get_db)):
    from .seed import seed
    return _json(seed(db))


@app.get("/api/audit")
def audit_log(limit: int = 200, db: Session = Depends(get_db)):
    rows = db.query(AuditLog).order_by(AuditLog.id.desc()).limit(limit).all()
    return _json([{"id": r.id, "at": r.at, "action": r.action, "target": r.target, "detail": r.detail} for r in rows])


# ------------------------------------------------- interface web (si elle est compilée)
import os
from fastapi.staticfiles import StaticFiles

FRONT = Path(os.getenv("FRONTEND_DIR", config.BASE_DIR.parent / "frontend" / "dist"))
if (FRONT / "index.html").exists():
    app.mount("/assets", StaticFiles(directory=FRONT / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path.startswith("api/"):
            raise HTTPException(404, "Introuvable")
        f = (FRONT / path).resolve()
        if path and f.is_file() and FRONT.resolve() in f.parents:
            return FileResponse(f)
        return FileResponse(FRONT / "index.html")
