import { useEffect, useRef, useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import { useQuarter, fmt, fdate, StatusBadge, Modal, Banner } from '../ui.jsx'

export default function Import() {
  const { quarters, quarter, select, reload } = useQuarter()
  const nav = useNavigate()
  const [invoices, setInvoices] = useState([])
  const [showNew, setShowNew] = useState(false)
  const [errors, setErrors] = useState([])
  const [busy, setBusy] = useState('')

  const load = useCallback(async () => { if (quarter) setInvoices(await api.invoices(quarter.id)) }, [quarter])
  useEffect(() => { load() }, [load])

  async function onFiles(direction, files) {
    setErrors([]); setBusy(direction)
    const errs = []; let last = null; let n = 0
    for (const f of files) {
      try { last = await api.upload(f, direction); n++ } catch (e) { errs.push(`${f.name} : ${e.message}`) }
    }
    setBusy(''); setErrors(errs); reload()
    if (n === 1 && last && !errs.length) nav(`/factures/${last.id}`)
    else load()
  }

  const toCheck = invoices.filter((i) => i.status === 'a_verifier' || i.status === 'doublon_detecte')
  const count = (f) => invoices.filter(f).length
  const stats = [
    ['Factures importées', count((i) => !['doublon_ignore', 'remplacee'].includes(i.status))],
    ['À vérifier', toCheck.length],
    ['Non conformes', count((i) => i.non_conforme && i.direction === 'achat' && i.status !== 'doublon_ignore')],
    ['Doublons ignorés', count((i) => i.status === 'doublon_ignore')],
  ]

  return (
    <>
      <div className="head"><div><h1>Import des factures</h1><div className="sub">Étape 1 · Lire — trimestre ouvert : <b>{quarter.label}</b>, échéance {fdate(quarter.echeance)}</div></div></div>

      <section className="card">
        <h2>Trimestres</h2>
        <div className="quarters">
          {quarters.map((q) => (
            <button key={q.id} className={`qcard ${q.id === quarter.id ? 'sel' : ''}`} onClick={() => select(q.id)}>
              <b>{q.label}</b><span>{q.nb_factures} facture(s){q.nb_a_verifier ? ` · ${q.nb_a_verifier} à vérifier` : ''}</span>
            </button>
          ))}
          <button className="qcard new" onClick={() => setShowNew(true)}>+ Nouveau trimestre</button>
        </div>
      </section>

      <div className="grid2">
        {[['vente', 'Ventes', 'Factures émises à vos clients'], ['achat', 'Achats', 'Factures reçues de vos fournisseurs']].map(([dir, title, sub]) => (
          <UploadCard key={dir} title={title} sub={sub} busy={busy === dir} onFiles={(f) => onFiles(dir, f)}
            count={count((i) => i.direction === dir && !['doublon_ignore', 'remplacee'].includes(i.status))} />
        ))}
      </div>

      {errors.length > 0 && <Banner kind="red">{errors.map((e) => <div key={e}>{e}</div>)}</Banner>}

      <div className="stats">{stats.map(([l, v]) => <div className="stat" key={l}><span>{l}</span><b>{v}</b></div>)}</div>

      {toCheck.length > 0 && (
        <Banner action={<button className="btn" onClick={() => nav(`/factures/${toCheck[0].id}`)}>Vérifier maintenant</button>}>
          <b>{toCheck.length} facture(s) à vérifier.</b> Elles ne sont pas comptées dans le calcul tant qu'elles ne sont pas validées.
        </Banner>
      )}

      <section className="card">
        <h2>Historique des factures importées</h2>
        <div className="scroll">
          <table>
            <thead><tr><th>Fichier</th><th>Sens</th><th>Tiers</th><th>Date</th><th className="r">TTC (MAD)</th><th>Statut</th></tr></thead>
            <tbody>
              {invoices.map((i) => (
                <tr key={i.id} className="click" onClick={() => nav(`/factures/${i.id}`)}>
                  <td>{i.filename}</td><td>{i.direction === 'vente' ? 'Vente' : 'Achat'}</td><td>{i.party_name || '—'}</td>
                  <td>{fdate(i.date)}</td><td className="r mono">{fmt(i.total_ttc, 2)}</td><td><StatusBadge inv={i} /></td>
                </tr>
              ))}
              {invoices.length === 0 && <tr><td colSpan="6" className="muted">Aucune facture pour ce trimestre. Importez-en une ci-dessus.</td></tr>}
            </tbody>
          </table>
        </div>
      </section>

      {showNew && <NewQuarter onClose={() => setShowNew(false)} onCreated={async (q) => { await reload(); select(q.id); setShowNew(false) }} />}
    </>
  )
}

function UploadCard({ title, sub, onFiles, busy, count }) {
  const ref = useRef()
  return (
    <section className="card">
      <div className="row between"><div><h2>{title}</h2><div className="muted">{sub}</div></div><span className="badge b-gray">{count} facture(s)</span></div>
      <input ref={ref} type="file" hidden multiple accept=".pdf,.jpg,.jpeg,.png"
        onChange={(e) => { if (e.target.files.length) onFiles([...e.target.files]); e.target.value = '' }} />
      <div className="muted">PDF, photo ou scan (JPG, PNG)</div>
      <div><button className="btn primary" disabled={busy} onClick={() => ref.current.click()}>{busy ? 'Lecture en cours…' : 'Importer une facture'}</button></div>
    </section>
  )
}

function NewQuarter({ onClose, onCreated }) {
  const now = new Date()
  const [year, setYear] = useState(now.getFullYear())
  const [q, setQ] = useState(Math.floor(now.getMonth() / 3) + 1)
  const [err, setErr] = useState('')
  return (
    <Modal onClose={onClose}>
      <h2>Nouveau trimestre</h2>
      <label className="f">Année<input className="in" type="number" value={year} onChange={(e) => setYear(Number(e.target.value))} /></label>
      <label className="f">Trimestre
        <select className="in" value={q} onChange={(e) => setQ(Number(e.target.value))}>{[1, 2, 3, 4].map((n) => <option key={n} value={n}>T{n}</option>)}</select>
      </label>
      {err && <div className="err">{err}</div>}
      <div className="row" style={{ justifyContent: 'flex-end' }}>
        <button className="btn" onClick={onClose}>Annuler</button>
        <button className="btn primary" onClick={async () => { try { onCreated(await api.createQuarter(year, q)) } catch (e) { setErr(e.message) } }}>Créer</button>
      </div>
    </Modal>
  )
}
