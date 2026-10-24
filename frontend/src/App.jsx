import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Background,
  Controls,
  ReactFlow,
  ReactFlowProvider,
  useEdgesState,
  useNodesState,
  useReactFlow,
} from '@xyflow/react'
import {
  AlertCircle,
  ArrowDownRight,
  ArrowRight,
  BadgeCheck,
  CarFront,
  Check,
  ChevronDown,
  CircleDot,
  Clock3,
  Expand,
  FileSearch,
  FileText,
  LockKeyhole,
  Play,
  RotateCcw,
  Shield,
  Users,
  X,
} from 'lucide-react'
import { ClaimNode, NODE_META, STATUS_LABEL, initialEdges, initialNodes, nodeStatus } from './flow.jsx'

const nodeTypes = { claim: ClaimNode }

const FALLBACK_CASES = [
  { id: 'AUTO-101', vehicle: 'Honda Civic 2020', incident_type: 'Front collision' },
  { id: 'AUTO-202', vehicle: 'Toyota Corolla 2019', incident_type: 'Minor side collision' },
  { id: 'AUTO-303', vehicle: 'Hyundai HB20 2021', incident_type: 'Rear collision' },
]

const MONEY_KEYS = ['repair_estimate_brl', 'reference_value_brl', 'insured_value_brl', 'supplemental_estimate_brl', 'estimated_price']

const FIELD_LABELS = {
  claim_id: 'Claim',
  policy_id: 'Policy',
  incident_date: 'Incident date',
  plate: 'Plate',
  vehicle: 'Vehicle',
  incident_type: 'Incident type',
  repair_estimate: 'Repair estimate',
  description: 'Description',
  repair_estimate_brl: 'Repair estimate',
  reference_value_brl: 'Reference value',
  insured_value_brl: 'Insured value',
  supplemental_estimate_brl: 'Supplemental estimate',
  total_loss_threshold: 'Total-loss threshold',
  active: 'Policy active',
  collision_covered: 'Collision covered',
  requires_supplemental: 'Needs supplemental',
  inspection_complete: 'Inspection complete',
  evidence_id: 'Evidence',
  damage_type: 'Damage type',
  size: 'Size',
  source: 'Source',
  notes: 'Notes',
  estimated_price: 'Estimated price',
  image_urls: 'Image URL',
  warning: 'Warning',
  basis: 'Basis',
  coverage_status: 'Coverage',
  next_agent: 'Next agent',
  iteration: 'Iteration',
  prior_claims: 'Prior claims',
  question: 'Question',
  answer: 'Answer',
  reason_summary: 'Reason',
  history_notes: 'History notes',
}

const ADJUSTER_CHOICES = [
  { id: 'total_loss', label: 'Review as total loss', detail: 'Treat the file as a total loss. The calculated ratio stays as it is.' },
  { id: 'repair', label: 'Review as repair', detail: 'Treat the file as a repair. The calculated ratio stays as it is.' },
  { id: 'more_evidence', label: 'Request more evidence', detail: 'The file still needs a fact before a judgment.' },
  { id: 'disagree', label: 'Disagree with the threshold reading', detail: 'The calculated ratio should not decide this file.' },
]

const AGENT_LABELS = {
  coverage: 'Coverage',
  damage: 'Damage',
  adjuster: 'Adjuster consult',
  FINISH: 'FINISH',
  finalizer: 'Investigation memo',
}

