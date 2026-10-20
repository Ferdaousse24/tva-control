"""Moteur de calcul de la TVA : fonctions pures, sans IA, sans base de données.

Toutes les valeurs sont des Decimal. Les règles marquées « paramètre » sont
modifiables dans config.py ou dans la table des taux.
"""
from __future__ import annotations
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP, ROUND_CEILING
from typing import Iterable
from . import config

D = Decimal
CENT = D("0.01")

# Table des taux avec dates de validité : (taux %, début, fin)
RATES = [
    (D(20), date(1900, 1, 1), None),
    (D(10), date(1900, 1, 1), None),
    (D(0), date(1900, 1, 1), None),
    (D(14), date(1900, 1, 1), date(2025, 12, 31)),
    (D(7), date(1900, 1, 1), date(2025, 12, 31)),
]


def q2(x) -> Decimal:
    return D(x).quantize(CENT, rounding=ROUND_HALF_UP)


def round_dirham(x) -> Decimal:
    return D(x).quantize(D("1"), rounding=ROUND_HALF_UP)


def rate_allowed(rate, on: date | None) -> bool:
    if on is None:
        return any(D(rate) == r for r, _, _ in RATES)
    return any(D(rate) == r and d0 <= on and (d1 is None or on <= d1) for r, d0, d1 in RATES)


def tva_from_ht(base, rate) -> Decimal:
    return q2(D(base) * D(rate) / D(100))


def tva_in_payment(amount_ttc_paid, rate) -> Decimal:
    """TVA contenue dans un encaissement TTC : encaissé × t / (1 + t)."""
    t = D(rate) / D(100)
    return q2(D(amount_ttc_paid) * t / (1 + t))


def quarter_bounds(year: int, q: int) -> tuple[date, date]:
    start = date(year, 3 * (q - 1) + 1, 1)
    nxt = date(year + 1, 1, 1) if q == 4 else date(year, 3 * q + 1, 1)
    return start, nxt - timedelta(days=1)


def previous_quarter(year: int, q: int) -> tuple[int, int]:
    return (year - 1, 4) if q == 1 else (year, q - 1)


def deadline(year: int, q: int) -> date:
    """Échéance retenue : dernier jour du mois suivant le trimestre (à confirmer, sources divergentes)."""
    _, end = quarter_bounds(year, q)
    y, m = (end.year + 1, 1) if end.month == 12 else (end.year, end.month + 1)
    nxt = date(y + 1, 1, 1) if m == 12 else date(y, m + 1, 1)
    return nxt - timedelta(days=1)


def prorata_ceil(taxable, exonere_deductible, total) -> int:
    total = D(total)
    if total <= 0:
        return 100
    pct = (D(taxable) + D(exonere_deductible)) / total * 100
    return int(pct.to_integral_value(rounding=ROUND_CEILING))


def paid_fraction(inv) -> Decimal:
    ttc = D(inv["total_ttc"])
    if ttc <= 0:
        return D(0)
    return min(D(1), D(inv["paid_amount"]) / ttc)


def _in(d: date | None, a: date, b: date) -> bool:
    return d is not None and a <= d <= b


