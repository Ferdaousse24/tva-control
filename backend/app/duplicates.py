from datetime import timedelta
from decimal import Decimal as D


def find_duplicate(db_invoices, new: dict):
    """Retourne (facture_existante, 'certain'|'probable') ou (None, '').

    Certain : même empreinte de fichier, ou même ICE tiers + même n° + même sens.
    Probable : même tiers, même TTC, dates à moins de 3 jours (signalé sans bloquer).
    """
    for inv in db_invoices:
        if inv.status in ("doublon_ignore", "remplacee", "doublon_detecte"):
            continue
        if new.get("sha256") and inv.sha256 == new["sha256"]:
            return inv, "certain"
    for inv in db_invoices:
        if inv.status in ("doublon_ignore", "remplacee", "doublon_detecte"):
            continue
        if inv.direction != new["direction"]:
            continue
        same_party = (new["party_ice"] and inv.party_ice == new["party_ice"]) or \
                     (not new["party_ice"] and new["party_name"] and inv.party_name.lower() == new["party_name"].lower())
        if same_party and new["number"] and inv.number == new["number"]:
            return inv, "certain"
    for inv in db_invoices:
        if inv.status in ("doublon_ignore", "remplacee", "doublon_detecte") or inv.direction != new["direction"]:
            continue
        same_party = (new["party_ice"] and inv.party_ice == new["party_ice"]) or \
                     (new["party_name"] and inv.party_name.lower() == new["party_name"].lower())
        if same_party and D(inv.total_ttc) == D(new["total_ttc"]) and new["date"] and inv.date \
                and abs(inv.date - new["date"]) < timedelta(days=3):
            return inv, "probable"
    return None, ""
