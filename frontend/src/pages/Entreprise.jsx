import { useEffect, useState } from 'react'
import { api } from '../api'
import { Banner, BackBtn } from '../ui.jsx'

const FIELDS = [
  ['raison_sociale', 'Raison sociale', 'Obligatoire'],
  ['forme_juridique', 'Forme juridique', 'Ex. SARL, SARL AU, SA'],
  ['adresse', 'Adresse du siège', ''],
  ['ice', 'ICE', '15 chiffres, obligatoire'],
  ['if_fiscal', 'Identifiant fiscal (IF)', 'Chiffres uniquement'],
  ['rc', 'Registre de commerce (RC)', 'Numéro'],
  ['tribunal', 'Tribunal du RC', 'Ville'],
  ['taxe_pro', 'N° de taxe professionnelle', ''],
  ['cnss', 'N° CNSS', ''],
]

export default function Entreprise({ company, onSaved }) {
  const [f, setF] = useState(null)
  const [err, setErr] = useState('')
  const [ok, setOk] = useState(false)
  const [busy, setBusy] = useState(false)

  useEffect(() => { if (company) setF({ ...company }) }, [company])
  if (!f) return <div className="muted">Chargement…</div>

  const set = (k, v) => { setOk(false); setF((s) => ({ ...s, [k]: v })) }
  const save = async () => {
    setBusy(true); setErr(''); setOk(false)
    try { await api.saveCompany(f); await onSaved(); setOk(true) } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }
  const missing = FIELDS.filter(([k]) => !String(f[k] || '').trim()).map(([, l]) => l)

  return (
    <>
      <div className="head hasback"><BackBtn to="/" /><div><h1>Fiche entreprise</h1><div className="sub">Identité fiscale utilisée dans les rapports et les contrôles. Elle ne peut pas être supprimée.</div></div></div>
      {!company.configured && <Banner>La fiche n'a pas encore été enregistrée : les valeurs affichées sont des valeurs par défaut.</Banner>}
      <section className="card">
        <div className="grid2">
          {FIELDS.map(([k, label, hint]) => (
            <label className="f" key={k}>
              <span className="lbl">{label}{hint && <span className="hint muted"> · {hint}</span>}</span>
              <input className="in" value={f[k] || ''} inputMode={['ice', 'if_fiscal'].includes(k) ? 'numeric' : undefined}
                onChange={(e) => set(k, ['ice', 'if_fiscal'].includes(k) ? e.target.value.replace(/\D/g, '') : e.target.value)} />
            </label>
          ))}
        </div>
        {missing.length > 0 && <span className="hint amber">Fiche incomplète : {missing.join(', ')}.</span>}
        {err && <div className="alert red">{err}</div>}
        {ok && <div className="alert green">Fiche enregistrée.</div>}
      </section>
      <div className="row actionbar" style={{ justifyContent: 'flex-end' }}>
        <button className="btn primary" disabled={busy} onClick={save}>Enregistrer</button>
      </div>
    </>
  )
}
