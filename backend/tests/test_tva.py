from datetime import date
from decimal import Decimal as D
from app import tva


def inv(**kw):
    base = dict(id=1, direction="vente", filename="f.pdf", number="1", party_name="X", party_ice="001234567890123",
                date=date(2026, 5, 10), categorie="charge", lines=[{"rate": 20, "base_ht": D(1000), "tva": D(200)}],
                total_ttc=D(1200), paid_date=date(2026, 5, 20), paid_amount=D(1200), pay_mode="virement",
                status="validee", conforme=True, forced=False, motifs_non_conforme=[])
    base.update(kw)
    return base


def test_tva_from_ht_and_ttc():
    assert tva.tva_from_ht(6000, 20) == D("1200.00")
    assert tva.tva_in_payment(7200, 20) == D("1200.00")      # encaissé × t / (1 + t)
    assert tva.tva_in_payment(1100, 10) == D("100.00")


def test_quarter_bounds_and_deadline():
    assert tva.quarter_bounds(2026, 2) == (date(2026, 4, 1), date(2026, 6, 30))
    assert tva.quarter_bounds(2026, 4) == (date(2026, 10, 1), date(2026, 12, 31))
    assert tva.deadline(2026, 4) == date(2027, 1, 31)
    assert tva.previous_quarter(2026, 1) == (2025, 4)


def test_prorata_rounds_up():
    assert tva.prorata_ceil(600, 100, 1000) == 70
    assert tva.prorata_ceil(333, 0, 1000) == 34
    assert tva.prorata_ceil(0, 0, 0) == 100


def test_rates_by_date():
    assert tva.rate_allowed(20, date(2026, 5, 1))
    assert tva.rate_allowed(14, date(2025, 5, 1))
    assert not tva.rate_allowed(14, date(2026, 5, 1))     # supprimé en 2026
    assert not tva.rate_allowed(13, date(2026, 5, 1))


def test_collectee_deductible_and_result():
    invs = [inv(id=1, lines=[{"rate": 20, "base_ht": D(10000), "tva": D(2000)}], total_ttc=D(12000), paid_amount=D(12000)),
            inv(id=2, direction="achat", lines=[{"rate": 20, "base_ht": D(4000), "tva": D(800)}], total_ttc=D(4800), paid_amount=D(4800))]
    r = tva.compute_quarter(invs, 2026, 2, prorata=100, credit_anterieur=300)
    assert r["collectee"]["tva"] == D("2000.00")
    assert r["deductible"]["tva"] == D("800.00")
    assert r["tva_due"] == D(900)                     # 2000 − 800 − 300
    assert r["credit_a_reporter"] == 0


def test_negative_result_is_credit():
    invs = [inv(id=2, direction="achat", lines=[{"rate": 20, "base_ht": D(5000), "tva": D(1000)}], total_ttc=D(6000), paid_amount=D(6000))]
    r = tva.compute_quarter(invs, 2026, 2)
    assert r["tva_due"] == 0 and r["credit_a_reporter"] == D(1000)


def test_partial_payment_only_paid_share():
    i = inv(paid_amount=D(600))                       # moitié encaissée
    r = tva.compute_quarter([i], 2026, 2)
    assert r["collectee"]["tva"] == D("100.00")


def test_unpaid_sale_is_reported_not_counted():
    i = inv(paid_date=date(2026, 7, 8))
    r = tva.compute_quarter([i], 2026, 2)
    assert r["collectee"]["tva"] == 0 and len(r["reportees"]) == 1


def test_non_conforme_excluded_unless_forced():
    base = dict(direction="achat", conforme=False, motifs_non_conforme=["ICE manquant"])
    r = tva.compute_quarter([inv(**base)], 2026, 2)
    assert r["deductible"]["tva"] == 0 and r["exclusions"][0]["motif"].startswith("Non conforme")
    r2 = tva.compute_quarter([inv(**base, forced=True)], 2026, 2)
    assert r2["deductible"]["tva"] == D("200.00")


