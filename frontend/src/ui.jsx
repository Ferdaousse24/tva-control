import { createContext, useContext } from 'react'

export const QuarterCtx = createContext(null)
export const useQuarter = () => useContext(QuarterCtx)

export const fmt = (n, dec = 0) =>
  (n ?? 0).toLocaleString('fr-FR', { minimumFractionDigits: dec, maximumFractionDigits: dec }).replace(/[  ]/g, ' ')
export const mad = (n, dec = 0) => `${fmt(n, dec)} MAD`
export const fdate = (s) => (s ? s.split('-').reverse().join('/') : '—')

const STATUS = {
  validee: ['Validée', 'b-green'], a_verifier: ['À vérifier', 'b-amber'], non_conforme: ['Non conforme', 'b-red'],
  doublon_detecte: ['Doublon détecté', 'b-red'], doublon_ignore: ['Doublon ignoré', 'b-gray'], remplacee: ['Remplacée', 'b-gray'],
}
export function StatusBadge({ inv }) {
  const key = inv.non_conforme && inv.status !== 'doublon_ignore' && inv.status !== 'remplacee' ? 'non_conforme' : inv.status
  const [label, cls] = STATUS[key] || [key, 'b-gray']
  return <span className={`badge ${cls}`}>{inv.forced ? 'Inclusion forcée' : label}</span>
}

export function Modal({ children, onClose }) {
  return (
    <div className="overlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>{children}</div>
    </div>
  )
}

export function Banner({ kind = 'amber', children, action }) {
  return <div className={`alert ${kind === 'amber' ? '' : kind}`}><div>{children}</div>{action}</div>
}
