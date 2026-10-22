from pathlib import Path

S = Path(__file__).resolve().parent.parent.parent / "samples"


def seed(client):
    assert client.post("/api/demo/seed").json()["seeded"] is True
    return {q["label"]: q["id"] for q in client.get("/api/quarters").json()}


def test_seed_reproduces_mockup_after_validating_photo(client):
    qs = seed(client)
    t2 = qs["T2 2026"]
    c = client.get(f"/api/quarters/{t2}/calcul").json()
    assert c["collectee"]["tva"] == 30000
    assert len(c["a_verifier"]) == 1 and c["a_verifier"][0]["filename"] == "scan_0618.jpg"
    assert c["deductible"]["tva"] == 10000 and c["tva_due"] == 19000     # photo pas encore validée
    assert len(c["reportees"]) == 1                                         # vente encaissée en juillet
    assert c["exclusions"][0]["filename"] == "achat_electro_0420.pdf" and c["exclusions"][0]["tva"] == 1200
    photo = next(i for i in client.get(f"/api/quarters/{t2}/invoices").json() if i["filename"] == "scan_0618.jpg")
    assert client.post(f"/api/invoices/{photo['id']}/validate").status_code == 200
    c = client.get(f"/api/quarters/{t2}/calcul").json()
    assert c["deductible"]["tva"] == 12000 and c["tva_due"] == 17000 and c["credit_anterieur"] == 1000


def test_comparison_finds_electro_as_origin(client):
    t2 = seed(client)["T2 2026"]
    photo = next(i for i in client.get(f"/api/quarters/{t2}/invoices").json() if i["filename"] == "scan_0618.jpg")
    client.post(f"/api/invoices/{photo['id']}/validate")
    c = client.get(f"/api/quarters/{t2}/comparaison").json()
    rows = {r["key"]: r for r in c["lignes"]}
    assert rows["deductible"]["ecart"] == 1200 and rows["tva_due"]["ecart"] == -1200
    assert rows["collectee"]["has_ecart"] is False and rows["credit"]["has_ecart"] is False
    o = c["origines"][0]
    assert o["key"] == "deductible" and o["explique_entierement"] and o["factures"][0]["filename"] == "achat_electro_0420.pdf"
    assert c["sens"] == "inferieur" and c["ecart_tva_due"] == 1200
    assert c["n_moins_1"]["valeur_precedente"] == 14000 and round(c["n_moins_1"]["variation"], 2) == 0.21
    assert c["n_moins_1"]["alerte"] is False


def test_comparison_requires_declaration(client):
    qid = client.post("/api/quarters", json={"year": 2027, "q": 1}).json()["id"]
    assert client.get(f"/api/quarters/{qid}/comparaison").status_code == 409


def test_create_quarter_validation(client):
    assert client.post("/api/quarters", json={"year": 2026, "q": 5}).status_code == 422
    assert client.post("/api/quarters", json={"year": 2026, "q": 3}).status_code == 200
    assert client.post("/api/quarters", json={"year": 2026, "q": 3}).status_code == 409


def upload(client, name, sens):
    with open(S / name, "rb") as f:
        return client.post("/api/invoices/upload", data={"direction": sens}, files={"file": (name, f.read())})


def test_upload_non_conforme_flags_ice(client):
    r = upload(client, "achat_electro_0420.pdf", "achat").json()
    assert r["status"] == "a_verifier" and r["non_conforme"] is True
    assert any(i["code"] == "ice_missing" and i["level"] == "error" for i in r["issues"])


def test_corrections_are_audited_and_revalidate(client):
    r = upload(client, "achat_electro_0420.pdf", "achat").json()
    client.post(f"/api/invoices/{r['id']}/validate")
    r2 = client.patch(f"/api/invoices/{r['id']}", json={"party_ice": "001234512345123"}).json()
    assert r2["status"] == "a_verifier" and r2["non_conforme"] is False       # toute correction impose une nouvelle validation
    log = client.get("/api/audit").json()
    assert any(l["action"] == "correction" for l in log)


def test_force_inclusion_needs_comment(client):
    r = upload(client, "achat_electro_0420.pdf", "achat").json()
    assert client.post(f"/api/invoices/{r['id']}/force", json={"comment": ""}).status_code == 422
    assert client.post(f"/api/invoices/{r['id']}/force", json={"comment": "Attestation reçue du fournisseur"}).json()["forced"] is True


