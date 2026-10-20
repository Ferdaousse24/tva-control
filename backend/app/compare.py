"""Comparaison déclaration du comptable vs recalcul."""
from __future__ import annotations
from decimal import Decimal as D
from . import config
from .tva import q2

TOLERANCE = D("1")  # arrondi au dirham


def _items(lst):
    return [{"id": x["id"], "filename": x["filename"], "party_name": x["party_name"], "tva": x.get("tva"), "motif": x.get("motif", "")} for x in lst]


def declared_result(decl) -> D:
    """TVA due signée : négatif = crédit à reporter."""
    return D(decl.tva_due) - D(decl.credit_reporte)


def computed_result(calc) -> D:
    return D(calc["tva_due"]) - D(calc["credit_a_reporter"])


def compare(calc: dict, decl, prev_decl, explained: dict) -> dict:
    d_col = D(decl.collectee_20) + D(decl.collectee_10)
    d_ded = D(decl.deductible_charges) + D(decl.deductible_immo)
    pairs = [
        ("collectee", "TVA collectée", d_col, calc["collectee"]["tva"]),
        ("deductible", "TVA déductible", d_ded, calc["deductible"]["tva"]),
        ("credit", "Crédit antérieur", D(decl.credit_anterieur), calc["credit_anterieur"]),
        ("tva_due", "TVA due", declared_result(decl), computed_result(calc)),
    ]
    rows = []
    for key, label, declared, computed in pairs:
        ecart = q2(D(declared) - D(computed))
        rows.append({"key": key, "label": label, "declare": q2(declared), "recalcule": q2(computed),
                     "ecart": ecart, "has_ecart": abs(ecart) > TOLERANCE,
                     "explique": explained.get(key)})
    by = {r["key"]: r for r in rows}
    origins = []
    for key in ("collectee", "deductible", "credit"):
        r = by[key]
        if not r["has_ecart"]:
            continue
        origins.append(_origin(key, r, calc))
    n_ecarts = sum(1 for r in rows if r["has_ecart"] and r["key"] != "tva_due")
    total = abs(by["tva_due"]["ecart"])
    # N-1
    yoy = None
    if prev_decl is not None:
        prev = declared_result(prev_decl)
        cur = computed_result(calc)
        pct = None if prev == 0 else float((cur - prev) / abs(prev))
        yoy = {"annee_precedente": calc["year"] - 1, "valeur_precedente": q2(prev), "valeur_courante": q2(cur),
               "variation": pct, "alerte": pct is not None and abs(pct) > config.YOY_ALERT, "seuil": config.YOY_ALERT}
    return {"year": calc["year"], "q": calc["q"], "lignes": rows, "origines": origins,
            "nb_ecarts": n_ecarts, "ecart_tva_due": total,
            "sens": "inferieur" if by["tva_due"]["ecart"] < 0 else "superieur" if by["tva_due"]["ecart"] > 0 else "egal",
            "n_moins_1": yoy, "a_verifier": len(calc["a_verifier"])}


def _origin(key, row, calc):
    ecart = row["ecart"]
    if key == "deductible":
        if ecart > 0:
            items = calc["exclusions"]
            exact = [x for x in items if abs(x["tva"] - ecart) <= TOLERANCE]
            tot = sum((x["tva"] for x in items), D(0))
            full = bool(exact) or abs(tot - ecart) <= TOLERANCE
            shown = exact or items
            msg = ("La déclaration déduit plus de TVA que le recalcul : " +
                   ("l'écart correspond à des factures que l'application exclut." if full
                    else "les factures exclues n'expliquent qu'une partie de l'écart."))
        else:
            shown, full = calc["a_verifier"], False
            msg = "Le recalcul retient plus de TVA déductible que la déclaration : factures non déclarées ou à vérifier ?"
    elif key == "collectee":
        shown = calc["reportees"] if ecart > 0 else calc["a_verifier"]
        full = False
        msg = ("La déclaration comptabilise plus de TVA collectée que le recalcul : ventes non encaissées (déclaration au débit ?)."
               if ecart > 0 else "Le recalcul retient plus de TVA collectée : ventes oubliées ou à vérifier ?")
    else:
        shown, full = [], False
        msg = "Le crédit repris diffère du crédit calculé du trimestre précédent."
    return {"key": key, "label": row["label"], "ecart": ecart, "explique_entierement": full,
            "message": msg, "factures": _items(shown)}
