from io import BytesIO
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from . import config


def mad(x):
    return f"{x:,.2f}".replace(",", " ").replace(".", ",") + " MAD"


def build_pdf(calc: dict, cmp: dict) -> bytes:
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm, topMargin=2 * cm, bottomMargin=2 * cm,
                            title=f"Rapport de contrôle T{calc['q']} {calc['year']}")
    st = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=st["Title"], textColor=colors.HexColor("#A0366D"), alignment=0, fontSize=20)
    h2 = ParagraphStyle("h2", parent=st["Heading2"], fontSize=13, textColor=colors.HexColor("#111827"))
    body = ParagraphStyle("b", parent=st["BodyText"], fontSize=10, leading=14)
    small = ParagraphStyle("s", parent=body, fontSize=8, textColor=colors.HexColor("#6B7280"))
    el = [Paragraph(f"Rapport de contrôle de la TVA — T{calc['q']} {calc['year']}", h1),
          Paragraph(f"{config.COMPANY_NAME} · généré le {datetime.now():%d/%m/%Y %H:%M}", small), Spacer(1, 12)]

    ecart = cmp["ecart_tva_due"]
    if cmp["nb_ecarts"] == 0 and ecart <= 1:
        concl = "Aucun écart : la déclaration déposée est cohérente avec le recalcul."
    else:
        sens = {"inferieur": "inférieure", "superieur": "supérieure", "egal": "égale"}[cmp["sens"]]
        concl = (f"La TVA due déclarée est {sens} de {mad(ecart)} au recalcul. "
                 f"{cmp['nb_ecarts']} rubrique(s) présentent un écart : à vérifier avec le comptable.")
    el += [Paragraph("Conclusion", h2), Paragraph(concl, body), Spacer(1, 8)]

    el.append(Paragraph("Comparaison par rubrique", h2))
    data = [["Rubrique", "Déclaré", "Recalculé", "Écart"]]
    for r in cmp["lignes"]:
        data.append([r["label"], mad(r["declare"]), mad(r["recalcule"]), mad(r["ecart"]) if r["has_ecart"] else "0"])
    t = Table(data, colWidths=[6 * cm, 3.7 * cm, 3.7 * cm, 3.6 * cm])
    style = [("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F4F6FA")), ("FONTSIZE", (0, 0), (-1, -1), 9),
             ("ALIGN", (1, 0), (-1, -1), "RIGHT"), ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#E5E7EB")),
             ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold")]
    for i, r in enumerate(cmp["lignes"], start=1):
        if r["has_ecart"]:
            style.append(("BACKGROUND", (0, i), (-1, i), colors.HexColor("#FEE2E2")))
    t.setStyle(TableStyle(style))
    el += [t, Spacer(1, 10)]

    if cmp["origines"]:
        el.append(Paragraph("Origine des écarts", h2))
        for o in cmp["origines"]:
            el.append(Paragraph(f"<b>{o['label']}</b> — écart {mad(o['ecart'])}. {o['message']}", body))
            for f in o["factures"]:
                tva_txt = f" · TVA {mad(f['tva'])}" if f.get("tva") is not None else ""
                el.append(Paragraph(f"• {f['filename']} — {f['party_name'] or 'tiers inconnu'}{tva_txt} {('· ' + f['motif']) if f['motif'] else ''}", body))
        el.append(Spacer(1, 8))

    ded = calc["deductible"]
    el.append(Paragraph("Détail du recalcul", h2))
    d2 = [["Élément", "Montant"],
          ["TVA collectée", mad(calc["collectee"]["tva"])],
          [f"TVA déductible (prorata {ded['prorata']} %)", mad(ded["tva"])],
          ["Crédit antérieur", mad(calc["credit_anterieur"])],
          ["Retenue à la source subie", mad(calc["ras_subie"])],
          ["TVA due (arrondie au dirham)" if calc["tva_due"] > 0 else "Crédit à reporter", mad(calc["tva_due"] or calc["credit_a_reporter"])]]
    t2 = Table(d2, colWidths=[10 * cm, 7 * cm])
    t2.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F4F6FA")), ("FONTSIZE", (0, 0), (-1, -1), 9),
                            ("ALIGN", (1, 0), (-1, -1), "RIGHT"), ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#E5E7EB"))]))
    el += [t2, Spacer(1, 8)]
    if calc["exclusions"]:
        el.append(Paragraph("TVA exclue du recalcul", h2))
        for x in calc["exclusions"]:
            el.append(Paragraph(f"• {x['filename']} — {x['party_name'] or 'tiers inconnu'} — {mad(x['tva'])} — {x['motif']}", body))
    if calc["a_verifier"]:
        el.append(Paragraph(f"<b>Attention :</b> {len(calc['a_verifier'])} facture(s) non validée(s) ne sont pas incluses dans le recalcul.", body))
    if cmp.get("n_moins_1"):
        n = cmp["n_moins_1"]
        v = "" if n["variation"] is None else f" ({n['variation'] * 100:+.0f} %)"
        el.append(Paragraph(f"Comparaison avec T{calc['q']} {n['annee_precedente']} : {mad(n['valeur_precedente'])} → {mad(n['valeur_courante'])}{v}.", body))
    el += [Spacer(1, 16), Paragraph("Contrôle indicatif réalisé à partir des factures importées et des règles de calcul paramétrées. "
                                    "Il ne remplace pas l'avis d'un expert-comptable.", small)]
    doc.build(el)
    return buf.getvalue()
