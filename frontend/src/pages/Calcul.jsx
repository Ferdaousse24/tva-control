import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api'
import { useQuarter, mad, fdate, Banner, BackBtn } from '../ui.jsx'

export default function Calcul() {
  const { quarter } = useQuarter()
  const nav = useNavigate()
  const [c, setC] = useState(null)
  const [err, setErr] = useState('')
  useEffect(() => { setC(null); api.calcul(quarter.id).then(setC).catch((e) => setErr(e.message)) }, [quarter.id])
  if (err) return <div className="alert red">{err}</div>
  if (!c) return <div className="muted">Calcul en cours…</div>

  const d = c.deductible
  const due = c.tva_due > 0
  return (
    <>
      <div className="head hasback">
        <BackBtn to="/" />
        <div><h1>TVA du trimestre</h1><div className="sub">Étape 2 · Calculer — {c.label} (du {fdate(c.debut)} au {fdate(c.fin)}) · échéance {fdate(c.echeance)}</div></div>
        <button className="btn primary hide-m" onClick={() => nav('/declaration')}>Comparer avec la déclaration déposée</button>
      </div>

      {c.a_verifier.length > 0 && (
        <Banner action={<Link className="btn" to={`/factures/${c.a_verifier[0].id}`}>Vérifier</Link>}>
          <b>{c.a_verifier.length} facture(s) non validée(s) ne sont pas comptées :</b> {c.a_verifier.map((x) => x.filename).join(', ')}.
        </Banner>
      )}

      <div className="grid2">
        <section className="card">
          <h2>TVA collectée (ventes encaissées)</h2>
          <table>
            <thead><tr><th>Taux</th><th className="r">Base HT</th><th className="r">TVA</th></tr></thead>
            <tbody>
              {c.collectee.lignes.map((l) => <tr key={l.rate}><td>{l.rate} %</td><td className="r mono">{mad(l.base)}</td><td className="r mono">{mad(l.tva)}</td></tr>)}
              {c.collectee.lignes.length === 0 && <tr><td colSpan="3" className="muted">Aucune vente encaissée dans le trimestre</td></tr>}
              <tr><td><b>Total</b></td><td className="r mono"><b>{mad(c.collectee.base)}</b></td><td className="r mono"><b>{mad(c.collectee.tva)}</b></td></tr>
            </tbody>
          </table>
          <div className="muted">{c.nb_ventes} vente(s) encaissée(s){c.reportees.length > 0 && ` · reportée(s) au trimestre suivant : ${c.reportees.length}`}</div>
          {c.reportees.map((r) => <div key={r.id} className="muted">• {r.filename} — {r.party_name} : {r.motif}</div>)}
        </section>

        <section className="card">
          <h2>TVA déductible (achats payés, conformes)</h2>
          <div className="kv"><span>Base HT retenue</span><span className="mono">{mad(d.base)}</span></div>
          <div className="kv"><span>TVA avant prorata</span><span className="mono">{mad(d.tva_avant_prorata)}</span></div>
          <div className="kv"><span>Prorata de déduction</span><span className="mono">{d.prorata} %</span></div>
          <div className="kv"><span>dont charges</span><span className="mono">{mad(d.charges)}</span></div>
          <div className="kv"><span>dont immobilisations</span><span className="mono">{mad(d.immobilisations)}</span></div>
          <div className="kv total"><span>TVA déductible</span><span className="mono">{mad(d.tva)}</span></div>
          <div className="muted">{c.nb_achats} achat(s) payé(s) dans le trimestre</div>
        </section>
      </div>

      <section className="card result">
        <h2>Résultat du trimestre <span className="badge b-amber">{c.statut}</span></h2>
        <div className="kv"><span>TVA collectée</span><span className="mono">{mad(c.collectee.tva)}</span></div>
        <div className="kv"><span>− TVA déductible</span><span className="mono">{mad(d.tva)}</span></div>
        <div className="kv"><span>− Crédit de TVA {c.trimestre_precedent}</span><span className="mono">{mad(c.credit_anterieur)}</span></div>
        {c.ras_subie > 0 && <div className="kv"><span>− Retenue à la source subie</span><span className="mono">{mad(c.ras_subie)}</span></div>}
        <div className="kv total"><span>{due ? 'TVA à payer' : 'Crédit à reporter'}</span>
          <span className="big mono">{mad(due ? c.tva_due : c.credit_a_reporter)}</span></div>
        {c.arrondi !== 0 && <div className="muted">Arrondi au dirham : {mad(c.arrondi, 2)}</div>}
      </section>

      {c.exclusions.length > 0 && (
        <section className="card">
          <h2>TVA exclue du calcul</h2>
          <table className="stack">
            <thead><tr><th>Facture</th><th>Tiers</th><th className="r">TVA exclue</th><th>Motif</th></tr></thead>
            <tbody>{c.exclusions.map((x, i) => (
              <tr key={i}><td className="full title"><Link to={`/factures/${x.id}`}>{x.filename}</Link></td><td data-l="Tiers">{x.party_name || '—'}</td><td data-l="TVA exclue" className="r mono">{mad(x.tva)}</td><td className="full" data-l="Motif">{x.motif}</td></tr>
            ))}</tbody>
          </table>
        </section>
      )}

      <div className="actionbar only-m"><button className="btn primary" onClick={() => nav('/declaration')}>Comparer avec la déclaration</button></div>
    </>
  )
}
