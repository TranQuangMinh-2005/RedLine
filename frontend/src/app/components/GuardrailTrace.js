'use client'

import { useEffect, useState } from 'react'
import {
  ArrowDown,
  Brain,
  CaretDown,
  ChatText,
  CheckCircle,
  Funnel,
  Prohibit,
  Robot,
  Scales,
  ShieldCheck,
  ShieldWarning,
  TextAlignLeft,
  Wrench,
  X,
} from '@phosphor-icons/react'

const STATUS = {
  passed: { label: 'qua', dot: 'bg-emerald-500', pill: 'bg-emerald-100 text-emerald-700', ring: 'border-emerald-200' },
  applied: { label: 'áp dụng', dot: 'bg-sky-500', pill: 'bg-sky-100 text-sky-700', ring: 'border-sky-200' },
  called: { label: 'đã gọi', dot: 'bg-sky-500', pill: 'bg-sky-100 text-sky-700', ring: 'border-sky-200' },
  blocked: { label: 'CHẶN', dot: 'bg-red-500', pill: 'bg-red-100 text-red-700', ring: 'border-red-300' },
  error: { label: 'lỗi', dot: 'bg-amber-500', pill: 'bg-amber-100 text-amber-700', ring: 'border-amber-300' },
  skipped: { label: 'tắt', dot: 'bg-ink-300', pill: 'bg-ink-100 text-ink-500', ring: 'border-ink-200' },
  not_reached: { label: 'không tới', dot: 'bg-ink-200', pill: 'bg-ink-50 text-ink-400', ring: 'border-dashed border-ink-200' },
}

const STAGE_ICON = {
  input_filter: Funnel,
  prompt_guard: ShieldWarning,
  llama_guard_input: ShieldCheck,
  system_prompt: TextAlignLeft,
  llm: Brain,
  tools: Wrench,
  output_filter: Funnel,
  llama_guard_output: ShieldCheck,
}

/** Màu theo kết luận: đỏ = guardrail code/model chặn, tím = LLM tự từ chối, xanh = qua. */
export function verdictTone(code) {
  if (['input_filter', 'prompt_guard', 'output_filter', 'llama_guard_input', 'llama_guard_output', 'roe_tool_limit'].includes(code)) {
    return { chip: 'bg-red-50 text-red-700 ring-red-200', icon: Prohibit, card: 'border-red-200 bg-red-50' }
  }
  if (code === 'llm_refusal') return { chip: 'bg-violet-50 text-violet-700 ring-violet-200', icon: Robot, card: 'border-violet-200 bg-violet-50' }
  if (code === 'canary_leaked') return { chip: 'bg-amber-50 text-amber-800 ring-amber-300', icon: ShieldWarning, card: 'border-amber-300 bg-amber-50' }
  if (code === 'tool_policy' || code === 'empty_reply') return { chip: 'bg-amber-50 text-amber-700 ring-amber-200', icon: ShieldWarning, card: 'border-amber-200 bg-amber-50' }
  return { chip: 'bg-emerald-50 text-emerald-700 ring-emerald-200', icon: CheckCircle, card: 'border-emerald-200 bg-emerald-50' }
}

/** Chip nhỏ dưới câu trả lời: kết luận + dải chấm trạng thái từng chốt. */
export function TraceBadge({ trace, onOpen }) {
  if (!trace?.verdict) return null
  const tone = verdictTone(trace.verdict.code)
  const Icon = tone.icon
  return (
    <button
      type="button"
      onClick={onOpen}
      className={`mt-2 flex w-full items-center gap-2 rounded-xl px-2.5 py-1.5 text-left text-[11px] ring-1 transition hover:brightness-95 ${tone.chip}`}
      title="Xem đường đi của prompt qua các guardrail"
    >
      <Icon size={13} weight="fill" className="shrink-0" />
      <span className="min-w-0 flex-1 truncate font-medium">{trace.verdict.title}</span>
      <span className="flex shrink-0 items-center gap-0.5" aria-hidden>
        {trace.stages.map((s) => (
          <span key={s.id} className={`h-1.5 w-1.5 rounded-full ${(STATUS[s.status] || STATUS.skipped).dot}`} />
        ))}
      </span>
      <span className="shrink-0 text-[10px] underline decoration-dotted">trace</span>
    </button>
  )
}

