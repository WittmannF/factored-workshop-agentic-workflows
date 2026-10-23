import { Handle, MarkerType, Position } from '@xyflow/react'
import {
  BadgeCheck,
  ClipboardCheck,
  FileSearch,
  FileText,
  Gauge,
  GitBranch,
  Scale,
  Shield,
  Users,
  Wrench,
} from 'lucide-react'

export const NODE_META = {
  ocr: { title: 'Document read', icon: FileSearch },
  extract: { title: 'Structured extract', icon: FileText },
  confidence_gate: { title: 'Confidence gate', icon: Gauge },
  human_review: { title: 'OCR review', icon: Users },
  validate_claim: { title: 'Validate claim', icon: ClipboardCheck },
  supervisor: { title: 'Supervisor', icon: GitBranch },
  coverage: { title: 'Coverage', icon: Shield },
  damage: { title: 'Damage', icon: Wrench },
  adjuster: { title: 'Adjuster consult', icon: Scale },
  finalizer: { title: 'Investigation memo', icon: BadgeCheck },
}

export const STATUS_LABEL = {
  idle: 'not run',
  next: 'next',
  current: 'just finished',
  done: 'done',
  waiting: 'waiting on you',
}

const SPINE = 260
const LEFT = 0
const RIGHT = 520

const NODES = [
  { id: 'ocr', x: SPINE, y: 0 },
  { id: 'extract', x: SPINE, y: 108 },
  { id: 'confidence_gate', x: SPINE, y: 216 },
  { id: 'human_review', x: RIGHT, y: 204 },
  { id: 'validate_claim', x: SPINE, y: 336 },
  { id: 'supervisor', x: SPINE, y: 460 },
  { id: 'coverage', x: LEFT, y: 430 },
  { id: 'damage', x: RIGHT, y: 430 },
  { id: 'adjuster', x: RIGHT, y: 580 },
  { id: 'finalizer', x: SPINE, y: 720 },
]

const HANDLES = {
  ocr: [
    { id: 'bottom', type: 'source', position: Position.Bottom },
  ],
  extract: [
    { id: 'top', type: 'target', position: Position.Top },
    { id: 'bottom', type: 'source', position: Position.Bottom },
  ],
  confidence_gate: [
    { id: 'top', type: 'target', position: Position.Top },
    { id: 'bottom', type: 'source', position: Position.Bottom },
    { id: 'right', type: 'source', position: Position.Right },
  ],
  human_review: [
    { id: 'left', type: 'target', position: Position.Left },
    { id: 'bottom', type: 'source', position: Position.Bottom },
  ],
  validate_claim: [
    { id: 'top', type: 'target', position: Position.Top },
    { id: 'right', type: 'target', position: Position.Right },
    { id: 'bottom', type: 'source', position: Position.Bottom },
  ],
  supervisor: [
    { id: 'top', type: 'target', position: Position.Top },
    { id: 'bottom', type: 'source', position: Position.Bottom },
    { id: 'coverage-out', type: 'source', position: Position.Left, style: { top: '36%' } },
    { id: 'coverage-in', type: 'target', position: Position.Left, style: { top: '68%' } },
    { id: 'damage-out', type: 'source', position: Position.Right, style: { top: '32%' } },
    { id: 'damage-in', type: 'target', position: Position.Right, style: { top: '50%' } },
    { id: 'adjuster-out', type: 'source', position: Position.Right, style: { top: '70%' } },
    { id: 'adjuster-in', type: 'target', position: Position.Right, style: { top: '88%' } },
  ],
  coverage: [
    { id: 'in', type: 'target', position: Position.Right, style: { top: '32%' } },
    { id: 'out', type: 'source', position: Position.Right, style: { top: '68%' } },
  ],
  damage: [
    { id: 'in', type: 'target', position: Position.Left, style: { top: '32%' } },
    { id: 'out', type: 'source', position: Position.Left, style: { top: '68%' } },
  ],
  adjuster: [
    { id: 'in', type: 'target', position: Position.Left, style: { top: '32%' } },
    { id: 'out', type: 'source', position: Position.Left, style: { top: '68%' } },
  ],
  finalizer: [
    { id: 'top', type: 'target', position: Position.Top },
  ],
}