async function api(path, options) {
  const response = await fetch(`/api${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  const text = await response.text()
  const body = text ? JSON.parse(text) : null
  if (!response.ok) {
    const detail = body?.detail
    const message = typeof detail === 'string' ? detail : `Request failed (${response.status})`
    const error = new Error(message)
    error.status = response.status
    throw error
  }
  return body
}

function brl(value) {
  const number = Number(value)
  return Number.isFinite(number)
    ? number.toLocaleString('en-US', { style: 'currency', currency: 'BRL', maximumFractionDigits: 0 })
    : '—'
}

function humanize(key) {
  return FIELD_LABELS[key] || key.replaceAll('_', ' ').replace(/\./g, ' / ')
}

function formatValue(key, value) {
  if (MONEY_KEYS.includes(key)) return brl(value)
  if (typeof value === 'boolean') return value ? 'Yes' : 'No'
  if (value === null || value === undefined || value === '') return '—'
  if (typeof value === 'number' && (key.includes('ratio') || key.includes('threshold'))) {
    return `${(value * 100).toLocaleString('en-US', { maximumFractionDigits: 2 })}%`
  }
  return String(value)
}

function flattenObject(value, prefix = '') {
  if (value == null) return []
  return Object.entries(value).flatMap(([key, child]) => {
    const full = prefix ? `${prefix}.${key}` : key
    if (Array.isArray(child)) {
      if (!child.length) return [[full, 'None']]
      return child.map((item, index) => {
        const label = `${full} · ${index + 1}`
        if (item && typeof item === 'object') {
          const summary = [item.id, item.status, item.damage].filter(Boolean).join(' · ')
          return [label, summary || JSON.stringify(item)]
        }
        return [label, item]
      })
    }
    if (child && typeof child === 'object') return flattenObject(child, full)
    return [[full, child]]
  })
}

function percent(value) {
  const number = Number(value)
  return Number.isFinite(number) ? `${(number * 100).toLocaleString('en-US', { maximumFractionDigits: 2 })}%` : '—'
}

function withoutToolCalls(data) {
  if (!data || typeof data !== 'object' || Array.isArray(data)) return data
  const { tool_calls: _omitted, ...rest } = data
  return rest
}

function ToolValue({ name, value }) {
  const key = String(name).split('.').pop()
  if (typeof value === 'string' && /^https?:\/\//.test(value)) {
    return <a href={value} target="_blank" rel="noreferrer">{value}</a>
  }
  if (value && typeof value === 'object') return JSON.stringify(value)
  return formatValue(key, value)
}

function ToolTrace({ calls }) {
  if (!calls?.length) return null
  return (
    <div className="tool-trace">
      <span className="micro-label">TOOLS</span>
      {calls.map((call, index) => (
        <div className="tool-call" key={`${call.name}-${index}`}>
          <strong>{call.name}</strong>
          {flattenObject(call.arguments).map(([key, value]) => (
            <div className="tool-row" key={`arg-${key}`}>
              <span>{humanize(key)}</span>
              <strong><ToolValue name={key} value={value} /></strong>
            </div>
          ))}
          {flattenObject(call.result).map(([key, value]) => (
            <div className="tool-row" key={`result-${key}`}>
              <span>{humanize(key)}</span>
              <strong><ToolValue name={key} value={value} /></strong>
            </div>
          ))}
        </div>
      ))}
    </div>
  )
}

function PromptBlock({ text }) {
  const [open, setOpen] = useState(false)
  if (!text) return null
  const long = text.length > 280
  const shown = open || !long ? text : `${text.slice(0, 280)}…`
  return (
    <div className="prompt-block">
      <span className="micro-label">SYSTEM INSTRUCTION</span>
      <pre>{shown}</pre>
      {long && (
        <button className="prompt-toggle" type="button" onClick={() => setOpen((value) => !value)}>
          {open ? 'Show less' : 'Show full instruction'}
        </button>
      )}
    </div>
  )
}

function recommendationLabel(value) {
  return {
    TOTAL_LOSS_REVIEW: 'Review as total loss',
    REPAIR_REVIEW: 'Review as repair',
    REQUEST_MORE_EVIDENCE: 'Request more evidence',
    HUMAN_REVIEW: 'Human review',
  }[value] || 'Recommendation in review'
}

function DocumentPreview({ imageUrl, compact = false }) {
  const [failed, setFailed] = useState(false)
  const [open, setOpen] = useState(false)

  useEffect(() => {
    if (!open) return undefined
    const onKey = (event) => {
      if (event.key === 'Escape') setOpen(false)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open])

  return (
    <>
      <figure className={`document-preview ${compact ? 'document-compact' : ''}`}>
        <div className="document-frame">
          {failed ? (
            <div className="image-fallback">
              <FileText size={22} />
              <span>Annotated page is unavailable</span>
            </div>
          ) : (
            <button type="button" className="document-open" onClick={() => setOpen(true)}>
              <img src={imageUrl} alt="Claim form with OCR annotations" onError={() => setFailed(true)} />
              <span className="zoom-hint"><Expand size={14} /> Click to enlarge</span>
            </button>
          )}
        </div>
        <figcaption>
          <span><FileText size={11} /> CLAIM FORM · PAGE 01</span>
          <span className="mono">ANNOTATED EVIDENCE</span>
        </figcaption>
      </figure>
      {open && (
        <div className="lightbox" role="dialog" aria-modal="true" aria-label="Annotated claim form" onClick={() => setOpen(false)}>
          <button type="button" className="lightbox-close" onClick={() => setOpen(false)}><X size={16} /> Close</button>
          <img src={imageUrl} alt="Claim form with OCR annotations, enlarged" onClick={(event) => event.stopPropagation()} />
        </div>
      )}
    </>
  )
}

function FieldTable({ fields, flagged = [] }) {
  const rows = Object.entries(fields || {})
  if (!rows.length) return <div className="honest-empty">No fields on this step yet.</div>
  return (
    <div className="field-table">
      <div className="field-table-head"><span>FIELD / EXTRACTED VALUE</span><span>CONFIDENCE</span></div>
      {rows.map(([name, field]) => {
        const confidence = Number(field?.confidence)
        const low = Number.isFinite(confidence) && confidence < 86
        return (
          <div className={`field-row ${flagged.includes(name) ? 'field-flagged' : ''}`} key={name}>
            <div>
              <span className="field-key">{humanize(name)} {flagged.includes(name) && <span className="review-tag">REVIEW</span>}</span>
              <strong className="field-value">{field?.value || '—'}</strong>
            </div>
            <div className="confidence-cell">
              {Number.isFinite(confidence) ? (
                <>
                  <span className={`mono ${low ? 'low-number' : ''}`}>{confidence.toFixed(0)}%</span>
                  <div className="confidence-track"><i style={{ width: `${Math.min(confidence, 100)}%` }} /></div>
                </>
              ) : <span>—</span>}
            </div>
          </div>
        )
      })}
    </div>
  )
}

function ObjectPanel({ title, data }) {
  const rows = flattenObject(data)
  if (!rows.length) {
    return <div className="honest-empty"><FileText size={15} /><span>This step has no results yet.</span></div>
  }
  return (
    <div className="object-panel">
      <div className="micro-label object-title">{title}</div>
      <div className="object-list">
        {rows.map(([key, value]) => (
          <div className="object-row" key={key}>
            <span>{humanize(key.split('.').pop())}</span>
            <strong className={MONEY_KEYS.includes(key.split('.').pop()) ? 'mono' : ''}>{formatValue(key.split('.').pop(), value)}</strong>
          </div>
        ))}
      </div>
    </div>
  )
}

function FinalReport({ report, consult }) {
  if (!report) {
    return <div className="honest-empty"><BadgeCheck size={15} /><span>The investigation memo appears when the flow reaches the end.</span></div>
  }
  const ratio = Number(report.loss_ratio ?? 0)
  return (
    <div className="final-report">
      <div className="report-overline">
        <span className="micro-label">SYSTEM RECOMMENDATION</span>
        <span className="report-seal"><BadgeCheck size={13} /> INVESTIGATION MEMO</span>
      </div>
      <h4 className="recommendation-label">{recommendationLabel(report.recommendation)}</h4>
      <div className="recommendation-code mono">{report.recommendation}</div>
      <div className="ratio-block">
        <div className="ratio-head">
          <span>REPAIR / REFERENCE</span>
          <strong className="mono">{Number.isFinite(ratio) ? `${(ratio * 100).toLocaleString('en-US', { maximumFractionDigits: 2 })}%` : '—'}</strong>
        </div>
        <div className="ratio-track"><span style={{ width: `${Math.min(Math.max(ratio * 100, 0), 100)}%` }} /></div>
        <div className="ratio-scale">
          <span>0%</span>
          <span>repair <b className="mono">{brl(report.repair_estimate_brl)}</b></span>
          <span>reference <b className="mono">{brl(report.reference_value_brl)}</b></span>
        </div>
      </div>
      <div className="report-facts">
        <div><span>COVERAGE</span><strong>{report.coverage_status ?? '—'}</strong></div>
        <div><span>CLAIM ID</span><strong className="mono">{report.claim_id ?? '—'}</strong></div>
      </div>
      {report.justification && (
        <div className="report-justification"><span className="micro-label">REASONING</span><p>{report.justification}</p></div>
      )}
      {Array.isArray(report.evidence_ids) && (
        <div className="report-list">
          <span className="micro-label">EVIDENCE</span>
          {report.evidence_ids.map((item) => <span className="evidence-chip mono" key={item}>{item}</span>)}
        </div>
      )}
      {Array.isArray(report.unresolved_issues) && report.unresolved_issues.length > 0 && (
        <div className="unresolved">
          <span className="micro-label">OPEN POINTS</span>
          {report.unresolved_issues.map((item) => <p key={item}>{item}</p>)}
        </div>
      )}
      {consult?.answer && (
        <div className="consult-note">
          <span className="micro-label">ADJUSTER CONSULT</span>
          {consult.question && <p>{consult.question}</p>}
          <p><strong>{consult.answer}</strong></p>
        </div>
      )}
      <div className="human-required">
        <Users size={14} />
        <span>A person still has to decide. This memo does not authorize payment.</span>
      </div>
    </div>
  )
}

function TracePanel({ trace }) {
  return (
    <section className="trace-panel">
      <div className="trace-heading">
        <div>
          <div className="panel-kicker">CHRONOLOGICAL LOG</div>
          <h3>Trace</h3>
        </div>
        <span className="trace-total mono">{String(trace.length).padStart(2, '0')} ENTRIES</span>
      </div>
      {trace.length ? (
        <ol className="trace-list">
          {trace.map((line, index) => (
            <li key={`${index}-${line}`}>
              <span className="trace-num mono">{String(index + 1).padStart(2, '0')}</span>
              <span className="trace-mark" />
              <span className="trace-text">{line}</span>
            </li>
          ))}
        </ol>
      ) : <div className="trace-empty"><Clock3 size={14} /> No steps recorded yet.</div>}
    </section>
  )
}

function NodeInspector({ nodeId, snap, imageUrl, corrections, setCorrections, choice, setChoice, comment, setComment, onResume, busy }) {
  const meta = NODE_META[nodeId] || NODE_META.ocr
  const Icon = meta.icon
  const waitingHere = snap.status === 'awaiting_human' && (snap.next_nodes || []).includes(nodeId)
  const visited = (snap.visit_counts?.[nodeId] || 0) > 0 || snap.last_node === nodeId || waitingHere
  const isOcrReview = nodeId === 'human_review' && waitingHere && snap.pending_review?.kind !== 'adjuster'
  const isAdjusterReview = nodeId === 'adjuster' && waitingHere && snap.pending_review?.kind === 'adjuster'
  const pending = snap.pending_review?.fields || {}
  const consult = snap.findings?.adjuster

  return (
    <div className="node-inspector">
      <div className="focus-title">
        <span className={`focus-icon focus-${nodeId}`}><Icon size={16} /></span>
        <div>
          <span className="micro-label">SELECTED STEP</span>
          <h3>{meta.title}</h3>
        </div>
        {(snap.visit_counts?.[nodeId] || 0) > 0 && <span className="visit-pill mono">{snap.visit_counts[nodeId]}×</span>}
      </div>
      {!visited && (
        <div className="honest-empty">
          <CircleDot size={15} />
          <span>This step has not run on this case yet.</span>
        </div>
      )}
      {visited && nodeId === 'ocr' && (
        <div className="node-copy">
          <p>The claim document was read. The annotated image is the source evidence for the extracted fields.</p>
          {imageUrl && <DocumentPreview imageUrl={imageUrl} compact />}
          {snap.ocr_lines?.length > 0 && (
            <div className="ocr-lines">
              <span className="micro-label">OCR OUTPUT</span>
              {snap.ocr_lines.map((line, index) => (
                <div className="ocr-line" key={`${index}-${line.text}`}>
                  <span>{line.text}</span>
                  <span className="mono">{line.confidence == null ? '—' : `${Number(line.confidence).toFixed(0)}%`}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
      {visited && (nodeId === 'extract' || nodeId === 'confidence_gate') && (
        <div className="node-copy">
          {nodeId === 'confidence_gate' && (
            <div className={`gate-callout ${(snap.fields_to_review || []).length ? 'gate-alert' : 'gate-clear'}`}>
              <span className="gate-number">{(snap.fields_to_review || []).length}</span>
              <span>
                <strong>{(snap.fields_to_review || []).length ? 'fields below 86%' : 'no fields below 86%'}</strong>
                <small>{(snap.fields_to_review || []).length ? 'They need a check before validation.' : 'Every field cleared the threshold.'}</small>
              </span>
            </div>
          )}
          <FieldTable fields={snap.fields} flagged={snap.fields_to_review} />
        </div>
      )}
      {visited && nodeId === 'human_review' && (isOcrReview ? (
        <div className="review-workspace">
          <div className="review-message">
            <span className="review-mark"><AlertCircle size={15} /></span>
            <p>{snap.pending_review?.message}</p>
          </div>
          {imageUrl && <DocumentPreview imageUrl={imageUrl} />}
          <div className="correction-header">
            <div>
              <span className="micro-label">UNCERTAIN FIELDS</span>
              <h4>Manual check</h4>
            </div>
            <span className="correction-count mono">{Object.keys(pending).length} PENDING</span>
          </div>
          <div className="correction-fields">
            {Object.entries(pending).map(([key, field]) => (
              <label className="correction-field" key={key}>
                <span className="correction-label">
                  {humanize(key)}
                  <span className="confidence-low mono">{Number(field?.confidence || 0).toFixed(0)}% confidence</span>
                </span>
                <span className="ocr-value">OCR read <strong>{field?.value || '—'}</strong></span>
                <input
                  value={corrections[key] ?? ''}
                  onChange={(event) => setCorrections({ ...corrections, [key]: event.target.value })}
                  autoComplete="off"
                />
              </label>
            ))}
          </div>
          <button className="button button-resume" type="button" disabled={busy} onClick={onResume}>
            <Check size={16} /> Confirm corrections and resume
          </button>
          <div className="review-footnote"><LockKeyhole size={12} /> The flow stays here until you confirm.</div>
        </div>
      ) : (
        <div className="node-copy">
          {snap.human_edits?.length ? (
            <>
              <div className="micro-label edits-label">CONFIRMED EDITS</div>
              <div className="edit-list">
                {snap.human_edits.map((edit) => (
                  <div className="edit-row" key={`${edit.field}-${edit.new}`}>
                    <span>{humanize(edit.field)}</span>
                    <span className="mono"><del>{edit.old || '—'}</del><ArrowRight size={12} /><strong>{edit.new}</strong></span>
                  </div>
                ))}
              </div>
            </>
          ) : (
            <div className="honest-empty"><Users size={15} /><span>This case has not asked for an OCR review.</span></div>
          )}
        </div>
      ))}
      {visited && nodeId === 'adjuster' && (isAdjusterReview ? (
        <div className="review-workspace">
          <div className="review-message">
            <span className="review-mark"><AlertCircle size={15} /></span>
            <p>{snap.pending_review?.message}</p>
          </div>
          <div className="reason-block">
            <span className="micro-label">QUESTION</span>
            <p>{snap.pending_review?.question || '—'}</p>
          </div>
          {snap.pending_review?.reason_summary && (
            <div className="question-block">
              <span className="micro-label">WHY THIS CONSULT</span>
              <p>{snap.pending_review.reason_summary}</p>
            </div>
          )}
          <div className="metric-grid">
            <div className="metric-card"><span>REPAIR</span><strong className="mono">{brl(snap.pending_review?.packet?.repair_estimate_brl)}</strong></div>
            <div className="metric-card"><span>REFERENCE</span><strong className="mono">{brl(snap.pending_review?.packet?.reference_value_brl)}</strong></div>
            <div className="metric-card"><span>LOSS RATIO</span><strong className="mono">{percent(snap.pending_review?.packet?.loss_ratio)}</strong></div>
            <div className="metric-card"><span>THRESHOLD</span><strong className="mono">{percent(snap.pending_review?.packet?.total_loss_threshold)}</strong></div>
          </div>
          {(snap.pending_review?.packet?.evidence_ids || []).length > 0 && (
            <div className="report-list">
              <span className="micro-label">EVIDENCE</span>
              {snap.pending_review.packet.evidence_ids.map((item) => <span className="evidence-chip mono" key={item}>{item}</span>)}
            </div>
          )}
          <div className="micro-label">SELECT A RESPONSE</div>
          <div className="choice-grid">
            {ADJUSTER_CHOICES.map((item) => (
              <button
                className={`choice-card${choice === item.id ? ' selected' : ''}`}
                type="button"
                key={item.id}
                onClick={() => setChoice(item.id)}
              >
                <strong>{item.label}</strong>
                <small>{item.detail}</small>
              </button>
            ))}
          </div>
          <label className="correction-field">
            <span className="correction-label">Comment, optional</span>
            <textarea
              value={comment}
              onChange={(event) => setComment(event.target.value)}
              placeholder="Add a note for the memo. It does not change the calculated recommendation."
            />
          </label>
          <button className="button button-resume" type="button" disabled={busy} onClick={onResume}>
            <Check size={16} /> Record answer and resume
          </button>
          <div className="review-footnote"><LockKeyhole size={12} /> The flow stays here until you answer.</div>
        </div>
      ) : (
        <div className="node-copy">
          {consult?.answer ? (
            <div className="consult-note">
              <span className="micro-label">RECORDED ANSWER</span>
              {consult.question && <p>{consult.question}</p>}
              <p><strong>{consult.answer}</strong></p>
            </div>
          ) : (
            <div className="honest-empty"><Users size={15} /><span>The supervisor has not escalated to an adjuster.</span></div>
          )}
        </div>
      ))}
      {visited && nodeId === 'validate_claim' && <ObjectPanel title="Validated claim" data={snap.claim} />}
      {visited && nodeId === 'supervisor' && (
        <div className="node-copy">
          {snap.routing ? (
            <>
              <div className="routing-card">
                <span className="micro-label">NEXT SPECIALIST</span>
                <strong>{AGENT_LABELS[snap.routing.next_agent] || snap.routing.next_agent}</strong>
                <span className="routing-arrow"><ArrowDownRight size={15} /></span>
              </div>
              {snap.routing.reason_summary && (
                <div className="reason-block"><span className="micro-label">REASON</span><p>{snap.routing.reason_summary}</p></div>
              )}
              {snap.routing.question && (
                <div className="question-block"><span className="micro-label">QUESTION</span><p>{snap.routing.question}</p></div>
              )}
            </>
          ) : <div className="honest-empty"><span>The supervisor has not chosen the next agent yet.</span></div>}
        </div>
      )}
      {visited && nodeId !== 'adjuster' && snap.findings?.[nodeId] && (
        <>
          <ToolTrace calls={snap.findings[nodeId].tool_calls} />
          <ObjectPanel title={`Findings · ${meta.title}`} data={withoutToolCalls(snap.findings[nodeId])} />
        </>
      )}
      {visited && nodeId === 'finalizer' && <FinalReport report={snap.final_report} consult={snap.findings?.adjuster} />}
      <PromptBlock key={nodeId} text={snap.prompts?.[nodeId]} />
    </div>
  )
}

function Studio() {
  const [cases, setCases] = useState(FALLBACK_CASES)
  const [caseId, setCaseId] = useState('AUTO-303')
  const [snap, setSnap] = useState(null)
  const [selected, setSelected] = useState(null)
  const [corrections, setCorrections] = useState({})
  const [choice, setChoice] = useState('')
  const [comment, setComment] = useState('')
  const [busy, setBusy] = useState(false)
  const [runningNode, setRunningNode] = useState(null)
  const [error, setError] = useState('')
  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes())
  const [edges, , onEdgesChange] = useEdgesState(initialEdges())
  const { fitView } = useReactFlow()

  const threadId = snap?.thread_id
  useEffect(() => {
    const id = setTimeout(() => fitView({ padding: 0.16 }), 80)
    return () => clearTimeout(id)
  }, [fitView, threadId])

  useEffect(() => {
    api('/cases').then((payload) => {
      if (payload.cases?.length) setCases(payload.cases)
    }).catch((err) => setError(err.message))
  }, [])

  useEffect(() => {
    setNodes((current) => current.map((node) => {
      const status = nodeStatus(node.id, snap)
      return {
        ...node,
        data: {
          ...node.data,
          status,
          stateLabel: STATUS_LABEL[status],
          visits: snap?.visit_counts?.[node.id] || 0,
        },
      }
    }))
  }, [snap, setNodes])

  const apply = useCallback((next) => {
    setSnap(next)
    setError('')
    if (next.status === 'awaiting_human') {
      const kind = next.pending_review?.kind
      if (kind === 'adjuster') {
        setChoice('')
        setComment('')
        setSelected(next.next_nodes?.[0] || 'adjuster')
      } else {
        const pending = next.pending_review?.fields || {}
        setCorrections(Object.fromEntries(Object.entries(pending).map(([name, field]) => [name, field?.value || ''])))
        setSelected(next.next_nodes?.[0] || 'human_review')
      }
    } else {
      setSelected(next.last_node)
    }
  }, [])

  async function run(action, nodeId) {
    setBusy(true)
    setRunningNode(nodeId)
    setError('')
    try {
      apply(await action())
    } catch (err) {
      setError(err.status === 409 ? `Step unavailable: ${err.message}` : err.message)
    } finally {
      setBusy(false)
      setRunningNode(null)
    }
  }

  const resume = () => {
    const kind = snap.pending_review?.kind
    const waiting = snap.next_nodes?.[0] || (kind === 'adjuster' ? 'adjuster' : 'human_review')
    run(
      () => api(`/runs/${snap.thread_id}/resume`, {
        method: 'POST',
        body: JSON.stringify(kind === 'adjuster' ? { choice, comment } : { corrections }),
      }),
      waiting,
    )
  }

  const reviewKind = snap?.pending_review?.kind
  const canResume = snap?.status === 'awaiting_human' && !busy && (
    reviewKind === 'adjuster'
      ? Boolean(choice)
      : Object.values(corrections).every((value) => String(value).trim())
  )
  const selectedCase = cases.find((item) => item.id === caseId) || FALLBACK_CASES[2]
  const isHuman = snap?.status === 'awaiting_human'
  const waitingNode = isHuman ? (snap.next_nodes?.[0] || (reviewKind === 'adjuster' ? 'adjuster' : 'human_review')) : null
  const focused = selected || waitingNode || snap?.last_node || 'ocr'
  const imageUrl = snap?.page_url ? `/api${snap.page_url}?v=${snap.trace.length}` : ''

  const statusLine = useMemo(() => {
    if (busy) return `Running ${NODE_META[runningNode]?.title || 'the next step'}…`
    if (!snap) return 'Waiting to start an investigation'
    if (isHuman) return reviewKind === 'adjuster' ? 'Paused for an adjuster consult' : 'Paused for OCR review'
    if (snap.status === 'finished') return 'Investigation finished'
    const next = (snap.next_nodes || []).map((id) => NODE_META[id]?.title || id)
    return `Next: ${next.join(', ') || '—'}`
  }, [snap, busy, runningNode, isHuman, reviewKind])

  return (
    <main className="desk">
      <header className="topbar">
        <div className="brand-lockup">
          <div className="brand-mark"><Shield size={19} strokeWidth={1.8} /></div>
          <div>
            <div className="brand-name">NORTE <span>·</span> CLAIMS</div>
            <div className="brand-caption">AUTOMOTIVE INVESTIGATION DESK</div>
          </div>
        </div>
        <div className="top-meta">
          <span className="desk-indicator"><span /> analysis desk</span>
          <span className="mono top-clock">{snap?.mode === 'mock' ? 'SIMULATED' : 'LOCAL API'}</span>
        </div>
      </header>
      <div className="page-wrap">
        <section className="page-heading">
          <div>
            <div className="eyebrow"><span className="eyebrow-line" /> CLAIMS DESK <span className="eyebrow-index">01 — 10</span></div>
            <h1 className="serif">Claim <em>investigation</em></h1>
            <p className="heading-sub">Follow each step, inspect the evidence, and move the analysis at your own pace.</p>
          </div>
        </section>
        <section className="control-strip">
          <label className="case-select-wrap">
            <span className="micro-label">CASE UNDER REVIEW</span>
            <span className="select-field">
              <CarFront size={17} />
              <select value={caseId} onChange={(event) => { setCaseId(event.target.value); setSnap(null); setSelected(null); setError('') }}>
                {cases.map((item) => <option key={item.id} value={item.id}>{item.id} — {item.vehicle}</option>)}
              </select>
              <ChevronDown size={14} />
            </span>
          </label>
          <div className="case-summary">
            <span className="case-vehicle">{selectedCase.vehicle}</span>
            <span className="summary-divider" />
            <span>{selectedCase.incident_type}</span>
          </div>
          <div className="control-actions">
            <button className="button button-start" type="button" disabled={busy} onClick={() => run(() => api('/runs', { method: 'POST', body: JSON.stringify({ case_id: caseId }) }), 'ocr')}>
              <Play size={14} fill="currentColor" /> Start analysis
            </button>
            <button className="button button-step" type="button" disabled={busy || !snap || snap.status !== 'running'} onClick={() => run(() => api(`/runs/${snap.thread_id}/step`, { method: 'POST' }), snap.next_nodes?.[0])}>
              <ArrowRight size={15} /> Advance step
            </button>
            {isHuman && <span className="interrupt-chip"><span /> DECISION POINT</span>}
          </div>
        </section>
        <div className="status-line">
          <span className={`status-led ${busy ? 'led-busy' : isHuman ? 'led-review' : snap?.status === 'finished' ? 'led-done' : ''}`} />
          <span>{statusLine}</span>
          {snap && <span className="thread-id mono">{snap.thread_id}</span>}
        </div>
        {error && (
          <div className="error-banner" role="alert">
            <AlertCircle size={16} />
            <span>{error}</span>
            <button type="button" aria-label="Dismiss notice" onClick={() => setError('')}>×</button>
          </div>
        )}
        {isHuman && (
          <section className="decision-banner">
            <div className="decision-icon"><Users size={18} /></div>
            <div>
              <strong>{reviewKind === 'adjuster' ? 'Adjuster consult before the memo' : 'OCR review before continuing'}</strong>
              <p>
                {reviewKind === 'adjuster'
                  ? 'The supervisor asked for a judgment. Your answer is recorded on the memo and does not change the calculated recommendation.'
                  : 'Some fields are below the confidence threshold. Compare them with the document and confirm the values.'}
              </p>
            </div>
            <div className="decision-lock"><LockKeyhole size={14} /> ADVANCE HELD</div>
          </section>
        )}
        <div className="workspace-grid">
          <section className="graph-panel">
            <div className="panel-heading graph-heading">
              <div>
                <div className="panel-kicker">INVESTIGATION FLOW <span className="tiny-rule" /></div>
                <h2>Processing map</h2>
              </div>
              <div className="graph-top-right">
                <span className="node-count-total">10 <small>STEPS</small></span>
                <button className="icon-button" type="button" title="Return to the current step" onClick={() => setSelected(waitingNode || snap?.last_node || null)}>
                  <RotateCcw size={15} />
                </button>
              </div>
            </div>
            <div className="graph-legend">
              <span><i className="legend-dot done" /> Done</span>
              <span><i className="legend-dot current" /> Just finished</span>
              <span><i className="legend-dash" /> Next</span>
              <span><i className="legend-wait" /> Human review</span>
            </div>
            <div className="flow-shell">
              <ReactFlow
                nodes={nodes}
                edges={edges}
                onNodesChange={onNodesChange}
                onEdgesChange={onEdgesChange}
                nodeTypes={nodeTypes}
                onNodeClick={(_, node) => setSelected(node.id)}
                fitView
                fitViewOptions={{ padding: 0.16 }}
                minZoom={0.2}
                nodesDraggable
                nodesConnectable={false}
                proOptions={{ hideAttribution: true }}
              >
                <Background gap={18} size={1} color="#d7d1c4" />
                <Controls showInteractive={false} position="bottom-left" />
              </ReactFlow>
            </div>
            <div className="graph-foot">
              <span><CircleDot size={12} /> Drag a block if you need room. Select one to inspect that step.</span>
              <span className="mono">READ TOP TO BOTTOM</span>
            </div>
          </section>
          <aside className="inspector">
            <div className="panel-heading inspector-heading">
              <div>
                <div className="panel-kicker">READING DESK <span className="tiny-rule" /></div>
                <h2>Step inspector</h2>
              </div>
              {snap && <span className={`inspector-status state-${nodeStatus(focused, snap)}`}>{STATUS_LABEL[nodeStatus(focused, snap)]}</span>}
            </div>
            {!snap ? (
              <>
                <div className="empty-inspector">
                  <div className="empty-stamp"><FileSearch size={22} /></div>
                  <h3>Ready to inspect</h3>
                  <p>Start an analysis to follow the document read and each decision, one step at a time.</p>
                  <div className="empty-case-note">
                    <span>SELECTED CASE</span>
                    <strong>{caseId}</strong>
                    <small>{selectedCase.vehicle} · {selectedCase.incident_type}</small>
                  </div>
                </div>
                <TracePanel trace={[]} />
              </>
            ) : (
              <div className="inspector-scroll">
                <NodeInspector
                  nodeId={focused}
                  snap={snap}
                  imageUrl={imageUrl}
                  corrections={corrections}
                  setCorrections={setCorrections}
                  choice={choice}
                  setChoice={setChoice}
                  comment={comment}
                  setComment={setComment}
                  onResume={resume}
                  busy={!canResume}
                />
                <TracePanel trace={snap.trace || []} />
              </div>
            )}
          </aside>
        </div>
        <footer className="page-footer">
          <span><Shield size={13} /> Restricted desk · decision support</span>
          <span>Recommendations support a decision. They do not authorize payment.</span>
          <span className="mono">NOR / AUTO</span>
        </footer>
      </div>
    </main>
  )
}

export default function App() {
  return (
    <ReactFlowProvider>
      <Studio />
    </ReactFlowProvider>
  )
}
