"""Lecture d'une facture : PDF (texte) ou image/scan (OCR) -> champs structurés + confiance.

Deux étapes : (1) obtenir des lignes de texte avec une confiance, (2) interpréter ces lignes.
L'étape 2 est ici un analyseur à règles ; elle peut être remplacée par un modèle de vision
sans toucher au reste (même format de sortie).
"""
from __future__ import annotations
import re
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from . import config

NUM = r"\d{1,3}(?:[ \u00a0.]\d{3})+(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?"


def parse_amount(s: str):
    if s is None:
        return None
    s = s.replace(" ", " ").strip()
    s = re.sub(r"[^\d,.\- ]", "", s).strip()
    if not s:
        return None
    s = s.replace(" ", "")
    if "," in s and "." in s:
        # le dernier séparateur est le séparateur décimal
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        # « 1,200 » (3 chiffres après) = milliers ; sinon virgule décimale
        s = s.replace(",", "") if re.fullmatch(r"\d{1,3}(,\d{3})+", s) else s.replace(",", ".")
    elif "." in s and re.fullmatch(r"\d{1,3}(\.\d{3})+", s):
        s = s.replace(".", "")
    try:
        return Decimal(s)
    except InvalidOperation:
        return None


def parse_date(s: str):
    m = re.search(r"(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})", s)
    if not m:
        return None
    try:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    except ValueError:
        return None


# ---------------------------------------------------------------- étape 1 : texte
def lines_from_pdf(path: Path):
    import pdfplumber
    lines = []
    with pdfplumber.open(str(path)) as pdf:
        for page in pdf.pages:
            txt = page.extract_text() or ""
            lines += [(l.strip(), 0.99) for l in txt.splitlines() if l.strip()]
    return lines


def _estimate_skew(g):
    """Angle de rotation (degrés) par profil de projection ; 0 si le gain est faible."""
    import cv2
    import numpy as np
    small = cv2.resize(g, None, fx=0.4, fy=0.4, interpolation=cv2.INTER_AREA)
    bw = cv2.adaptiveThreshold(small, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 31, 12)
    h, w = bw.shape
    best, best_angle, base = -1.0, 0.0, None
    for a in np.arange(-6, 6.01, 0.5):
        M = cv2.getRotationMatrix2D((w / 2, h / 2), a, 1.0)
        r = cv2.warpAffine(bw, M, (w, h), flags=cv2.INTER_NEAREST)
        v = float(np.var(r.sum(axis=1)))
        if abs(a) < 1e-9:
            base = v
        if v > best:
            best, best_angle = v, float(a)
    return best_angle if base and best > base * 1.08 else 0.0


