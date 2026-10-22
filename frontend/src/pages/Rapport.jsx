import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import { useQuarter, mad, BackBtn } from '../ui.jsx'

export default function Rapport() {
  const { quarter } = useQuarter()
  const nav = useNavigate()
  const [r, setR] = useState(null)
  const [err, setErr] = useState('')
  useEffect(() => { api.rapport(quarter.id).then(setR).catch((e) => setErr(e.message)) }, [quarter.id])
  if (err) return <div className="alert red">{err} <button className="btn" onClick={() => nav('/declaration')}>Saisir la déclaration</button></div>
  if (!r) return <div className="muted">Génération du rapport…</div>

  const c = r.comparaison
  const by = Object.fromEntries(c.lignes.map((l) => [l.key, l]))
  const ok = c.nb_ecarts === 0 && c.ecart_tva_due <= 1
  const sens = { inferieur: 'inférieure', superieur: 'supérieure', egal: 'égale' }[c.sens]
  const mailto = `mailto:?subject=${encodeURIComponent(`Contrôle TVA ${r.label}`)}&body=${encodeURIComponent(
    `Bonjour,\n\nVoici le rapport de contrôle de la TVA ${r.label} (PDF à joindre).\nTVA due déclarée : ${mad(by.tva_due.declare)} ; recalculée : ${mad(by.tva_due.recalcule)} ; écart : ${mad(Math.abs(by.tva_due.ecart))}.\n\nPouvez-vous m'expliquer ces écarts ?\n\nCordialement`)}`

  return (
    <>
      <div className="head hasback"><BackBtn to="/bilan" /><div><h1>Rapport de contrôle</h1><div className="sub">{r.label} · déclaration du comptable comparée au recalcul</div></div></div>
      <div className="stats">
        <div className="stat"><span>TVA due déclarée</span><b>{mad(by.tva_due.declare)}</b></div>
        <div className="stat"><span>TVA due recalculée</span><b>{mad(by.tva_due.recalcule)}</b></div>
        <div className="stat"><span>Écart</span><b style={{ color: ok ? 'var(--green)' : 'var(--orange)' }}>{mad(Math.abs(by.tva_due.ecart))}</b></div>
        <div className="stat"><span>Factures contrôlées</span><b>{r.nb_factures}</b></div>
      </div>
      <section className="card" style={ok ? { background: 'var(--green-bg)' } : { background: '#fff7ed', borderColor: '#fdba74' }}>
        <h2 style={{ color: ok ? 'var(--green)' : 'var(--orange)' }}>{ok ? 'Déclaration cohérente' : 'À vérifier avec le comptable'}</h2>
        <div>{ok ? 'Aucun écart significatif entre la déclaration déposée et le recalcul.'
          : `La TVA due déclarée est ${sens} de ${mad(c.ecart_tva_due)} au recalcul. ${c.origines.map((o) => o.message).join(' ')}`}</div>
        {c.a_verifier > 0 && <div><b>Attention :</b> {c.a_verifier} facture(s) non validée(s) ne sont pas incluses.</div>}
      </section>
      <section className="card">
        <h2>Détail des écarts</h2>
        <table className="stack">
          <thead><tr><th>Ligne</th><th className="r">Déclaré</th><th className="r">Recalculé</th><th className="r">Écart</th><th>Statut</th></tr></thead>
          <tbody>{c.lignes.map((l) => (
            <tr key={l.key}><td className="full title">{l.label}</td><td data-l="Déclaré" className="r mono">{mad(l.declare)}</td><td data-l="Recalculé" className="r mono">{mad(l.recalcule)}</td><td data-l="Écart" className="r mono">{l.has_ecart ? mad(Math.abs(l.ecart)) : '0'}</td>
              <td data-l="Statut">{!l.has_ecart ? <span className="badge b-green">OK</span> : l.explique ? <span className="badge b-blue" title={l.explique}>Expliqué</span> : <span className="badge b-amber">À vérifier</span>}</td></tr>
          ))}</tbody>
        </table>
      </section>
      <div className="row actionbar" style={{ justifyContent: 'flex-end' }}>
        <button className="btn hide-m" onClick={() => nav('/bilan')}>Retour à la comparaison</button>
        <a className="btn" href={mailto}>Envoyer au comptable</a>
        <a className="btn primary" href={`/api/quarters/${quarter.id}/rapport.pdf`}>Télécharger le PDF</a>
      </div>
    </>
  )
}
