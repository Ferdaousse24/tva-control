from pathlib import Path
from decimal import Decimal as D
import pytest
from app import extraction

S = Path(__file__).resolve().parent.parent.parent / "samples"


@pytest.mark.parametrize("fn,sens,number,ht,tva,ice", [
    ("achat_0415.pdf", "achat", "AF-2203", 18000, 3600, "001234567890123"),
    ("vente_0418.pdf", "vente", "V-2026-038", 40000, 8000, "001987654321098"),   # montants « 40.000,00 »
    ("vente_0603.pdf", "vente", "V-2026-051", 35000, 7000, "001555666777889"),   # montants « 35000.00 »
])
def test_pdf_text_extraction(fn, sens, number, ht, tva, ice):
    f = extraction.extract(S / fn, sens)["fields"]
    assert f["number"] == number and f["total_ht"] == D(ht) and f["total_tva"] == D(tva) and f["party_ice"] == ice


def test_missing_ice_is_detected_not_invented():
    r = extraction.extract(S / "achat_electro_0420.pdf", "achat")
    assert r["fields"]["party_ice"] == "" and r["fields"]["party_name"] == "Electro Casa"


def test_company_ice_is_not_taken_as_supplier_ice():
    r = extraction.extract(S / "vente_0405.pdf", "vente")
    assert r["fields"]["party_ice"] == "001122334455667"       # le client, pas CBS TECH MAROC


@pytest.mark.parametrize("fn,sens,ht,ttc", [("scan_0618.jpg", "achat", 10000, 12000), ("photo_vente_0614.jpg", "vente", 10000, 11800)])
def test_photo_ocr_reads_amounts(fn, sens, ht, ttc):
    r = extraction.extract(S / fn, sens)
    assert r["source"] == "ocr"
    assert r["fields"]["total_ht"] == D(ht) and r["fields"]["total_ttc"] == D(ttc)
    assert max(r["confidence"].values()) < 0.99      # une photo n'a jamais la confiance d'un PDF texte


def test_photo_two_rates():
    r = extraction.extract(S / "photo_vente_0614.jpg", "vente")
    assert [(l["rate"], l["base_ht"]) for l in r["fields"]["lines"]] == [(20, D(8000)), (10, D(2000))]


def test_amount_parsing():
    p = extraction.parse_amount
    assert p("6 000,00") == D("6000.00") and p("6.000,00") == D("6000.00") and p("6000.00") == D("6000.00")
    assert p("12,000.00") == D("12000.00") and p("1.200") == D("1200") and p("abc") is None
