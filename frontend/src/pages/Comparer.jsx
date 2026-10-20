import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api'
import { useQuarter, mad, Banner } from '../ui.jsx'

export default function Comparer() {
  const { quarter } = useQuarter()
  const nav = useNavigate()
  const [c, setC] = useState(null)
  const [err, setErr] = useState('')
  const [noDecl, setNoDecl] = useState(false)
  const load = () => api.comparaison(quarter.id).then((d) => { setC(d); setNoDecl(false) })
    .catch((e) => { if (/déclaration du comptable/i.test(e.message)) setNoDecl(true); else setErr(e.message) })
  useEffect(() => { setC(null); setErr(''); load() }, [quarter.id])

  if (noDecl) return (
    <>
      <div className="head"><h1>Comparer avec la déclaration déposée</h1></div>
      <Banner action={<button className="btn primary" onClick={() => nav('/declaration')}>Saisir la déclaration</button>}>La déclaration du comptable n'est pas encore saisie pour {quarter.label}.</Banner>
    </>
  )
  if (err) return <div className="alert red">{err}</div>
  if (!c) return <div className="muted">Chargement…</div>

  const sens = { inferieur: 'inférieure', superieur: 'supérieure', egal: 'égale' }[c.sens]
  const yoy = c.n_moins_1
  const maxv = yoy ? Math.max(Math.abs(yoy.valeur_precedente), Math.abs(yoy.valeur_courante), 1) : 1

  async function explain(key) {
    const comment = window.prompt('Explication de l\'écart (conservée dans le journal d\'audit) :')
    if (comment && comment.trim()) { await api.explain(quarter.id, key, comment.trim()); load() }
  }

  return (
    <>
      <div className="head">
        <div><h1>Comparer avec la déclaration déposée</h1><div className="sub">{c.label} · montants déclarés par le comptable vs recalcul de l'application</div></div>
        <button className="btn primary" onClick={() => nav('/rapport')}>Générer le rapport</button>
      </div>

      {c.a_verifier > 0 && <Banner>{c.a_verifier} facture(s) non validée(s) ne sont pas dans le recalcul : le résultat peut changer après validation.</Banner>}
      {c.nb_ecarts === 0 && c.ecart_tva_due <= 1
        ? <Banner kind="green"><b>Aucun écart.</b> La déclaration est cohérente avec le recalcul.</Banner>
        : <Banner kind="red"><span className="badge b-red">{c.nb_ecarts} écart(s)</span> Écart total de {mad(c.ecart_tva_due)} : la TVA due déclarée est <b>{sens}</b> au recalcul.</Banner>}

      <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
        <table>
          <thead><tr><th>Rubrique</th><th className="r">Déclaré (MAD)</th><th className="r">Recalculé (MAD)</th><th className="r">Écart (MAD)</th><th /></tr></thead>
          <tbody>
            {c.lignes.map((r) => (
              <tr key={r.key} className={r.has_ecart ? 'bad' : ''} style={r.key === 'tva_due' ? { fontWeight: 700 } : null}>
                <td>{r.label}</td><td className="r mono">{mad(r.declare)}</td><td className="r mono">{mad(r.recalcule)}</td>
                <td className="r"><span className={`badge ${r.has_ecart ? 'b-red' : 'b-green'}`}>{r.has_ecart ? mad(Math.abs(r.ecart)) : '0'}</span></td>
                <td>{r.explique && <span className="badge b-blue" title={r.explique}>Expliqué</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="grid2">
        <section className="card">
          <h2>Origine de l'écart</h2>
          {c.origines.length === 0 && <div className="muted">Aucun écart à expliquer.</div>}
          {c.origines.map((o) => (
            <div key={o.key} className="card" style={{ padding: 14 }}>
              <div><b>{o.label}</b> — écart {mad(Math.abs(o.ecart))}</div>
              <div className="muted">{o.message}</div>
              {o.factures.map((f) => (
                <div key={f.id}><Link to={`/factures/${f.id}`}><b>{f.filename}</b></Link> — {f.party_name || 'tiers inconnu'}{f.tva != null && ` · TVA ${mad(f.tva)}`}{f.motif && <div className="badge b-red" style={{ marginTop: 6 }}>{f.motif}</div>}</div>
              ))}
              <div className="row">
                {o.factures[0] && <Link className="btn primary" to={`/factures/${o.factures[0].id}`}>Voir la facture</Link>}
                <button className="btn" onClick={() => explain(o.key)}>Marquer comme expliqué</button>
              </div>
            </div>
          ))}
        </section>
        <section className="card bars">
          <h2>TVA due : {c.label.replace(/\d{4}/, '')} {quarter.year} vs {c.label.replace(/\d{4}/, '')} {quarter.year - 1}</h2>
          {yoy ? (
            <>
              <div className="row between"><span>{quarter.year - 1}</span><b className="mono">{mad(yoy.valeur_precedente)}</b></div>
              <div className="bar" style={{ width: `${Math.abs(yoy.valeur_precedente) / maxv * 100}%`, background: '#93c5fd' }} />
              <div className="row between"><span>{quarter.year} (recalculé)</span><b className="mono">{mad(yoy.valeur_courante)}</b></div>
              <div className="bar" style={{ width: `${Math.abs(yoy.valeur_courante) / maxv * 100}%`, background: 'var(--blue)' }} />
              {yoy.variation != null && <span className={`badge ${yoy.alerte ? 'b-red' : 'b-green'}`}>{yoy.variation >= 0 ? '+' : ''}{Math.round(yoy.variation * 100)} % — {yoy.alerte ? `au-dessus du seuil d'alerte de ${yoy.seuil * 100} %` : `sous le seuil d'alerte de ${yoy.seuil * 100} %`}</span>}
            </>
          ) : <div className="muted">Pas de déclaration de l'année précédente pour ce trimestre.</div>}
        </section>
      </div>
    </>
  )
}