function edgeStyle(color, dashed) {
  return {
    type: 'smoothstep',
    pathOptions: { borderRadius: 18 },
    markerEnd: { type: MarkerType.ArrowClosed, color, width: 14, height: 14 },
    style: { stroke: color, strokeWidth: 1.7, ...(dashed ? { strokeDasharray: '5 4' } : {}) },
    labelStyle: { fill: color, fontSize: 11, fontWeight: 600, fontFamily: 'DM Mono, ui-monospace, monospace' },
    labelBgStyle: { fill: '#f4f0e7', fillOpacity: 0.96 },
    labelBgPadding: [5, 3],
    labelBgBorderRadius: 4,
  }
}

const EDGES = [
  { id: 'ocr-extract', source: 'ocr', target: 'extract', sourceHandle: 'bottom', targetHandle: 'top', ...edgeStyle('#7d8a80') },
  { id: 'extract-gate', source: 'extract', target: 'confidence_gate', sourceHandle: 'bottom', targetHandle: 'top', ...edgeStyle('#7d8a80') },
  { id: 'gate-validate', source: 'confidence_gate', target: 'validate_claim', sourceHandle: 'bottom', targetHandle: 'top', label: 'clear', ...edgeStyle('#3d7a62') },
  { id: 'gate-human', source: 'confidence_gate', target: 'human_review', sourceHandle: 'right', targetHandle: 'left', label: 'low confidence', ...edgeStyle('#b25743') },
  { id: 'human-validate', source: 'human_review', target: 'validate_claim', sourceHandle: 'bottom', targetHandle: 'right', label: 'resume', ...edgeStyle('#b25743') },
  { id: 'validate-supervisor', source: 'validate_claim', target: 'supervisor', sourceHandle: 'bottom', targetHandle: 'top', ...edgeStyle('#7d8a80') },
  { id: 'supervisor-coverage', source: 'supervisor', target: 'coverage', sourceHandle: 'coverage-out', targetHandle: 'in', ...edgeStyle('#7d8a80') },
  { id: 'coverage-supervisor', source: 'coverage', target: 'supervisor', sourceHandle: 'out', targetHandle: 'coverage-in', ...edgeStyle('#b0b1a6', true) },
  { id: 'supervisor-damage', source: 'supervisor', target: 'damage', sourceHandle: 'damage-out', targetHandle: 'in', ...edgeStyle('#7d8a80') },
  { id: 'damage-supervisor', source: 'damage', target: 'supervisor', sourceHandle: 'out', targetHandle: 'damage-in', ...edgeStyle('#b0b1a6', true) },
  { id: 'supervisor-adjuster', source: 'supervisor', target: 'adjuster', sourceHandle: 'adjuster-out', targetHandle: 'in', label: 'escalate', ...edgeStyle('#b25743') },
  { id: 'adjuster-supervisor', source: 'adjuster', target: 'supervisor', sourceHandle: 'out', targetHandle: 'adjuster-in', label: 'answer', ...edgeStyle('#b25743', true) },
  { id: 'supervisor-finalizer', source: 'supervisor', target: 'finalizer', sourceHandle: 'bottom', targetHandle: 'top', label: 'FINISH', ...edgeStyle('#a66f4e') },
]

export function initialNodes() {
  return NODES.map((node) => ({
    id: node.id,
    type: 'claim',
    position: { x: node.x, y: node.y },
    data: { nodeId: node.id, status: 'idle', visits: 0, stateLabel: STATUS_LABEL.idle },
  }))
}

export function initialEdges() {
  return EDGES
}

export function ClaimNode({ data, selected }) {
  const meta = NODE_META[data.nodeId] || NODE_META.ocr
  const Icon = meta.icon
  return (
    <div className={`node-card state-${data.status}${selected ? ' selected-node' : ''}${data.nodeId === 'supervisor' ? ' node-hub' : ''}`}>
      {(HANDLES[data.nodeId] || []).map((handle) => (
        <Handle key={handle.id} id={handle.id} type={handle.type} position={handle.position} style={handle.style} />
      ))}
      <div className="node-top">
        <span className="node-icon"><Icon size={13} strokeWidth={2.2} /></span>
        <span className="node-name">{meta.title}</span>
      </div>
      <div className="node-id"><span className="node-state">{data.stateLabel}</span></div>
      {data.visits > 0 && <span className="node-count">{data.visits}</span>}
    </div>
  )
}

export function nodeStatus(id, snap) {
  if (!snap) return 'idle'
  if (snap.status === 'awaiting_human' && (snap.next_nodes || []).includes(id)) return 'waiting'
  if (snap.last_node === id) return 'current'
  if ((snap.next_nodes || []).includes(id)) return 'next'
  if ((snap.visit_counts?.[id] || 0) > 0) return 'done'
  return 'idle'
}
