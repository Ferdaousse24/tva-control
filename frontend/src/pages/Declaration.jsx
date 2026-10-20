import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import { useQuarter, mad, Banner } from '../ui.jsx'

const FIELDS = [
  ['collectee_20', 'TVA collectée à 20 %'], ['collectee_10', 'TVA collectée à 10 %'],
  ['deductible_charges', 'TVA déductible sur charges'], ['deductible_immo', 'TVA déductible sur immobilisations'],
  ['credit_anterieur', 'Crédit de TVA reporté'], ['tva_due', 'TVA due déclarée'],
]
const n = (v) => Number(String(v ?? '').replace(/\s/g, '').replace(',', '.')) || 0

export default function Declaration() {
  const { quarter } = useQuarter()
  const nav = useNavigate()
  const [f, setF] = useState(null)
  const [err, setErr] = useState('')
  useEffect(() => { api.declaration(quarter.id).then((d) => setF(d)).catch((e) => setErr(e.message)) }, [quarter.id])
  if (!f) return <div className="muted">{err || 'Chargement…'}</div>

  const calculee = Math.round(n(f.collectee_20) + n(f.collectee_10) - n(f.deductible_charges) - n(f.deductible_immo) - n(f.credit_anterieur))
  const declaree = n(f.tva_due) - n(f.credit_reporte)
  const coherent = Math.abs(calculee - declaree) <= 1

  async function save(goto) {
    setErr('')
    try {
      await api.saveDeclaration(quarter.id, Object.fromEntries([...FIELDS.map(([k]) => k), 'credit_reporte'].map((k) => [k, n(f[k])])))
      nav(goto)
    } catch (e) { setErr(e.message) }
  }

  return (
    <>
      <div className="head"><div><h1>Déclaration du comptable</h1><div className="sub">{quarter.label} · saisissez les montants de la déclaration déposée pour les comparer au recalcul</div></div></div>
      <div className="split">
        <section className="card">
          <h2>Montants de la déclaration déposée</h2>
          <div className="grid2">
            {FIELDS.map(([k, label]) => (
              <label className="f" key={k}>{label}
                <div className="row"><input className="in r mono" inputMode="decimal" value={f[k]} onChange={(e) => setF({ ...f, [k]: e.target.value })} /><span className="muted">MAD</span></div>
              </label>
            ))}
          </div>
          <label className="f">Crédit à reporter (si la déclaration se solde par un crédit)
            <div className="row"><input className="in r mono" inputMode="decimal" value={f.credit_reporte ?? 0} onChange={(e) => setF({ ...f, credit_reporte: e.target.value })} /><span className="muted">MAD</span></div>
          </label>
          {f.credit_anterieur_calcule > 0 && Math.abs(f.credit_anterieur_calcule - n(f.credit_anterieur)) > 1 &&
            <Banner>Le crédit reporté du trimestre précédent, d'après ses déclarations, est de {mad(f.credit_anterieur_calcule)}.</Banner>}
        </section>

        <section className="card">
          <h2>Contrôle de cohérence</h2>
          <div className="muted">Les montants saisis doivent s'accorder entre eux.</div>
          <div className="kv"><span>TVA collectée</span><span className="mono">{mad(n(f.collectee_20) + n(f.collectee_10))}</span></div>
          <div className="kv"><span>− TVA déductible</span><span className="mono">{mad(n(f.deductible_charges) + n(f.deductible_immo))}</span></div>
          <div className="kv"><span>− Crédit reporté</span><span className="mono">{mad(n(f.credit_anterieur))}</span></div>
          <div className="kv total"><span>= TVA due calculée</span><span className="mono">{mad(calculee)}</span></div>
          <span className={`badge ${coherent ? 'b-green' : 'b-red'}`}>{coherent ? '✓ Cohérent avec la TVA due saisie' : `✗ Incohérent : la TVA due saisie est ${mad(declaree)}`}</span>
        </section>
      </div>
      {err && <div className="alert red">{err}</div>}
      <div className="row" style={{ justifyContent: 'flex-end' }}>
        <button className="btn" onClick={() => nav('/calcul')}>Retour au calcul</button>
        <button className="btn primary" onClick={() => save('/bilan')}>Comparer avec le recalcul</button>
      </div>
    </>
  )
}
