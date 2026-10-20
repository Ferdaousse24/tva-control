"""Génère des factures d'exemple (PDF + photos) dans samples/. Données entièrement fictives."""
import random
from datetime import date
from pathlib import Path
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

OUT = Path(__file__).resolve().parent.parent / "samples"
COMPANY = ("CBS TECH MAROC", "002345678000012", "Bd Zerktouni, Casablanca")


def fmt(x, style="space"):
    s = f"{x:,.2f}"
    if style == "space":
        return s.replace(",", " ").replace(".", ",")
    if style == "dot":
        return s.replace(",", "X").replace(".", ",").replace("X", ".")
    return s.replace(",", "")


def invoice_pdf(path, *, number, d, other, direction, lines, paid=None, label="Émetteur", style="space", ice_shown=True, designation="Prestation"):
    """other = (nom, ice, adresse) du tiers. direction = 'achat' (le tiers est l'émetteur) ou 'vente' (le tiers est le client)."""
    issuer, client = (other, COMPANY) if direction == "achat" else (COMPANY, other)
    c = canvas.Canvas(str(path), pagesize=A4)
    W, H = A4
    y = H - 60
    c.setFont("Helvetica-Bold", 20); c.drawString(50, y, f"FACTURE N° {number}")
    c.setFont("Helvetica", 11); y -= 28; c.drawString(50, y, f"Date : {d:%d/%m/%Y}")
    y -= 40
    c.setFont("Helvetica-Bold", 11); c.drawString(50, y, f"{label} : {issuer[0]}")
    c.setFont("Helvetica", 10); y -= 15; c.drawString(50, y, issuer[2])
    if issuer is COMPANY or ice_shown:
        y -= 15; c.drawString(50, y, f"ICE : {issuer[1]}")
    y -= 30
    c.setFont("Helvetica-Bold", 11); c.drawString(50, y, f"Client : {client[0]}")
    c.setFont("Helvetica", 10); y -= 15; c.drawString(50, y, client[2])
    y -= 15; c.drawString(50, y, f"ICE : {client[1]}")
    y -= 40
    c.setFont("Helvetica-Bold", 10)
    c.drawString(50, y, "Désignation"); c.drawString(300, y, "Taux"); c.drawString(360, y, "Base HT"); c.drawString(460, y, "TVA")
    c.setFont("Helvetica", 10)
    ht = tv = 0
    for rate, base in lines:
        t = round(base * rate / 100, 2)
        y -= 20
        # ligne lisible par l'extraction : « 20 % 6 000,00 1 200,00 »
        c.drawString(50, y, designation); c.drawString(300, y, f"{rate} %"); c.drawString(360, y, fmt(base, style)); c.drawString(460, y, fmt(t, style))
        ht += base; tv += t
    y -= 40
    c.setFont("Helvetica", 11)
    c.drawString(300, y, f"Total HT : {fmt(ht, style)} MAD"); y -= 18
    c.drawString(300, y, f"Total TVA : {fmt(tv, style)} MAD"); y -= 18
    c.setFont("Helvetica-Bold", 12); c.drawString(300, y, f"Total TTC : {fmt(ht + tv, style)} MAD")
    if paid:
        y -= 40; c.setFont("Helvetica", 10)
        c.drawString(50, y, f"Payée le {paid[0]:%d/%m/%Y} par {paid[1]} - Montant : {fmt(ht + tv, style)} MAD")
    c.save()
    return ht, tv


def to_photo(pdf_path, out_path, angle=2.2, seed=3, blur_total=False):
    import numpy as np, cv2, pypdfium2 as pdfium
    random.seed(seed); np.random.seed(seed)
    pil = pdfium.PdfDocument(str(pdf_path))[0].render(scale=1.6).to_pil().convert("RGB")
    img = cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)
    h, w = img.shape[:2]
    if blur_total:  # zone du total HT légèrement floue, comme un reflet / un pli
        y0, y1 = int(h * 0.50), int(h * 0.54)
        img[y0:y1, int(w * 0.5):] = cv2.GaussianBlur(img[y0:y1, int(w * 0.5):], (0, 0), 2.6)
    bg = np.full((h + 160, w + 160, 3), (190, 205, 215), np.uint8)  # surface sombre autour de la feuille
    bg[80:80 + h, 80:80 + w] = img
    M = cv2.getRotationMatrix2D(((w + 160) / 2, (h + 160) / 2), angle, 1.0)
    bg = cv2.warpAffine(bg, M, (w + 160, h + 160), borderValue=(190, 205, 215))
    grad = np.linspace(0.86, 1.04, w + 160)[None, :, None]  # éclairage inégal
    bg = np.clip(bg * grad + np.random.normal(0, 4, bg.shape), 0, 255).astype(np.uint8)
    bg = cv2.GaussianBlur(bg, (0, 0), 0.8)
    cv2.imwrite(str(out_path), bg, [cv2.IMWRITE_JPEG_QUALITY, 72])


