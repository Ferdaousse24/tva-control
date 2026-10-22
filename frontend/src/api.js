async function req(path, opts = {}) {
  const res = await fetch('/api' + path, opts)
  if (!res.ok) {
    let msg = `Erreur ${res.status}`
    try { const j = await res.json(); msg = j.detail || msg } catch { /* pas de JSON */ }
    throw new Error(typeof msg === 'string' ? msg : JSON.stringify(msg))
  }
  return res.json()
}
const json = (method, body) => ({ method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body ?? {}) })

export const api = {
  quarters: () => req('/quarters'),
  createQuarter: (year, q) => req('/quarters', json('POST', { year, q })),
  invoices: (qid) => req(`/quarters/${qid}/invoices`),
  upload: (file, direction) => { const f = new FormData(); f.append('file', file); f.append('direction', direction); return req('/invoices/upload', { method: 'POST', body: f }) },
  invoice: (id) => req(`/invoices/${id}`),
  patch: (id, body) => req(`/invoices/${id}`, json('PATCH', body)),
  validate: (id, body) => req(`/invoices/${id}/validate`, json('POST', body)),
  force: (id, comment) => req(`/invoices/${id}/force`, json('POST', { comment })),
  unforce: (id) => req(`/invoices/${id}/unforce`, json('POST')),
  duplicate: (id, action, justification) => req(`/invoices/${id}/duplicate`, json('POST', { action, justification })),
  calcul: (qid) => req(`/quarters/${qid}/calcul`),
  declaration: (qid) => req(`/quarters/${qid}/declaration`),
  saveDeclaration: (qid, body) => req(`/quarters/${qid}/declaration`, json('PUT', body)),
  comparaison: (qid) => req(`/quarters/${qid}/comparaison`),
  explain: (qid, key, comment) => req(`/quarters/${qid}/ecarts/${key}/expliquer`, json('POST', { comment })),
  rapport: (qid) => req(`/quarters/${qid}/rapport`),
  company: () => req('/company'),
  saveCompany: (body) => req('/company', json('PUT', body)),
  createManual: (body) => req('/invoices/manual', json('POST', body)),
  seed: () => req('/demo/seed', json('POST')),
  resetDemo: () => req('/demo/reset', json('POST')),
}