def test_duplicate_flow(client):
    first = upload(client, "vente_0405.pdf", "vente").json()
    dup = upload(client, "vente_0405.pdf", "vente").json()
    assert dup["status"] == "doublon_detecte" and dup["dup_of"] == first["id"] and dup["dup_kind"] == "certain"
    detail = client.get(f"/api/invoices/{dup['id']}").json()
    assert detail["dup_sha_identique"] is True
    assert client.post(f"/api/invoices/{dup['id']}/validate").status_code == 409
    assert client.post(f"/api/invoices/{dup['id']}/duplicate", json={"action": "conserver", "justification": ""}).status_code == 422
    assert client.post(f"/api/invoices/{dup['id']}/duplicate", json={"action": "ignorer"}).json()["status"] == "doublon_ignore"


def test_duplicate_replace_archives_original(client):
    first = upload(client, "vente_0405.pdf", "vente").json()
    dup = upload(client, "vente_0405.pdf", "vente").json()
    client.post(f"/api/invoices/{dup['id']}/duplicate", json={"action": "remplacer"})
    assert client.get(f"/api/invoices/{first['id']}").json()["status"] == "remplacee"


def test_rejects_bad_files(client):
    r = client.post("/api/invoices/upload", data={"direction": "achat"}, files={"file": ("x.exe", b"abc")})
    assert r.status_code == 422
    r = client.post("/api/invoices/upload", data={"direction": "achat"}, files={"file": ("x.pdf", b"pas un pdf")})
    assert r.status_code == 422


def test_report_pdf(client):
    t2 = seed(client)["T2 2026"]
    r = client.get(f"/api/quarters/{t2}/rapport.pdf")
    assert r.status_code == 200 and r.content.startswith(b"%PDF")


def test_explain_gap(client):
    t2 = seed(client)["T2 2026"]
    client.post(f"/api/quarters/{t2}/ecarts/deductible/expliquer", json={"comment": "Facture Electro Casa à régulariser"})
    rows = {r["key"]: r for r in client.get(f"/api/quarters/{t2}/comparaison").json()["lignes"]}
    assert rows["deductible"]["explique"] == "Facture Electro Casa à régulariser"


def test_password_protection(client, monkeypatch):
    monkeypatch.setenv("APP_PASSWORD", "secret123")
    assert client.get("/api/quarters").status_code == 401
    assert client.get("/api/health").status_code == 200
    import base64
    ok = {"Authorization": "Basic " + base64.b64encode(b"hamza:secret123").decode()}
    bad = {"Authorization": "Basic " + base64.b64encode(b"hamza:faux").decode()}
    assert client.get("/api/quarters", headers=ok).status_code == 200
    assert client.get("/api/quarters", headers=bad).status_code == 401


def test_very_long_values_do_not_crash(client):
    with open(S / "vente_0405.pdf", "rb") as f:
        r = client.post("/api/invoices/upload", data={"direction": "vente"}, files={"file": ("x" * 200 + ".pdf", f.read())})
    assert r.status_code == 200
    iid = r.json()["id"]
    assert client.patch(f"/api/invoices/{iid}", json={"number": "N" * 500}).status_code == 422
    assert client.patch(f"/api/invoices/{iid}", json={"party_name": "Z" * 150}).status_code == 200


def test_file_survives_disk_loss_when_stored_in_db(client, monkeypatch):
    from app import config
    monkeypatch.setattr(config, "STORE_FILES_IN_DB", True)
    with open(S / "vente_0405.pdf", "rb") as f:
        r = client.post("/api/invoices/upload", data={"direction": "vente"}, files={"file": ("a.pdf", f.read())})
    iid = r.json()["id"]
    from app.db import SessionLocal
    from app.models import Invoice
    with SessionLocal() as db:
        Path(db.get(Invoice, iid).file_path).unlink()  # le disque temporaire a été vidé
    got = client.get(f"/api/invoices/{iid}/file")
    assert got.status_code == 200 and got.content.startswith(b"%PDF")


def test_demo_reset_replaces_existing_data(client):
    assert client.post("/api/demo/seed").json()["seeded"] is True
    assert client.post("/api/demo/seed").json()["seeded"] is False  # déjà des factures
    r = client.post("/api/demo/reset")
    assert r.status_code == 200 and r.json()["seeded"] is True


# ------------------------------------------------ fiche entreprise, saisie manuelle, paiements
def _manual(**kw):
    body = {"direction": "vente", "number": "F-100", "date": "2026-05-10", "party_name": "Client SA", "party_ice": "001234567890123",
            "lines": [{"rate": 20, "base_ht": 1000, "tva": 200}], "total_ht": 1000, "total_tva": 200, "total_ttc": 1200}
    body.update(kw)
    return body


