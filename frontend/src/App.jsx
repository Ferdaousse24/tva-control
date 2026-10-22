import { useCallback, useEffect, useState } from 'react'
import { Link, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { api } from './api'
import { QuarterCtx } from './ui.jsx'
import Import from './pages/Import.jsx'
import Verify from './pages/Verify.jsx'
import Calcul from './pages/Calcul.jsx'
import Declaration from './pages/Declaration.jsx'
import Comparer from './pages/Comparer.jsx'
import Rapport from './pages/Rapport.jsx'
import Entreprise from './pages/Entreprise.jsx'

const NAV = [
  { n: 1, short: 'Factures', label: 'Tableau de bord', to: '/', match: (p) => p === '/' || p.startsWith('/factures') },
  { n: 2, short: 'TVA', label: 'TVA du trimestre', to: '/calcul', match: (p) => p.startsWith('/calcul') },
  { n: 3, short: 'Bilan', label: 'Bilan du trimestre', to: '/bilan', match: (p) => ['/bilan', '/declaration', '/rapport'].some((s) => p.startsWith(s)) },
]

export default function App() {
  const { pathname } = useLocation()
  const navigate = useNavigate()
  const [busy, setBusy] = useState(false)
  const [quarters, setQuarters] = useState(null)
  const [error, setError] = useState('')
  const [company, setCompany] = useState(null)
  const [selected, setSelected] = useState(() => { try { return Number(localStorage.getItem('quarter')) || null } catch { return null } })

  const reload = useCallback(async () => {
    try { setQuarters(await api.quarters()); setError('') } catch (e) { setError(e.message) }
  }, [])
  const loadCompany = useCallback(async () => { try { setCompany(await api.company()) } catch { /* ignoré */ } }, [])
  useEffect(() => { reload(); loadCompany() }, [reload, loadCompany])
  const [slow, setSlow] = useState(false)
  useEffect(() => { const t = setTimeout(() => setSlow(true), 1500); return () => clearTimeout(t) }, [])
  useEffect(() => {
    if (quarters !== null || !error) return
    const t = setInterval(() => { reload(); loadCompany() }, 5000)
    return () => clearInterval(t)
  }, [quarters, error, reload, loadCompany])

  const quarter = quarters?.find((q) => q.id === selected) || quarters?.[0] || null
  const select = (id) => { setSelected(id); try { localStorage.setItem('quarter', String(id)) } catch { /* ignoré */ } }

  const loadDemo = async () => {
    setBusy(true)
    try {
      let r = await api.seed()
      if (!r.seeded) {
        const ok = window.prompt('Des données existent déjà. Pour TOUT effacer et recharger la démonstration, tapez EFFACER :')
        if (ok !== 'EFFACER') return
        r = await api.resetDemo()
      }
      const qs = await api.quarters()
      setQuarters(qs)
      const t2 = qs.find((q) => q.year === 2026 && q.q === 2)
      if (t2) select(t2.id)
      navigate('/')
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }

  if (quarters === null && (slow || error)) return <Wake error={error} onRetry={() => { reload(); loadCompany() }} />

  return (
    <QuarterCtx.Provider value={{ quarters, quarter, select, reload, loadDemo, demoBusy: busy }}>
      <div className={`app ${pathname.startsWith('/factures') ? 'notab' : ''}`}>
        {pathname === '/' && (
          <header className="topbar only-m">
            <div className="brand">{company?.raison_sociale || 'CBS TECH MAROC'}<small>Application trimestrielle · V1</small></div>
            <div className="avatar" aria-hidden="true">H</div>
          </header>
        )}
        <aside className="side">
          <div className="brand">{company?.raison_sociale || 'CBS TECH MAROC'}<small>Application trimestrielle · V1</small></div>
          <nav className="nav">
            {NAV.map((i) => (
              <Link key={i.n} to={i.to} className={i.match(pathname) ? 'on' : ''}><span className="n">{i.n}</span><span className="lbl">{i.label}</span></Link>
            ))}
          </nav>
          <div className="navgroup">
            <div className="navlabel">Paramètres</div>
            <nav className="nav">
              <Link to="/entreprise" className={pathname.startsWith('/entreprise') ? 'on' : ''}>
                <span className="n">⚙</span><span className="lbl">Fiche entreprise</span>
                {company && <span className={`chip ${company.complete ? 'ok' : 'todo'}`}>{company.complete ? '✓' : 'À faire'}</span>}
              </Link>
            </nav>
          </div>
          <button className="demolink" disabled={busy} onClick={loadDemo}>{busy ? 'Chargement…' : 'Recharger la démonstration'}</button>
          <div className="who"><b>Hamza</b><span>Casablanca · Régime trimestriel</span></div>
        </aside>
        <main className="main">
          {company && !company.complete && !pathname.startsWith('/entreprise') && (
            <div className={`alert ${pathname.startsWith('/factures') ? 'hide-m' : ''}`}>
              <div><b>Fiche entreprise incomplète.</b> Renseignez l'identité fiscale (ICE, IF, RC…) : elle apparaît dans les rapports.</div>
              <Link className="btn" to="/entreprise">Compléter la fiche</Link>
            </div>
          )}
          {error && <div className="alert red">Le serveur ne répond pas : {error}</div>}
          {pathname.startsWith('/entreprise') && <Entreprise company={company} onSaved={loadCompany} />}
          {quarters && quarters.length === 0 && !pathname.startsWith('/entreprise') && <Empty reload={reload} />}
          {quarters && quarters.length > 0 && !pathname.startsWith('/entreprise') && (
            <Routes>
              <Route path="/" element={<Import />} />
              <Route path="/factures/:id" element={<Verify />} />
              <Route path="/calcul" element={<Calcul />} />
              <Route path="/declaration" element={<Declaration />} />
              <Route path="/bilan" element={<Comparer />} />
              <Route path="/rapport" element={<Rapport />} />
            </Routes>
          )}
        </main>
        <nav className="tabbar only-m" aria-label="Navigation principale">
          {NAV.map((i) => (
            <Link key={i.n} to={i.to} className={i.match(pathname) ? 'on' : ''}><span className="n">{i.n}</span>{i.short}</Link>
          ))}
          <Link to="/entreprise" className={pathname.startsWith('/entreprise') ? 'on' : ''}>
            <span className="n"><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"><rect x="5" y="3" width="14" height="18" rx="1"/><path d="M9 8h2M13 8h2M9 12h2M13 12h2M10 21v-4h4v4"/></svg></span>Entreprise
          </Link>
        </nav>
      </div>
    </QuarterCtx.Provider>
  )
}

function Wake({ error, onRetry }) {
  return (
    <div className="wake">
      <div className="brand">CBS TECH MAROC</div>
      <div className="spinner" role="status" aria-label="Chargement" />
      <h1>Réveil du serveur…</h1>
      <p>Le site gratuit s'endort après un moment d'inactivité. Le premier chargement peut prendre jusqu'à une minute. Vos données sont conservées.</p>
      <div className="pbar"><i /></div>
      {error && <p style={{ fontSize: 12 }}>Pas encore de réponse. Nouvel essai automatique toutes les 5 secondes.</p>}
      <button className="btn" onClick={onRetry}>Réessayer</button>
    </div>
  )
}

function Empty({ reload }) {
  const [busy, setBusy] = useState(false)
  return (
    <div className="card">
      <h2>Bienvenue</h2>
      <p className="muted">Aucun trimestre pour l'instant. Chargez les données de démonstration (factures d'exemple, trimestre T2 2026) pour parcourir l'application.</p>
      <div className="row">
        <button className="btn primary" disabled={busy} onClick={async () => { setBusy(true); await api.seed(); reload() }}>Charger la démonstration</button>
        <button className="btn" disabled={busy} onClick={async () => {
          setBusy(true); const d = new Date()
          await api.createQuarter(d.getFullYear(), Math.floor(d.getMonth() / 3) + 1); reload()
        }}>Commencer avec le trimestre en cours</button>
      </div>
    </div>
  )
}