def compute_quarter(invoices: Iterable[dict], year: int, q: int, prorata: int = 100,
                    ras_subie=0, credit_anterieur=0) -> dict:
    """Calcule la TVA du trimestre (fait générateur : encaissement / paiement).

    Chaque facture est un dict avec : id, direction, filename, number, party_name, date,
    lines[{rate, base_ht, tva}], total_ttc, paid_date, paid_amount, pay_mode, party_ice,
    categorie, status, conforme, forced (bool), motifs_non_conforme.
    Seules les factures « validee » sont prises en compte ; les autres sont listées à part.
    """
    start, end = quarter_bounds(year, q)
    collectee = {}      # taux -> {base, tva}
    ded = {"charge": D(0), "immobilisation": D(0)}
    ded_base = {"charge": D(0), "immobilisation": D(0)}
    exclusions, reportees, a_verifier = [], [], []
    nb_ventes = nb_achats = 0

    cash_day, cash_month = {}, {}
    # cumul des paiements en espèces par fournisseur (jour / mois) pour appliquer les plafonds
    for inv in invoices:
        if inv["direction"] == "achat" and inv.get("pay_mode") == "especes" and _in(inv["paid_date"], start, end):
            k = (inv["party_ice"] or inv["party_name"], inv["paid_date"])
            cash_day[k] = cash_day.get(k, D(0)) + D(inv["paid_amount"])
            km = (inv["party_ice"] or inv["party_name"], inv["paid_date"].year, inv["paid_date"].month)
            cash_month[km] = cash_month.get(km, D(0)) + D(inv["paid_amount"])

    for inv in invoices:
        if inv["status"] in ("doublon_ignore", "remplacee", "doublon_detecte"):
            continue
        if inv["status"] != "validee":
            if (inv["date"] and _in(inv["date"], start, end)) or _in(inv["paid_date"], start, end):
                a_verifier.append(_ref(inv))
            continue
        paid_in_q = _in(inv["paid_date"], start, end)
        if not paid_in_q:
            if inv["direction"] == "vente" and inv["date"] and _in(inv["date"], start, end):
                reportees.append({**_ref(inv), "motif": "Non encaissée dans le trimestre"})
            continue
        frac = paid_fraction(inv)
        if inv["direction"] == "vente":
            nb_ventes += 1
            for ln in inv["lines"]:
                r = D(ln["rate"])
                base, tva = D(ln["base_ht"]) * frac, D(ln["tva"]) * frac
                c = collectee.setdefault(str(r.normalize()), {"rate": r, "base": D(0), "tva": D(0)})
                c["base"] += base
                c["tva"] += tva
            continue
        # --- achat payé dans le trimestre ---
        nb_achats += 1
        tva_total = sum((D(ln["tva"]) for ln in inv["lines"]), D(0)) * frac
        base_total = sum((D(ln["base_ht"]) for ln in inv["lines"]), D(0)) * frac
        motif = None
        if not inv["conforme"] and not inv.get("forced"):
            motif = "Non conforme : " + ", ".join(inv.get("motifs_non_conforme") or ["mention obligatoire manquante"])
        elif inv["categorie"] == "non_deductible":
            motif = "Dépense non déductible"
        if motif:
            exclusions.append({**_ref(inv), "tva": q2(tva_total), "base": q2(base_total), "motif": motif})
            continue
        # plafonds espèces
        if inv.get("pay_mode") == "especes":
            ident = inv["party_ice"] or inv["party_name"]
            day_total = cash_day.get((ident, inv["paid_date"]), D(0))
            month_total = cash_month.get((ident, inv["paid_date"].year, inv["paid_date"].month), D(0))
            over = D(0)
            if day_total > config.CASH_CAP_DAY:
                over = max(over, (day_total - config.CASH_CAP_DAY) / day_total)
            if month_total > config.CASH_CAP_MONTH:
                over = max(over, (month_total - config.CASH_CAP_MONTH) / month_total)
            if over > 0:
                part = q2(tva_total * over)
                exclusions.append({**_ref(inv), "tva": part, "base": q2(base_total * over),
                                   "motif": "Paiement en espèces au-delà du plafond"})
                tva_total -= part
                base_total -= q2(base_total * over)
        cat = "immobilisation" if inv["categorie"] == "immobilisation" else "charge"
        ded[cat] += tva_total
        ded_base[cat] += base_total

    rows = []
    col_total = col_base = D(0)
    for key in sorted(collectee, key=lambda k: -collectee[k]["rate"]):
        c = collectee[key]
        rows.append({"rate": int(c["rate"]), "base": q2(c["base"]), "tva": q2(c["tva"])})
        col_total += q2(c["tva"])
        col_base += q2(c["base"])
    pr = D(prorata) / 100
    ded_avant = q2(ded["charge"] + ded["immobilisation"])
    ded_charges = q2(ded["charge"] * pr)
    ded_immo = q2(ded["immobilisation"] * pr)
    ded_apres = ded_charges + ded_immo
    brut = col_total - D(ras_subie) - ded_apres - D(credit_anterieur)
    resultat = round_dirham(brut)
    return {
        "year": year, "q": q, "debut": start, "fin": end, "echeance": deadline(year, q),
        "collectee": {"lignes": rows, "base": q2(col_base), "tva": q2(col_total)},
        "deductible": {"base": q2(ded_base["charge"] + ded_base["immobilisation"]),
                       "tva_avant_prorata": ded_avant, "prorata": int(prorata),
                       "charges": ded_charges, "immobilisations": ded_immo, "tva": q2(ded_apres)},
        "ras_subie": q2(ras_subie), "credit_anterieur": q2(credit_anterieur),
        "resultat_brut": q2(brut), "arrondi": q2(resultat - brut),
        "tva_due": resultat if resultat > 0 else D(0),
        "credit_a_reporter": -resultat if resultat < 0 else D(0),
        "exclusions": exclusions, "reportees": reportees, "a_verifier": a_verifier,
        "nb_ventes": nb_ventes, "nb_achats": nb_achats,
    }


def _ref(inv: dict) -> dict:
    return {"id": inv["id"], "filename": inv["filename"], "number": inv["number"],
            "party_name": inv["party_name"], "direction": inv["direction"]}
