"""Contrôles automatiques d'une facture. Retourne la liste des anomalies."""
from __future__ import annotations
from datetime import date, timedelta
from decimal import Decimal as D
from . import config, tva

# code -> (niveau, libellé). « error » = mention obligatoire manquante => facture d'achat non conforme.
LABELS = {
    "ice_missing": ("error", "ICE du fournisseur non renseigné"),
    "ice_format": ("error", "ICE invalide (15 chiffres attendus)"),
    "number_missing": ("error", "Numéro de facture manquant"),
    "date_missing": ("error", "Date de facture manquante"),
    "party_missing": ("error", "Identité du tiers manquante"),
    "totals_mismatch": ("warning", "HT + TVA ≠ TTC"),
    "tva_mismatch": ("warning", "TVA ≠ base × taux"),
    "rate_invalid": ("warning", "Taux de TVA non autorisé à la date de la facture"),
    "date_implausible": ("warning", "Date peu plausible"),
    "low_confidence": ("warning", "Champ lu avec une faible confiance"),
    "no_amount": ("warning", "Aucun montant lu"),
}
FIELD_OF = {"ice_missing": "party_ice", "ice_format": "party_ice", "number_missing": "number",
            "date_missing": "date", "party_missing": "party_name", "totals_mismatch": "total_ht",
            "tva_mismatch": "total_tva", "rate_invalid": "lines", "date_implausible": "date",
            "no_amount": "total_ht"}


def _issue(code, field=None, message=None):
    lvl, lab = LABELS[code]
    return {"code": code, "level": lvl, "field": field or FIELD_OF.get(code, ""), "message": message or lab}


def check_invoice(inv: dict) -> list[dict]:
    out = []
    achat = inv["direction"] == "achat"
    ice = (inv.get("party_ice") or "").strip()
    if achat:
        if not ice:
            out.append(_issue("ice_missing"))
        elif not (ice.isdigit() and len(ice) == 15):
            out.append(_issue("ice_format"))
        if not (inv.get("party_name") or "").strip():
            out.append(_issue("party_missing"))
        if not (inv.get("number") or "").strip():
            out.append(_issue("number_missing"))
    elif ice and not (ice.isdigit() and len(ice) == 15):
        out.append(_issue("ice_format"))
    d = inv.get("date")
    if d is None:
        if achat:
            out.append(_issue("date_missing"))
    elif d > date.today() + timedelta(days=1) or d < date.today() - timedelta(days=365 * 6):
        out.append(_issue("date_implausible"))
    ht, tv, ttc = D(inv["total_ht"]), D(inv["total_tva"]), D(inv["total_ttc"])
    if ht == 0 and ttc == 0:
        out.append(_issue("no_amount"))
    elif abs(ht + tv - ttc) > config.TOTALS_TOLERANCE:
        out.append(_issue("totals_mismatch"))
    for ln in inv.get("lines", []):
        if not tva.rate_allowed(ln["rate"], d):
            out.append(_issue("rate_invalid", "lines", f"Taux {ln['rate']} % non autorisé à cette date"))
        elif abs(tva.tva_from_ht(ln["base_ht"], ln["rate"]) - D(ln["tva"])) > config.TOTALS_TOLERANCE:
            out.append(_issue("tva_mismatch"))
    for field, conf in (inv.get("confidence") or {}).items():
        if conf is not None and conf < config.CONFIDENCE_THRESHOLD:
            out.append(_issue("low_confidence", field, f"Confiance faible ({round(conf * 100)} %)"))
    return out


def conformity(inv: dict, issues: list[dict]) -> tuple[bool, list[str]]:
    """Une facture d'achat est conforme si aucune mention obligatoire n'est manquante."""
    if inv["direction"] != "achat":
        return True, []
    motifs = [i["message"] for i in issues if i["level"] == "error"]
    return (not motifs), motifs