/** Thanh điểm injection 0..1 cho từng đoạn, vạch đỏ khi ≥ ngưỡng. */
function ScoreBars({ scores, threshold, labelPrefix }) {
  if (!scores?.length) return null
  return (
    <ul className="mt-1 space-y-0.5">
      {scores.map((score, i) => (
        <li key={i} className="flex items-center gap-2 text-[10px]">
          <span className="w-16 shrink-0 text-ink-400">{labelPrefix} {i + 1}</span>
          <span className="relative h-1.5 flex-1 overflow-hidden rounded-full bg-ink-200">
            <span className={`absolute inset-y-0 left-0 ${score >= threshold ? 'bg-red-500' : 'bg-emerald-500'}`} style={{ width: `${Math.max(2, score * 100)}%` }} />
            <span className="absolute inset-y-0 w-px bg-ink-600" style={{ left: `${threshold * 100}%` }} aria-hidden />
          </span>
          <span className={`w-12 shrink-0 text-right font-mono ${score >= threshold ? 'font-semibold text-red-600' : 'text-ink-500'}`}>{score.toFixed(3)}</span>
        </li>
      ))}
    </ul>
  )
}

function RuleList({ rules, onOpenRule }) {
  if (!rules?.length) return null
  return (
    <ul className="space-y-1">
      {rules.map((rule) => (
        <li key={rule.id} className="rounded-lg bg-white/80 px-2 py-1.5">
          <button
            type="button"
            onClick={() => onOpenRule?.(rule.id)}
            className="font-mono text-[10px] font-semibold text-red-700 underline decoration-dotted"
            title="Xem nội dung luật"
          >
            {rule.id}
          </button>
          {rule.description && <p className="text-[11px] text-ink-600">{rule.description}</p>}
        </li>
      ))}
    </ul>
  )
}

/** Một lượt gọi LLM: suy luận (nếu có), tool được gọi kèm tham số. */
function LlmRound({ call, index }) {
  const [open, setOpen] = useState(index === 0)
  const reasoning = (call.reasoning || '').trim()
  return (
    <li className="rounded-xl border border-ink-200 bg-white/80 px-2 py-1.5">
      <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5 font-mono text-[10px] text-ink-500">
        <span className="rounded bg-ink-100 px-1.5 font-semibold text-ink-600">vòng {index + 1}</span>
        <span>{call.total_tokens} tok</span>
        <span>{Number(call.latency_s).toFixed(2)}s</span>
        <span>{call.finish_reason}</span>
      </div>
      {call.tool_calls?.length > 0 && (
        <ul className="mt-1 space-y-0.5">
          {call.tool_calls.map((tc, i) => (
            <li key={i} className="flex items-start gap-1 text-[10px]">
              <Wrench size={11} className="mt-0.5 shrink-0 text-brand-600" />
              <span className="min-w-0">
                <span className="font-mono font-semibold text-brand-700">{tc.name}</span>
                {tc.arguments && (
                  <code className="ml-1 break-all font-mono text-ink-500">{tc.arguments}</code>
                )}
              </span>
            </li>
          ))}
        </ul>
      )}
      {reasoning ? (
        <>
          <button
            type="button"
            onClick={() => setOpen((v) => !v)}
            className="mt-1 flex items-center gap-1 text-[10px] font-medium text-violet-700 hover:underline"
          >
            <Brain size={11} weight="duotone" />
            Suy luận của model ({reasoning.length} ký tự)
            <CaretDown size={9} className={`transition ${open ? 'rotate-180' : ''}`} />
          </button>
          {open && (
            <pre className="mt-1 max-h-56 overflow-auto whitespace-pre-wrap rounded-lg bg-violet-50 px-2 py-1.5 font-mono text-[10px] leading-relaxed text-violet-900">
              {reasoning}
            </pre>
          )}
        </>
      ) : (
        <p className="mt-1 text-[10px] text-ink-400">Provider không trả chuỗi suy luận cho model này.</p>
      )}
    </li>
  )
}

