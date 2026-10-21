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