def preprocess(img_bgr):
    """Niveaux de gris, agrandissement, redressement léger. (Un seuillage fort dégrade la lecture.)"""
    import cv2
    g = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    h, w = g.shape
    f = max(1.0, 2400 / max(h, w)) if max(h, w) < 2400 else 1.0
    if f > 1.0:
        g = cv2.resize(g, None, fx=f, fy=f, interpolation=cv2.INTER_CUBIC)
    angle = _estimate_skew(g)
    if angle:
        hh, ww = g.shape
        M = cv2.getRotationMatrix2D((ww / 2, hh / 2), angle, 1.0)
        g = cv2.warpAffine(g, M, (ww, hh), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
    return g


def _ocr_lang():
    import pytesseract
    try:
        langs = set(pytesseract.get_languages(config=""))
    except Exception:
        langs = {"eng"}
    return "fra+eng" if "fra" in langs else "eng"


def clean_ocr(t: str) -> str:
    """Corrige les artefacts fréquents de l'OCR dans les montants (« 2.:000,00 » -> « 2.000,00 »)."""
    return re.sub(r"(?<=\d)[.,]?[:;'`´|!](?=\d)", ".", t)


def lines_from_image(img_bgr):
    import pytesseract
    img = preprocess(img_bgr)
    data = pytesseract.image_to_data(img, lang=_ocr_lang(), config="--psm 6", output_type=pytesseract.Output.DICT)
    rows = {}
    for i, txt in enumerate(data["text"]):
        if not txt.strip():
            continue
        key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        rows.setdefault(key, []).append((data["left"][i], txt, max(0.0, float(data["conf"][i])) / 100))
    out = []
    for key in sorted(rows):
        words = sorted(rows[key])
        out.append((clean_ocr(" ".join(w[1] for w in words)), sum(w[2] for w in words) / len(words)))
    return out


def lines_from_file(path: Path):
    """Retourne (lignes, source) avec source = 'pdf_texte' | 'ocr'."""
    import cv2
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        lines = lines_from_pdf(path)
        if sum(len(l) for l, _ in lines) > 40:
            return lines, "pdf_texte"
        import pypdfium2 as pdfium
        import numpy as np
        pdf = pdfium.PdfDocument(str(path))
        out = []
        for page in pdf:
            bmp = page.render(scale=2.5).to_pil().convert("RGB")
            out += lines_from_image(cv2.cvtColor(np.array(bmp), cv2.COLOR_RGB2BGR))
        return out, "ocr"
    img = cv2.imread(str(path))
    if img is None:
        raise ValueError("Fichier image illisible")
    return lines_from_image(img), "ocr"


# ---------------------------------------------------------------- étape 2 : interprétation
ISSUER_LABELS = re.compile(r"^(?:[ée]metteur|fournisseur|vendeur|soci[ée]t[ée])\b", re.I)
CLIENT_LABELS = re.compile(r"^(?:client|factur[ée]\s*[àa]|destinataire|acheteur)\b", re.I)


def _ice(text: str):
    m = re.search(r"ICE\s*[:;|\-]?\s*([0-9OoIl\s]{0,24})", text)
    if not m:
        return None
    digits = re.sub(r"\D", "", m.group(1).replace("O", "0").replace("o", "0").replace("I", "1").replace("l", "1"))
    return digits


def interpret(lines, direction: str) -> dict:
    texts = [t for t, _ in lines]
    confs = [c for _, c in lines]
    fields, conf = {}, {}

    def put(name, value, idx_or_list):
        fields[name] = value
        idxs = idx_or_list if isinstance(idx_or_list, (list, tuple)) else [idx_or_list]
        conf[name] = round(min(confs[i] for i in idxs), 2) if idxs else 0.0

    # numéro
    for i, t in enumerate(texts):
        m = re.search(r"(?:facture|invoice|fact\.?)\s*(?:n[°o]?|num[ée]ro|#)\s*[:\-]?\s*([A-Za-z0-9][\w\-/]{2,})", t, re.I)
        if m:
            put("number", m.group(1), i)
            break
    # date (première date du document hors lignes de paiement)
    for i, t in enumerate(texts):
        if re.search(r"pay[ée]|encaiss|r[ée]gl", t, re.I):
            continue
        d = parse_date(t)
        if d:
            put("date", d, i)
            break
    # blocs émetteur / client
    iss_i = next((i for i, t in enumerate(texts) if ISSUER_LABELS.search(t)), None)
    cli_i = next((i for i, t in enumerate(texts) if CLIENT_LABELS.search(t)), None)

    def block(start, stop):
        if start is None:
            return None
        idxs = list(range(start, (stop if stop and stop > start else min(start + 4, len(texts)))))
        name_line = re.sub(r"^[^:]*:\s*", "", texts[start]).strip() if ":" in texts[start] else ""
        name, ice, ice_idx = name_line, None, None
        for i in idxs:
            ic = _ice(texts[i])
            if ic is not None:
                ice, ice_idx = ic, i
            elif not name and i != start:
                name = texts[i]
        return {"name": name, "ice": ice, "ice_i": ice_idx, "start": start}

    issuer = block(iss_i, cli_i)
    client = block(cli_i, next((i for i, t in enumerate(texts) if re.search(r"d[ée]signation|description|taux", t, re.I) and i > (cli_i or 0)), None))
    party = issuer if direction == "achat" else client
    if party is None and direction == "achat" and texts:
        party = {"name": texts[0], "ice": None, "ice_i": None, "start": 0}
    if party:
        if party["name"]:
            put("party_name", party["name"].strip(" \u2018\u2019'`\u00b4|,;:!_\u2014-").strip(), party["start"])
        if party["ice"] is not None and party["ice_i"] is not None:
            put("party_ice", party["ice"], party["ice_i"])
        else:
            fields["party_ice"] = ""
            conf["party_ice"] = None  # absent : pas un problème de lecture
    # lignes de TVA par taux : « 20 % 6 000,00 1 200,00 »
    lns = []
    for i, t in enumerate(texts):
        m = re.search(rf"(?:^|\s)(\d{{1,2}}(?:[.,]\d)?)\s*%\s+({NUM})\s*(?:MAD|DH|DHS)?\s+({NUM})\s*(?:MAD|DH|DHS)?[^\d]{{0,8}}$", t, re.I)
        if m:
            base, tv = parse_amount(m.group(2)), parse_amount(m.group(3))
            if base is not None and tv is not None:
                lns.append(({"rate": int(Decimal(m.group(1).replace(",", "."))), "base_ht": base, "tva": tv}, i))
    # totaux
    def total(pattern, name):
        for i, t in enumerate(texts):
            m = re.search(pattern + rf"[^\d\-]*({NUM})", t, re.I)
            if m:
                v = parse_amount(m.group(1))
                if v is not None:
                    put(name, v, i)
                    return
    total(r"(?:total|montant|net)\s*(?:h\.?t\.?|hors\s*taxes?)", "total_ht")
    total(r"total\s*t\.?v\.?a\.?(?!\s*\d)", "total_tva")
    total(r"(?:total|montant|net\s*[àa]\s*payer)\s*(?:t\.?t\.?c\.?|toutes\s*taxes\s*comprises)|net\s*[àa]\s*payer", "total_ttc")
    if lns:
        fields["lines"] = [l for l, _ in lns]
        conf["lines"] = round(min(confs[i] for _, i in lns), 2)
        if "total_ht" not in fields:
            fields["total_ht"] = sum(l["base_ht"] for l, _ in lns)
            conf["total_ht"] = conf["lines"]
        if "total_tva" not in fields:
            fields["total_tva"] = sum(l["tva"] for l, _ in lns)
            conf["total_tva"] = conf["lines"]
    elif "total_ht" in fields:
        rate = None
        for i, t in enumerate(texts):
            m = re.search(r"tva\s*\(?\s*(\d{1,2})\s*%", t, re.I)
            if m:
                rate = int(m.group(1))
                break
        if rate is None and fields.get("total_tva") and fields["total_ht"]:
            rate = int(round(fields["total_tva"] / fields["total_ht"] * 100))
        if rate is not None:
            fields["lines"] = [{"rate": rate, "base_ht": fields["total_ht"], "tva": fields.get("total_tva", Decimal(0))}]
            conf["lines"] = conf.get("total_ht", 0.0)
    if "total_ttc" not in fields and "total_ht" in fields:
        fields["total_ttc"] = fields["total_ht"] + fields.get("total_tva", Decimal(0))
        conf["total_ttc"] = min(conf.get("total_ht", 0), conf.get("total_tva", conf.get("total_ht", 0)))
    # paiement
    for i, t in enumerate(texts):
        m = re.search(r"(?:pa[yv]\w{1,3}|encaiss\w{1,3}|r[ée]gl\w{1,3})\s*(?:le)?\s*:?\s*(\d{1,2}[/\-.]\d{1,2}[/\-.]\d{4})", t, re.I)
        if m:
            pd = parse_date(m.group(1))
            if pd:
                put("paid_date", pd, i)
                mode = re.search(r"esp[èe]ces|virement|ch[èe]que|effet|carte", t, re.I)
                if mode:
                    fields["pay_mode"] = {"esp": "especes", "vir": "virement", "chè": "cheque", "che": "cheque", "eff": "effet", "car": "carte"}[mode.group(0).lower()[:3]]
                amt = re.search(rf"montant\s*:?\s*({NUM})", t, re.I)
                if amt:
                    fields["paid_amount"] = parse_amount(amt.group(1))
                break
    return {"fields": fields, "confidence": conf}


def extract(path: Path, direction: str) -> dict:
    lines, source = lines_from_file(path)
    res = interpret(lines, direction)
    res["source"] = source
    res["text"] = "\n".join(t for t, _ in lines)
    return res
