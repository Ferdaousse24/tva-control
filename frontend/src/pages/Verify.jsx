import { useEffect, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { api } from '../api'
import { useQuarter, fmt, fdate, Banner, StatusBadge } from '../ui.jsx'

const RATES = [20, 10, 0, 14, 7]
const num = (v) => (v === '' || v == null ? 0 : Number(String(v).replace(',', '.')) || 0)
const r2 = (x) => Math.round(x * 100) / 100

const MODES = [['', '—'], ['virement', 'Virement'], ['cheque', 'Chèque'], ['effet', 'Effet'], ['especes', 'Espèces'], ['carte', 'Carte']]
const today = () => new Date().toISOString().slice(0, 10)

export default function Verify() {
  const { id } = useParams()
  const isNew = id === 'nouvelle'
  const [params] = useSearchParams()
  const nav = useNavigate()
  const { reload, select } = useQuarter()
  const [inv, setInv] = useState(null)
  const [f, setF] = useState(null)
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)

  const load = async () => {
    const d = isNew
      ? { direction: params.get('sens') === 'achat' ? 'achat' : 'vente', filename: 'Saisie manuelle', status: 'nouvelle', manual: true, has_file: false,
          issues: [], confidence: {}, lines: [], payments: [], number: '', date: '', party_name: '', party_ice: '', categorie: 'charge',
          total_ttc: 0, non_conforme: false, forced: false }
      : await api.invoice(id)
    setInv(d)
    setF({
      direction: d.direction, number: d.number, date: d.date || '', party_name: d.party_name, party_ice: d.party_ice, categorie: d.categorie,
      lines: (d.lines.length ? d.lines : [{ rate: 20, base_ht: 0, tva: 0 }]).map((l) => ({ rate: l.rate, base_ht: l.base_ht, tva: l.tva })),
      total_ttc: d.total_ttc, payments: (d.payments || []).map((p) => ({ date: p.date, amount: p.amount, mode: p.mode || '' })),
    })
  }
  useEffect(() => { load().catch((e) => setErr(e.message)) }, [id])
  if (err && !inv) return <div className="alert red">{err}</div>
  if (!inv || !f) return <div className="muted">Chargement…</div>

  const set = (k, v) => setF((s) => ({ ...s, [k]: v }))
  const setLine = (i, k, v) => setF((s) => {
    const lines = s.lines.map((l, j) => (j === i ? { ...l, [k]: v } : l))
    if (k === 'rate' || k === 'base_ht') lines[i].tva = r2(num(lines[i].base_ht) * num(lines[i].rate) / 100)   // TVA recalculée, modifiable ensuite
    return { ...s, lines }
  })
  const ht = r2(f.lines.reduce((a, l) => a + num(l.base_ht), 0))
  const tv = r2(f.lines.reduce((a, l) => a + num(l.tva), 0))
  const mismatch = Math.abs(ht + tv - num(f.total_ttc)) > 1

  const paidTotal = r2(f.payments.reduce((a, p) => a + num(p.amount), 0))
  const remaining = r2(num(f.total_ttc) - paidTotal)
  const setPay = (i, k, v) => set('payments', f.payments.map((p, j) => (j === i ? { ...p, [k]: v } : p)))
  const addPay = () => set('payments', [...f.payments, { date: f.payments.length ? '' : (f.date || today()), amount: remaining > 0 ? remaining : '', mode: f.payments.at(-1)?.mode || '' }])
  const payload = () => {
    for (const p of f.payments) if ((num(p.amount) > 0) !== Boolean(p.date)) throw new Error('Chaque paiement doit avoir une date et un montant.')
    const { direction, ...rest } = f
    return {
      ...(isNew ? { direction } : {}), ...rest, date: f.date || null, total_ttc: num(f.total_ttc),
      total_ht: ht, total_tva: tv, lines: f.lines.map((l) => ({ rate: num(l.rate), base_ht: num(l.base_ht), tva: num(l.tva) })),
      payments: f.payments.filter((p) => p.date && num(p.amount) > 0).map((p) => ({ date: p.date, amount: num(p.amount), mode: p.mode })),
    }
  }
  const run = async (fn, after) => { setBusy(true); setErr(''); try { await fn(); await reload(); after() } catch (e) { setErr(e.message) } finally { setBusy(false) } }
  const createManual = (validate) => run(async () => {
    const created = await api.createManual({ ...payload(), validate })
    await reload()
    select(created.quarter_id)
    nav(validate && created.status === 'validee' ? '/' : `/factures/${created.id}`)
  }, () => {})

  const issueOf = (field) => inv.issues.find((i) => i.field === field)
  const cls = (field) => { const i = issueOf(field); return i ? (i.level === 'error' ? 'red' : 'amber') : '' }
  const isDup = inv.status === 'doublon_detecte'
  const achat = f.direction === 'achat'

  return (
    <>
      <div className="head">
        <div>
          <h1>{isNew ? 'Saisir une facture' : isDup ? 'Doublon détecté' : inv.non_conforme && achat ? 'Vérifier une facture non conforme' : 'Vérifier une facture'}</h1>
          <div className="sub">{isNew ? 'Saisie manuelle' : inv.filename} · {achat ? 'Achat' : 'Vente'}{!isNew && <> · {inv.manual ? 'saisie manuelle' : `lecture : ${inv.extraction_source === 'ocr' ? 'photo / scan (OCR)' : 'PDF texte'}`} <StatusBadge inv={inv} /></>}</div>
        </div>
      </div>

      {inv.non_conforme && achat && !isDup && (
        <Banner kind="red">
          <b>Facture non conforme :</b> {inv.issues.filter((i) => i.level === 'error').map((i) => i.message).join(' · ')}.
          {' '}{inv.forced ? 'Inclusion forcée dans le calcul.' : 'Sa TVA est exclue du calcul.'}
        </Banner>
      )}

      {isDup && <DuplicatePanel inv={inv} busy={busy} err={err}
        onResolve={(action, just) => run(() => api.duplicate(inv.id, action, just), () => (action === 'ignorer' ? nav('/') : load()))}
        onCancel={() => nav('/')} />}

      <div className="split">
        <div className="card">
          <h2>Fichier source</h2>
          {inv.has_file === false ? (
            <div className="muted">Facture saisie à la main : aucun fichier source. Pensez à conserver la pièce originale (obligation d'archivage).</div>
          ) : (
            <>
              <div className="preview">
                {inv.is_pdf ? <iframe title="Facture" src={inv.file_url} /> : <img alt={inv.filename} src={inv.file_url} />}
              </div>
              <a className="muted" href={inv.file_url} target="_blank" rel="noreferrer">Ouvrir le fichier dans un nouvel onglet</a>
            </>
          )}
        </div>

        <div className="card">
          <h2>{isNew ? 'Champs à saisir' : 'Champs lus — modifiables'}</h2>
          {isNew && (
            <Field inv={inv} label="Sens">
              <select className="in" value={f.direction} onChange={(e) => set('direction', e.target.value)}>
                <option value="vente">Vente (facture émise à un client)</option><option value="achat">Achat (facture reçue d'un fournisseur)</option>
              </select>
            </Field>
          )}
          <div className="grid2">
            <Field inv={inv} label="N° de facture" field="number"><input className={`in ${cls('number')}`} value={f.number} onChange={(e) => set('number', e.target.value)} /></Field>
            <Field inv={inv} label="Date" field="date"><input className={`in ${cls('date')}`} type="date" value={f.date} onChange={(e) => set('date', e.target.value)} /></Field>
            <Field inv={inv} label={achat ? 'Fournisseur' : 'Client'} field="party_name"><input className={`in ${cls('party_name')}`} value={f.party_name} onChange={(e) => set('party_name', e.target.value)} /></Field>
            <Field inv={inv} label="ICE (15 chiffres)" field="party_ice"><input className={`in ${cls('party_ice')}`} inputMode="numeric" value={f.party_ice} onChange={(e) => set('party_ice', e.target.value.replace(/\D/g, ''))} placeholder="Non renseigné" /></Field>
          </div>
          {achat && (
            <Field inv={inv} label="Catégorie fiscale">
              <select className="in" value={f.categorie} onChange={(e) => set('categorie', e.target.value)}>
                <option value="charge">Charge (frais généraux)</option><option value="immobilisation">Immobilisation</option><option value="non_deductible">Non déductible</option>
              </select>
            </Field>
          )}

          <div className="muted" style={{ fontWeight: 600, marginTop: 4 }}>Montants par taux de TVA {issueOf('lines') && <span className="hint amber">· {issueOf('lines').message}</span>}</div>
          <table>
            <thead><tr><th>Taux</th><th className="r">Base HT</th><th className="r">TVA</th><th /></tr></thead>
            <tbody>
              {f.lines.map((l, i) => (
                <tr key={i}>
                  <td style={{ width: 90 }}><select className="in" value={l.rate} onChange={(e) => setLine(i, 'rate', Number(e.target.value))}>{RATES.map((r) => <option key={r} value={r}>{r} %</option>)}</select></td>
                  <td><input className={`in r ${cls('total_ht')}`} value={l.base_ht} onChange={(e) => setLine(i, 'base_ht', e.target.value)} /></td>
                  <td><input className={`in r ${cls('total_tva')}`} value={l.tva} onChange={(e) => setLine(i, 'tva', e.target.value)} /></td>
                  <td style={{ width: 36 }}>{f.lines.length > 1 && <button className="btn" title="Supprimer la ligne" onClick={() => set('lines', f.lines.filter((_, j) => j !== i))}>×</button>}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div><button className="btn" onClick={() => set('lines', [...f.lines, { rate: 20, base_ht: 0, tva: 0 }])}>+ Ajouter un taux</button></div>

          <div className="kv"><span>Total HT</span><b className="mono">{fmt(ht, 2)} MAD</b></div>
          <div className="kv"><span>Total TVA</span><b className="mono">{fmt(tv, 2)} MAD</b></div>
          <Field inv={inv} label="Total TTC (lu sur la facture)" field="total_ht">
            <input className={`in ${mismatch ? 'amber' : ''}`} value={f.total_ttc} onChange={(e) => set('total_ttc', e.target.value)} />
          </Field>
          {mismatch && <span className="hint amber">HT + TVA = {fmt(ht + tv, 2)} MAD, différent du TTC saisi.</span>}

          <div className="muted" style={{ fontWeight: 600, marginTop: 4 }}>Paiements (la TVA est rattachée à chaque paiement, dans le trimestre où il a lieu)</div>
          {f.payments.length > 0 && (
            <table>
              <thead><tr><th>Date</th><th className="r">Montant TTC</th><th>Mode</th><th /></tr></thead>
              <tbody>
                {f.payments.map((p, i) => (
                  <tr key={i}>
                    <td><input className="in" type="date" value={p.date} onChange={(e) => setPay(i, 'date', e.target.value)} /></td>
                    <td><input className="in r" inputMode="decimal" value={p.amount} onChange={(e) => setPay(i, 'amount', e.target.value)} /></td>
                    <td><select className="in" value={p.mode} onChange={(e) => setPay(i, 'mode', e.target.value)}>{MODES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></td>
                    <td style={{ width: 36 }}><button className="btn" title="Supprimer ce paiement" onClick={() => set('payments', f.payments.filter((_, j) => j !== i))}>×</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <div><button className="btn" onClick={addPay}>+ Ajouter un paiement</button></div>
          <div className="kv"><span>Total payé</span><b className="mono">{fmt(paidTotal, 2)} MAD</b></div>
          <div className="kv"><span>Reste à payer</span><b className="mono">{fmt(Math.max(remaining, 0), 2)} MAD</b></div>
          {remaining < -1 && <span className="hint amber">Les paiements dépassent le TTC de {fmt(-remaining, 2)} MAD : l'excédent n'est pas compté dans la TVA.</span>}
          {f.payments.length === 0 && <span className="hint amber">Sans paiement, cette facture ne sera comptée dans aucun trimestre.</span>}
          {f.payments.some((p) => p.mode === 'especes') && achat && <span className="hint muted">Paiements en espèces : plafonds de 5 000 MAD par jour et 50 000 MAD par mois et par fournisseur.</span>}
        </div>
      </div>

      {inv.non_conforme && achat && !isDup && <ForcePanel inv={inv} busy={busy} run={run} reload={load} />}
      {err && <div className="alert red">{err}</div>}

      {isNew && (
        <div className="row" style={{ justifyContent: 'flex-end' }}>
          <button className="btn" onClick={() => nav('/')}>Annuler</button>
          <button className="btn" disabled={busy} onClick={() => createManual(false)}>Enregistrer (à vérifier)</button>
          <button className="btn primary" disabled={busy} onClick={() => createManual(true)}>Enregistrer et valider</button>
        </div>
      )}
      {!isDup && !isNew && (
        <div className="row" style={{ justifyContent: 'flex-end' }}>
          <button className="btn" onClick={() => nav('/')}>Annuler</button>
          <button className="btn" disabled={busy} onClick={() => run(() => api.patch(inv.id, payload()), () => load())}>Enregistrer</button>
          <button className="btn primary" disabled={busy} onClick={() => run(() => api.validate(inv.id, payload()), () => nav('/'))}>Confirmer et valider</button>
        </div>
      )}
    </>
  )
}

function Field({ inv, label, field, children }) {
  const i = field ? inv.issues.find((x) => x.field === field) : null
  const c = field ? inv.confidence?.[field] : null
  let hint = null
  if (i) hint = <span className={`hint ${i.level === 'error' ? 'red' : 'amber'}`}>{i.message}</span>
  else if (c != null && c < 0.99) hint = <span className="hint muted">Confiance {Math.round(c * 100)} %</span>
  return <label className="f"><span className="lbl">{label}{hint}</span>{children}</label>
}

function ForcePanel({ inv, busy, run, reload }) {
  const [c, setC] = useState('')
  if (inv.forced) {
    return (
      <div className="card"><h2>Inclusion forcée</h2><div className="muted">Commentaire : {inv.forced_comment}</div>
        <div><button className="btn" disabled={busy} onClick={() => run(() => api.unforce(inv.id), reload)}>Retirer l'inclusion forcée</button></div></div>
    )
  }
  return (
    <div className="card">
      <h2>Inclure malgré tout ?</h2>
      <div className="muted">Une facture non conforme n'ouvre pas droit à déduction en cas de contrôle. Vous pouvez forcer son inclusion avec un commentaire (conservé dans le journal d'audit).</div>
      <textarea className="in" rows="2" placeholder="Ex. attestation reçue du fournisseur" value={c} onChange={(e) => setC(e.target.value)} />
      <div><button className="btn" disabled={busy || c.trim().length < 5} onClick={() => run(() => api.force(inv.id, c), reload)}>Forcer l'inclusion</button></div>
    </div>
  )
}

function DuplicatePanel({ inv, onResolve, onCancel, busy }) {
  const [choice, setChoice] = useState('ignorer')
  const [just, setJust] = useState('')
  const o = inv.dup_original
  const same = (a, b) => (a && b && String(a) === String(b) ? '✓ identique' : '≠ différent')
  const rows = [
    ['Tiers', inv.party_name, o?.party_name], ['N° de facture', inv.number, o?.number], ['Date', fdate(inv.date), fdate(o?.date)],
    ['Montant TTC', fmt(inv.total_ttc, 2), fmt(o?.total_ttc, 2)], ['Empreinte du fichier', inv.dup_sha_identique ? 'identique' : 'différente', 'identique'],
  ]
  const labels = { ignorer: 'Confirmer : ignorer le doublon', remplacer: 'Confirmer : remplacer l\'original', conserver: 'Confirmer : conserver les deux' }
  return (
    <div className="card">
      <h2>Cette facture ressemble à une facture déjà importée ({inv.dup_kind === 'certain' ? 'doublon certain' : 'doublon probable'})</h2>
      <table>
        <thead><tr><th>Critère</th><th>Cette facture</th><th>Facture existante</th><th>Résultat</th></tr></thead>
        <tbody>{rows.map(([k, a, b]) => <tr key={k}><td>{k}</td><td>{a ?? '—'}</td><td>{b ?? '—'}</td><td>{k === 'Empreinte du fichier' ? (inv.dup_sha_identique ? '✓ identique' : '≠ différente') : same(a, b)}</td></tr>)}</tbody>
      </table>
      {[['ignorer', 'Ignorer le doublon', 'La facture importée est écartée du calcul (par défaut).'],
        ['remplacer', 'Remplacer l\'original', 'L\'ancienne facture est archivée, la nouvelle est à vérifier.'],
        ['conserver', 'Conserver les deux', 'Justification obligatoire (journalisée).']].map(([v, t, d]) => (
        <label key={v} className="row" style={{ alignItems: 'flex-start' }}>
          <input type="radio" name="dup" checked={choice === v} onChange={() => setChoice(v)} /><span><b>{t}</b><br /><span className="muted">{d}</span></span>
        </label>
      ))}
      {choice === 'conserver' && <textarea className="in" rows="2" placeholder="Justification (obligatoire)" value={just} onChange={(e) => setJust(e.target.value)} />}
      <div className="muted">Le choix et la justification sont enregistrés dans le journal d'audit.</div>
      <div className="row" style={{ justifyContent: 'flex-end' }}>
        <button className="btn" onClick={onCancel}>Annuler</button>
        <button className="btn primary" disabled={busy || (choice === 'conserver' && just.trim().length < 5)} onClick={() => onResolve(choice, just)}>{labels[choice]}</button>
      </div>
    </div>
  )
}