def main():
    OUT.mkdir(exist_ok=True)
    clients = [("Maroc Distribution SA", "001122334455667", "Av. Hassan II, Rabat"),
               ("Atlas Services SARL", "001987654321098", "Rue des FAR, Casablanca"),
               ("Sahara Négoce", "002233445566778", "Bd Mohammed V, Marrakech"),
               ("Rif Equipements", "001555666777889", "Rue Ibn Sina, Tanger"),
               ("Anfa Conseil", "002111222333445", "Bd d'Anfa, Casablanca"),
               ("Oasis Import", "001777888999001", "Av. Mohammed VI, Agadir")]
    # ---- ventes T2 2026 : 150 000 HT à 20 % (une dernière vente encaissée en juillet : reportée au T3)
    ventes = [("vente_0405.pdf", "V-2026-031", date(2026, 4, 5), clients[0], 30000, date(2026, 4, 20), "virement", "space"),
              ("vente_0418.pdf", "V-2026-038", date(2026, 4, 18), clients[1], 40000, date(2026, 5, 6), "virement", "dot"),
              ("vente_0512.pdf", "V-2026-044", date(2026, 5, 12), clients[2], 25000, date(2026, 5, 30), "cheque", "space"),
              ("vente_0603.pdf", "V-2026-051", date(2026, 6, 3), clients[3], 35000, date(2026, 6, 25), "virement", "plain"),
              ("vente_0610.pdf", "V-2026-055", date(2026, 6, 10), clients[4], 20000, date(2026, 6, 28), "virement", "space"),
              ("vente_0628.pdf", "V-2026-062", date(2026, 6, 28), clients[5], 12000, date(2026, 7, 8), "virement", "space")]
    for fn, num, d, cl, base, pd, mode, st in ventes:
        invoice_pdf(OUT / fn, number=num, d=d, other=cl, direction="vente", lines=[(20, base)], paid=(pd, mode), label="Émetteur", style=st, designation="Prestations informatiques")
    # ---- achats : 60 000 HT conformes + Electro Casa sans ICE (non conforme)
    fournisseurs = [("Atlas Fournitures SARL", "001234567890123", "Zone industrielle, Casablanca"),
                    ("Maroc Telecom Pro", "000987654321098", "Av. Annakhil, Rabat"),
                    ("Immo Bureau SA", "001357924680135", "Rue Moulay Youssef, Casablanca"),
                    ("Papeterie Nador", "001246813579246", "Bd Hassan II, Nador"),
                    ("Electro Casa", "", "Derb Omar, Casablanca")]
    achats = [("achat_0415.pdf", "AF-2203", date(2026, 4, 15), fournisseurs[0], [(20, 18000)], date(2026, 4, 25), "virement", "Fournitures", "Fournisseur", "space", True),
              ("achat_0502.pdf", "MT-88412", date(2026, 5, 2), fournisseurs[1], [(20, 12000)], date(2026, 5, 15), "virement", "Télécom", "Émetteur", "dot", True),
              ("achat_0520.pdf", "IB-0147", date(2026, 5, 20), fournisseurs[2], [(20, 20000)], date(2026, 6, 4), "cheque", "Loyer bureau", "Fournisseur", "space", True),
              ("achat_electro_0420.pdf", "EC-0420", date(2026, 4, 20), fournisseurs[4], [(20, 6000)], date(2026, 4, 22), "virement", "Matériel électrique", "Émetteur", "space", False),
              ("achat_0618_source.pdf", "PN-5530", date(2026, 6, 18), fournisseurs[3], [(20, 10000)], date(2026, 6, 20), "virement", "Mobilier", "Émetteur", "space", True)]
    for fn, num, d, fr, lines, pd, mode, des, lab, st, ice in achats:
        invoice_pdf(OUT / fn, number=num, d=d, other=fr, direction="achat", lines=lines, paid=(pd, mode), label=lab, style=st, ice_shown=ice, designation=des)
    # la facture du 18/06 est fournie sous forme de photo (le PDF source n'est qu'un intermédiaire)
    to_photo(OUT / "achat_0618_source.pdf", OUT / "scan_0618.jpg", angle=2.4, seed=5, blur_total=True)
    (OUT / "achat_0618_source.pdf").unlink()
    # une deuxième photo, plus propre : facture de vente
    invoice_pdf(OUT / "_tmp.pdf", number="V-2026-066", d=date(2026, 6, 14), other=clients[2], direction="vente", lines=[(20, 8000), (10, 2000)],
                paid=(date(2026, 6, 29), "virement"), label="Émetteur", designation="Prestations")
    to_photo(OUT / "_tmp.pdf", OUT / "photo_vente_0614.jpg", angle=-1.6, seed=9)
    (OUT / "_tmp.pdf").unlink()
    print("Exemples générés dans", OUT)


if __name__ == "__main__":
    main()