function Label({ children }) {
  return <p className="mb-0.5 text-[10px] font-semibold uppercase tracking-wide text-ink-400">{children}</p>
}

function StageDetails({ stage, onOpenRule }) {
  const d = stage.details || {}
  return (
    <div className="mt-2 space-y-2 text-[11px] text-ink-600">
      <RuleList rules={d.rules} onOpenRule={onOpenRule} />
      {d.matched_text && (
        <div>
          <Label>Đoạn khớp{d.decoded ? ' (sau khi giải mã Base64/hex)' : ''}</Label>
          <code className="block whitespace-pre-wrap break-words rounded-lg bg-red-100/70 px-2 py-1 font-mono text-[11px] text-red-800">
            {d.matched_text}
          </code>
        </div>
      )}
      {d.earlier_turn && <p className="text-amber-700">Luật khớp ở một lượt user trước đó trong session — mở hội thoại mới để thử lại.</p>}
      {d.prompt_guard && (
        <div className="rounded-lg bg-white/80 px-2 py-1.5">
          <p>
            Model <span className="font-mono">{d.model}</span> · ngưỡng {d.prompt_guard.threshold} · {d.prompt_guard.latency_s}s
          </p>
          {d.prompt_guard.error && <p className="text-amber-700">Lỗi: {d.prompt_guard.error}</p>}
          <ScoreBars scores={d.prompt_guard.scores} threshold={d.prompt_guard.threshold} labelPrefix="lượt user" />
        </div>
      )}
      {d.verdict && (
        <div className="rounded-lg bg-white/80 px-2 py-1.5">
          <p>
            Model <span className="font-mono">{d.model}</span> · {d.verdict.latency_s}s · raw:{' '}
            <code className="font-mono">{d.verdict.raw || '—'}</code>
          </p>
          {d.verdict.categories?.map((c) => (
            <span key={c.code} className="mr-1 mt-1 inline-block rounded-full bg-red-100 px-2 py-0.5 text-[10px] text-red-700">
              {c.code} · {c.name}
            </span>
          ))}
          {d.verdict.error && <p className="text-amber-700">Lỗi: {d.verdict.error}</p>}
        </div>
      )}
      {d.sections && (
        <div>
          <Label>Các phần system prompt đã gửi</Label>
          <div className="flex flex-wrap gap-1">
            {d.sections.map((s) => (
              <button
                key={s.key}
                type="button"
                onClick={() => onOpenRule?.(`section:${s.key}`)}
                className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${
                  s.key.startsWith('hardening') ? 'bg-sky-600 text-white' : 'bg-sky-100 text-sky-700'
                }`}
              >
                {s.title}
              </button>
            ))}
          </div>
        </div>
      )}
      {d.calls?.length > 0 && (
        <div>
          <Label>Các lượt gọi LLM ({d.calls.length})</Label>
          <ol className="space-y-1.5">
            {d.calls.map((c, i) => <LlmRound key={i} call={c} index={i} />)}
          </ol>
        </div>
      )}
      {d.events?.length > 0 && (
        <div className="space-y-1">
          <Label>Lời gọi tool</Label>
          {d.events.map((e, i) => (
            <div key={i} className={`rounded-lg px-2 py-1.5 ${e.allowed && !e.actions?.length ? 'bg-white/80' : 'bg-red-50'}`}>
              <p className="font-mono text-[10px]">
                {e.tool} · {e.allowed ? 'cho phép' : 'CHẶN'} · {e.result_status || '—'}
              </p>
              {e.arguments && <code className="block break-words font-mono text-[10px] text-ink-500">{JSON.stringify(e.arguments)}</code>}
              {e.error && <p className="text-[10px] text-red-600">{e.error}</p>}
              {e.prompt_guard && (
                <ScoreBars scores={e.prompt_guard.scores} threshold={e.prompt_guard.threshold} labelPrefix="tài liệu" />
              )}
              {e.result_preview && (
                <details className="mt-1">
                  <summary className="cursor-pointer text-[10px] text-ink-400">Kết quả trả về cho model</summary>
                  <pre className="mt-1 max-h-40 overflow-auto whitespace-pre-wrap break-all rounded bg-ink-50 px-2 py-1 font-mono text-[10px] text-ink-600">
                    {e.result_preview}
                  </pre>
                </details>
              )}
              <RuleList rules={e.rules} onOpenRule={onOpenRule} />
            </div>
          ))}
        </div>
      )}
      {d.raw_reply && (
        <div>
          <Label>Câu trả lời gốc của LLM (trước khi bị thay)</Label>
          <p className="max-h-40 overflow-y-auto whitespace-pre-wrap rounded-lg bg-white/80 px-2 py-1.5">{d.raw_reply}</p>
        </div>
      )}
      {d.block_reply && (
        <div>
          <Label>Câu từ chối cố định trả cho người dùng</Label>
          <p className="rounded-lg bg-white/80 px-2 py-1.5 italic">{d.block_reply}</p>
        </div>
      )}
    </div>
  )
}

function StageNode({ stage, onOpenRule }) {
  const st = STATUS[stage.status] || STATUS.skipped
  const Icon = STAGE_ICON[stage.id] || ShieldCheck
  const expandable = stage.status !== 'not_reached' && stage.status !== 'skipped' && Object.keys(stage.details || {}).length > 0
  const [open, setOpen] = useState(stage.status === 'blocked' || stage.status === 'error')
  return (
    <div className={`rounded-2xl border px-3 py-2 ${st.ring} ${stage.status === 'blocked' ? 'bg-red-50/60' : 'bg-white'}`}>
      <button
        type="button"
        disabled={!expandable}
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-2 text-left disabled:cursor-default"
        aria-expanded={expandable ? open : undefined}
      >
        <Icon size={15} weight="duotone" className={stage.status === 'not_reached' ? 'text-ink-300' : 'text-ink-600'} />
        <span className={`flex-1 text-[12px] font-semibold ${stage.status === 'not_reached' ? 'text-ink-400' : 'text-ink-700'}`}>
          {stage.title}
        </span>
        <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${st.pill}`}>{st.label}</span>
        {expandable && <CaretDown size={12} className={`text-ink-400 transition ${open ? 'rotate-180' : ''}`} />}
      </button>
      <p className={`mt-0.5 pl-6 text-[11px] ${stage.status === 'not_reached' ? 'text-ink-300' : 'text-ink-500'}`}>{stage.summary}</p>
      {expandable && open && <div className="pl-6"><StageDetails stage={stage} onOpenRule={onOpenRule} /></div>}
    </div>
  )
}

function Connector({ stopped }) {
  return (
    <div className="flex justify-center py-0.5" aria-hidden>
      <ArrowDown size={12} className={stopped ? 'text-ink-200' : 'text-ink-400'} />
    </div>
  )
}

function interpretCompare(results) {
  const by = Object.fromEntries(results.map((r) => [r.variant, r]))
  const answered = (r) => r && !r.refusal && !r.empty
  if (by.no_system_prompt && (by.no_system_prompt.refusal)) {
    return 'Ngay cả khi KHÔNG có system prompt model vẫn từ chối → do chính sách an toàn của model.'
  }
  if (answered(by.no_system_prompt) && by.no_hardening?.refusal) {
    return 'Không system prompt thì model trả lời, có prompt nền thì từ chối → do system prompt (quy tắc bảo mật cơ bản).'
  }
  if (answered(by.no_hardening) && by.active_prompt?.refusal) {
    return 'Prompt nền thì trả lời, thêm hardening thì từ chối → do phần prompt hardening của profile.'
  }
  if (results.some((r) => r.empty)) return 'Có biến thể trả rỗng (hết token) — chưa đủ căn cứ, thử lại.'
  if (results.every(answered)) return 'Mọi biến thể đều trả lời khi không có guardrail code → lần từ chối trước có thể do ngẫu nhiên hoặc lịch sử hội thoại.'
  return 'Kết quả chưa rõ ràng — xem nội dung từng biến thể.'
}

function ComparePanel({ apiBase, prompt, mode, hardening }) {
  const [state, setState] = useState({ loading: false, data: null, error: null })
  useEffect(() => setState({ loading: false, data: null, error: null }), [prompt])

  const run = async () => {
    setState({ loading: true, data: null, error: null })
    try {
      const variants = hardening ? ['no_system_prompt', 'no_hardening', 'active_prompt'] : ['no_system_prompt', 'no_hardening']
      const res = await fetch(`${apiBase}/chat/compare`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: prompt, mode, variants }),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(data?.detail || `HTTP ${res.status}`)
      setState({ loading: false, data, error: null })
    } catch (err) {
      setState({ loading: false, data: null, error: err.message })
    }
  }

  return (
    <section className="space-y-2 rounded-2xl border border-violet-200 bg-violet-50/50 p-3">
      <div className="flex items-center justify-between gap-2">
        <h4 className="flex items-center gap-1.5 text-[12px] font-semibold text-violet-800">
          <Scales size={14} weight="duotone" /> So sánh nguyên nhân từ chối
        </h4>
        <button
          type="button"
          onClick={run}
          disabled={state.loading || !prompt}
          className="rounded-lg bg-violet-600 px-2.5 py-1 text-[11px] font-semibold text-white hover:bg-violet-700 disabled:opacity-50"
        >
          {state.loading ? 'Đang chạy…' : state.data ? 'Chạy lại' : 'Chạy so sánh'}
        </button>
      </div>
      <p className="text-[10px] text-violet-700">
        Gửi lại cùng prompt tới model, BỎ QUA guardrail code và tool, với các biến thể system prompt. Tốn thêm token.
      </p>
      {state.error && <p className="text-[11px] text-red-600">{state.error}</p>}
      {state.data && (
        <>
          <p className="rounded-lg bg-white px-2 py-1.5 text-[11px] font-medium text-violet-900">{interpretCompare(state.data.results)}</p>
          {state.data.results.map((r) => (
            <div key={r.variant} className="rounded-lg bg-white px-2 py-1.5">
              <div className="flex items-center justify-between gap-2">
                <span className="text-[11px] font-semibold text-ink-700">{r.label}</span>
                <span
                  className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${
                    r.empty ? 'bg-amber-100 text-amber-700' : r.refusal ? 'bg-violet-100 text-violet-700' : 'bg-emerald-100 text-emerald-700'
                  }`}
                >
                  {r.empty ? `rỗng (${r.finish_reason})` : r.refusal ? 'từ chối' : 'trả lời'}
                </span>
              </div>
              <p className="mt-1 line-clamp-4 whitespace-pre-wrap text-[11px] text-ink-600">{r.reply || '—'}</p>
              {r.canary_leaked && <p className="text-[10px] font-semibold text-amber-700">Lộ canary (đã ẩn)</p>}
            </div>
          ))}
          <p className="text-[10px] text-ink-400">{state.data.note}</p>
        </>
      )}
    </section>
  )
}

/** Drawer: đường đi của một prompt qua các chốt guardrail. */
export default function TraceDrawer({ apiBase = '/api', view, onClose, onOpenRule }) {
  if (!view?.trace) return null
  const { trace, prompt, reply } = view
  const tone = verdictTone(trace.verdict?.code)
  const VerdictIcon = tone.icon
  let stopped = false

  return (
    <div className="fixed inset-0 z-40 flex justify-end bg-ink-900/20 backdrop-blur-[1px]">
      <button aria-label="Đóng trace" className="absolute inset-0" onClick={onClose} />
      <aside
        role="dialog"
        aria-modal="true"
        aria-labelledby="trace-title"
        className="relative flex h-full w-full max-w-md flex-col border-l border-ink-200 bg-ink-50 shadow-xl"
      >
        <div className="flex items-center justify-between border-b border-ink-200 bg-white px-4 py-3">
          <div>
            <h2 id="trace-title" className="text-sm font-semibold text-ink-800">Đường đi của prompt</h2>
            <p className="text-[11px] text-ink-400">
              profile <span className="font-mono">{trace.profile}</span> · {trace.mode === 'llm' ? 'LLM thuần' : 'Agent'} · Llama Guard{' '}
              {trace.llama_guard?.enabled ? 'bật' : 'tắt'}
            </p>
          </div>
          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={() => onOpenRule?.(null)}
              className="rounded-lg px-2 py-1 text-[11px] font-medium text-brand-700 hover:bg-brand-50"
            >
              Nội dung guardrail
            </button>
            <button onClick={onClose} className="grid h-8 w-8 place-items-center rounded-full text-ink-400 hover:bg-ink-100" aria-label="Đóng">
              <X size={16} />
            </button>
          </div>
        </div>

        <div className="chat-scroll min-h-0 flex-1 space-y-3 overflow-y-auto p-4">
          <div className={`rounded-2xl border p-3 ${tone.card}`}>
            <p className="flex items-center gap-1.5 text-[13px] font-semibold text-ink-800">
              <VerdictIcon size={16} weight="fill" /> {trace.verdict?.title}
            </p>
            <p className="mt-1 text-[12px] leading-relaxed text-ink-600">{trace.verdict?.detail}</p>
            <p className="mt-1.5 text-[11px] font-medium text-ink-500">
              {trace.reached_llm ? '✓ Prompt đã tới LLM' : '✗ Prompt KHÔNG tới LLM'}
              {trace.verdict?.heuristic && ' · nhận diện từ chối bằng heuristic'}
            </p>
          </div>

          <div>
            <div className="rounded-2xl border border-ink-200 bg-white px-3 py-2">
              <p className="flex items-center gap-2 text-[12px] font-semibold text-ink-700">
                <ChatText size={15} weight="duotone" /> Prompt người dùng
              </p>
              <p className="mt-0.5 line-clamp-3 whitespace-pre-wrap pl-6 text-[11px] text-ink-500">{prompt}</p>
            </div>
            {trace.stages.map((stage) => {
              const node = (
                <div key={stage.id}>
                  <Connector stopped={stopped} />
                  <StageNode stage={stage} onOpenRule={onOpenRule} />
                </div>
              )
              if (stage.status === 'blocked' && stage.id !== 'tools') stopped = true
              return node
            })}
            <Connector stopped={false} />
            <div className="rounded-2xl border border-ink-200 bg-white px-3 py-2">
              <p className="flex items-center gap-2 text-[12px] font-semibold text-ink-700">
                <Robot size={15} weight="duotone" /> Câu trả lời đã giao
              </p>
              <p className="mt-0.5 line-clamp-4 whitespace-pre-wrap pl-6 text-[11px] text-ink-500">{reply}</p>
            </div>
          </div>

          {trace.reached_llm && ['llm_refusal', 'passed', 'tool_policy', 'empty_reply'].includes(trace.verdict?.code) && (
            <ComparePanel
              apiBase={apiBase}
              prompt={prompt}
              mode={trace.mode}
              hardening={Boolean(trace.flags?.prompt_hardening)}
            />
          )}
        </div>
      </aside>
    </div>
  )
}
