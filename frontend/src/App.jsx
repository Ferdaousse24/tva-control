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
  { n: 1, label: 'Tableau de board', to: '/', match: (p) => p === '/' || p.startsWith('/factures') },
  { n: 2, label: 'TVA du trimestre', to: '/calcul', match: (p) => p.startsWith('/calcul') },
  { n: 3, label: 'Bilan du trimestre', to: '/bilan', match: (p) => ['/bilan', '/declaration', '/rapport'].some((s) => p.startsWith(s)) },
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

  return (
    <QuarterCtx.Provider value={{ quarters, quarter, select, reload }}>
      <div className="app">
        <aside className="side">
          <div className="brand">{company?.raison_sociale || 'CBS TECH MAROC'}<small>Application trimestrielle · V1</small></div>
          <nav className="nav">
            {NAV.map((i) => (
              <Link key={i.n} to={i.to} className={i.match(pathname) ? 'on' : ''}><span className="n">{i.n}</span>{i.label}</Link>
            ))}
          </nav>
          <Link to="/entreprise" className={`sidelink ${pathname.startsWith('/entreprise') ? 'on' : ''}`}>Fiche entreprise{company && !company.complete ? ' ⚠' : ''}</Link>
          <button className="btn demo" disabled={busy} onClick={loadDemo}>{busy ? 'Chargement…' : 'Charger la démonstration'}</button>
          <div className="who"><b>Hamza</b><span>Casablanca · Régime trimestriel</span></div>
        </aside>
        <main className="main">
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
      </div>
    </QuarterCtx.Provider>
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