def test_company_card_validation_and_defaults(client):
    c = client.get("/api/company").json()
    assert c["configured"] is False and c["complete"] is False
    bad = client.put("/api/company", json={"raison_sociale": "X", "ice": "123"})
    assert bad.status_code == 422 and "15 chiffres" in bad.json()["detail"]
    assert client.put("/api/company", json={"raison_sociale": "X", "ice": "001234567890123", "if_fiscal": "12AB"}).status_code == 422
    ok = client.put("/api/company", json={"raison_sociale": "CBS TECH MAROC", "ice": "001234567890123", "if_fiscal": "40123456",
                                          "forme_juridique": "SARL", "adresse": "Casablanca", "rc": "1", "tribunal": "Casablanca",
                                          "taxe_pro": "1", "cnss": "1"})
    assert ok.status_code == 200 and ok.json()["configured"] and ok.json()["complete"]
    assert client.get("/api/company").json()["if_fiscal"] == "40123456"


def test_manual_invoice_creates_quarter_and_is_counted_when_validated(client):
    r = client.post("/api/invoices/manual", json=_manual(validate=True, payments=[{"date": "2026-05-20", "amount": 1200, "mode": "virement"}]))
    assert r.status_code == 200
    inv = r.json()
    assert inv["status"] == "validee" and inv["manual"] and not inv["has_file"] and inv["paid_amount"] == 1200
    calc = client.get(f"/api/quarters/{inv['quarter_id']}/calcul").json()
    assert calc["collectee"]["tva"] == 200
    assert client.get(f"/api/invoices/{inv['id']}/file").status_code == 404


def test_manual_invoice_requires_date_and_flags_duplicates(client):
    assert client.post("/api/invoices/manual", json=_manual(date="")).status_code == 422
    a = client.post("/api/invoices/manual", json=_manual()).json()
    b = client.post("/api/invoices/manual", json=_manual()).json()
    assert a["status"] == "a_verifier" and b["status"] == "doublon_detecte" and b["dup_of"] == a["id"]


def test_partial_payments_split_across_quarters_via_api(client):
    r = client.post("/api/invoices/manual", json=_manual(validate=True, payments=[
        {"date": "2026-06-20", "amount": 600, "mode": "virement"}, {"date": "2026-07-15", "amount": 600, "mode": "virement"}])).json()
    qs = {q["label"]: q["id"] for q in client.get("/api/quarters").json()}
    assert client.get(f"/api/quarters/{qs['T2 2026']}/calcul").json()["collectee"]["tva"] == 100
    client.post("/api/quarters", json={"year": 2026, "q": 3})
    qs = {q["label"]: q["id"] for q in client.get("/api/quarters").json()}
    assert client.get(f"/api/quarters/{qs['T3 2026']}/calcul").json()["collectee"]["tva"] == 100
    got = client.get(f"/api/invoices/{r['id']}").json()
    assert [p["amount"] for p in got["payments"]] == [600, 600] and got["paid_date"] == "2026-07-15"


def test_patch_payments_replaces_list_and_invalidates_validation(client):
    r = client.post("/api/invoices/manual", json=_manual(validate=True)).json()
    assert r["status"] == "validee" and r["payments"] == []
    p = client.patch(f"/api/invoices/{r['id']}", json={"payments": [{"date": "2026-05-12", "amount": 1500, "mode": "cheque"}]}).json()
    assert p["status"] == "a_verifier" and p["paid_amount"] == 1500
    assert any(i["code"] == "paid_exceeds" for i in p["issues"])
    assert client.patch(f"/api/invoices/{r['id']}", json={"payments": [{"date": "2026-05-12", "amount": -5}]}).status_code == 422
    assert client.patch(f"/api/invoices/{r['id']}", json={"payments": [{"date": "n'importe quoi", "amount": 5}]}).status_code == 422
    assert client.patch(f"/api/invoices/{r['id']}", json={"payments": []}).json()["paid_date"] is None


def test_legacy_single_payment_fields_still_work(client):
    r = client.post("/api/invoices/manual", json=_manual()).json()
    p = client.patch(f"/api/invoices/{r['id']}", json={"paid_date": "2026-05-20", "paid_amount": 1200, "pay_mode": "virement"}).json()
    assert [x["amount"] for x in p["payments"]] == [1200]


def test_imported_invoice_gets_a_payment_row(client):
    seed(client)
    qid = next(q["id"] for q in client.get("/api/quarters").json() if q["label"] == "T2 2026")
    inv = client.get(f"/api/quarters/{qid}/invoices").json()[0]
    assert len(client.get(f"/api/invoices/{inv['id']}").json()["payments"]) == (1 if inv["paid_date"] else 0)