def test_unvalidated_invoice_is_not_counted():
    r = tva.compute_quarter([inv(status="a_verifier")], 2026, 2)
    assert r["collectee"]["tva"] == 0 and len(r["a_verifier"]) == 1


def test_prorata_applied_to_deductible():
    i = inv(direction="achat")
    r = tva.compute_quarter([i], 2026, 2, prorata=80)
    assert r["deductible"]["tva_avant_prorata"] == D("200.00") and r["deductible"]["tva"] == D("160.00")


def test_cash_cap_excludes_excess():
    i = inv(direction="achat", pay_mode="especes", lines=[{"rate": 20, "base_ht": D(10000), "tva": D(2000)}],
            total_ttc=D(12000), paid_amount=D(12000))
    r = tva.compute_quarter([i], 2026, 2)
    # 12 000 payés en espèces le même jour, plafond 5 000 : 7 000/12 000 de la TVA exclus
    assert r["exclusions"][0]["motif"].startswith("Paiement en espèces")
    assert r["deductible"]["tva"] == D("833.33") or r["deductible"]["tva"] == D("833.34")


def test_dirham_rounding():
    invs = [inv(lines=[{"rate": 20, "base_ht": D("1000.40"), "tva": D("200.08")}], total_ttc=D("1200.48"), paid_amount=D("1200.48"))]
    r = tva.compute_quarter(invs, 2026, 2)
    assert r["tva_due"] == D(200) and r["arrondi"] == D("-0.08")


def _two_payments():
    return [{"date": date(2026, 6, 20), "amount": D(600), "mode": "virement"},
            {"date": date(2026, 7, 15), "amount": D(600), "mode": "virement"}]


def test_sale_paid_in_two_installments_is_split_across_quarters():
    i = inv(payments=_two_payments())
    t2 = tva.compute_quarter([i], 2026, 2)
    t3 = tva.compute_quarter([i], 2026, 3)
    assert t2["collectee"]["tva"] == D("100.00") and t3["collectee"]["tva"] == D("100.00")
    assert not t3["reportees"]                         # la vente a bien un paiement dans T3


def test_overpayment_never_adds_vat():
    i = inv(payments=[{"date": date(2026, 5, 20), "amount": D(1000), "mode": ""},
                      {"date": date(2026, 5, 25), "amount": D(1000), "mode": ""}])
    assert tva.compute_quarter([i], 2026, 2)["collectee"]["tva"] == D("200.00")


def test_unpaid_installment_quarter_without_payment_is_reported():
    i = inv(payments=[{"date": date(2026, 8, 1), "amount": D(1200), "mode": ""}])
    r = tva.compute_quarter([i], 2026, 2)
    assert r["collectee"]["tva"] == 0 and len(r["reportees"]) == 1


def test_cash_cap_applies_across_same_day_installments():
    # 2 règlements en espèces le même jour chez le même fournisseur : 4 000 + 4 000 TTC > 5 000 /jour
    i = inv(direction="achat", lines=[{"rate": 20, "base_ht": D(6666.67), "tva": D(1333.33)}], total_ttc=D(8000),
            payments=[{"date": date(2026, 5, 20), "amount": D(4000), "mode": "especes"},
                      {"date": date(2026, 5, 20), "amount": D(4000), "mode": "especes"}])
    r = tva.compute_quarter([i], 2026, 2)
    assert any("espèces" in e["motif"] for e in r["exclusions"])
    assert r["deductible"]["tva"] < D("1333.33")


def test_payments_dict_matches_single_payment_fields():
    a = tva.compute_quarter([inv()], 2026, 2)["collectee"]["tva"]
    b = tva.compute_quarter([inv(payments=[{"date": date(2026, 5, 20), "amount": D(1200), "mode": "virement"}])], 2026, 2)["collectee"]["tva"]
    assert a == b == D("200.00")
