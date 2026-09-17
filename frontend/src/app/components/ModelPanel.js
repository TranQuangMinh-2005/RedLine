'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  ArrowClockwise,
  CheckCircle,
  CloudArrowDown,
  Cpu,
  HardDrives,
  PlugsConnected,
  Trash,
  Warning,
  X,
} from '@phosphor-icons/react'

const ENDPOINT_TABS = [
  { kind: 'groq', label: 'Groq', hint: 'API Groq — mặc định GPT-OSS 20B' },
  { kind: 'env', label: 'Docker env', hint: 'Endpoint khai báo trong .env của container' },
  { kind: 'custom', label: 'Kaggle / URL', hint: 'Kaggle Ollama gateway (ngrok) hoặc URL OpenAI-compatible' },
]

const FAMILY_LABEL = { 'gpt-oss': 'GPT-OSS', qwen: 'Qwen', llama: 'Llama' }

async function api(apiBase, path, options = {}) {
  const res = await fetch(`${apiBase}${path}`, {
    ...options,
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
  })
  const data = await res.json().catch(() => ({}))
  if (!res.ok) {
    const detail = Array.isArray(data?.detail) ? data.detail.map((d) => d.msg).join('; ') : data?.detail
    throw new Error(detail || `HTTP ${res.status}`)
  }
  return data
}

function formatBytes(n) {
  if (!n) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  const i = Math.min(units.length - 1, Math.floor(Math.log(n) / Math.log(1024)))
  return `${(n / 1024 ** i).toFixed(i >= 2 ? 1 : 0)} ${units[i]}`
}

/** Tóm tắt model đang dùng — đặt ở sidebar. */
export function ModelSummary({ active, onOpen, disabled }) {
  return (
    <div className="space-y-2">
      <p className="text-[11px] font-semibold uppercase tracking-wide text-ink-400">Model</p>
      <button
        type="button"
        onClick={onOpen}
        disabled={disabled}
        className="flex w-full items-center gap-2 rounded-xl border border-ink-200 bg-white px-3 py-2 text-left transition hover:border-brand-300 disabled:opacity-50"
      >
        <Cpu size={16} weight="duotone" className="shrink-0 text-brand-600" />
        <span className="min-w-0 flex-1 leading-tight">
          <span className="block truncate font-mono text-[11px] font-semibold text-ink-700">
            {active?.model || 'đang tải…'}
          </span>
          <span className="block truncate text-[10px] text-ink-400">
            {active ? `${active.kind === 'custom' ? 'Kaggle/URL' : active.kind === 'env' ? 'Docker env' : 'Groq'} · ${active.provider}` : ''}
          </span>
        </span>
        <span className="shrink-0 text-[10px] font-medium text-brand-700">Đổi</span>
      </button>
    </div>
  )
}

export default function ModelPanel({ apiBase = '/api', open, onClose, onChanged }) {
  const [config, setConfig] = useState(null)
  const [tab, setTab] = useState('groq')
  const [baseUrl, setBaseUrl] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [discovery, setDiscovery] = useState(null)
  const [selected, setSelected] = useState('')
  const [loading, setLoading] = useState(false)
  const [applying, setApplying] = useState(false)
  const [error, setError] = useState(null)
  const [notice, setNotice] = useState(null)
  const [catalog, setCatalog] = useState([])
  const [jobs, setJobs] = useState([])
  const finishedJobs = useRef(new Set())

  const gatewayKind = discovery?.gateway ? discovery.endpoint.kind : null

  const loadConfig = useCallback(async () => {
    const data = await api(apiBase, '/config/llm')
    setConfig(data)
    return data
  }, [apiBase])

  const discover = useCallback(async (kind, body = {}) => {
    setLoading(true)
    setError(null)
    setDiscovery(null)
    setCatalog([])
    setJobs([])
    try {
      const data = await api(apiBase, '/config/llm/discover', {
        method: 'POST',
        body: JSON.stringify({ endpoint: kind, ...body }),
      })
      setDiscovery(data)
      setSelected((prev) => {
        const ids = data.models.map((m) => m.id)
        if (ids.includes(prev)) return prev
        return data.models.find((m) => m.featured)?.id || ids[0] || ''
      })
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [apiBase])

  // Mở panel: đọc cấu hình hiện hành, nhảy tới tab đang dùng.
  useEffect(() => {
    if (!open) return
    setNotice(null)
    loadConfig()
      .then((data) => {
        const active = data.active
        setTab(active.kind)
        setSelected(active.model)
        const custom = data.endpoints.find((e) => e.kind === 'custom')
        if (custom?.base_url) setBaseUrl(custom.base_url)
        const target = data.endpoints.find((e) => e.kind === active.kind)
        if (active.kind !== 'custom' || target?.configured) discover(active.kind)
      })
      .catch((err) => setError(err.message))
  }, [open, loadConfig, discover])

  const switchTab = (kind) => {
    setTab(kind)
    setError(null)
    setDiscovery(null)
    const endpoint = config?.endpoints.find((e) => e.kind === kind)
    if (kind !== 'custom' || endpoint?.configured) discover(kind)
  }

  const connectCustom = (e) => {
    e.preventDefault()
    // Để trống API key -> giữ key đã lưu cho cùng URL.
    discover('custom', { base_url: baseUrl, ...(apiKey ? { api_key: apiKey } : {}) })
    setApiKey('')
  }

  const apply = async () => {
    if (!selected) return
    setApplying(true)
    setError(null)
    try {
      const data = await api(apiBase, '/config/llm', {
        method: 'POST',
        body: JSON.stringify({ endpoint: tab, model: selected }),
      })
      setConfig(data)
      setNotice(`Đang dùng ${data.active.model}`)
      onChanged?.(data)
    } catch (err) {
      setError(err.message)
    } finally {
      setApplying(false)
    }
  }

  // ===== Gateway: catalog + tiến trình tải =====
  const refreshGateway = useCallback(async () => {
    if (!gatewayKind) return []
    const q = `?endpoint=${gatewayKind}`
    const [cat, pulls] = await Promise.all([
      api(apiBase, `/config/llm/gateway/catalog${q}`),
      api(apiBase, `/config/llm/gateway/pulls${q}`),
    ])
    setCatalog(cat.models || [])
    setJobs(pulls.jobs || [])
    return pulls.jobs || []
  }, [apiBase, gatewayKind])

  const running = jobs.some((j) => j.state === 'running')

  useEffect(() => {
    if (!open || !gatewayKind) return undefined
    let cancelled = false
    let timer
    const tick = async () => {
      try {
        const latest = await refreshGateway()
        const newlyDone = latest.filter((j) => j.state === 'success' && !finishedJobs.current.has(j.id))
        latest.filter((j) => j.state !== 'running').forEach((j) => finishedJobs.current.add(j.id))
        if (newlyDone.length && !cancelled) {
          const ids = await api(apiBase, '/config/llm/discover', {
            method: 'POST',
            body: JSON.stringify({ endpoint: gatewayKind }),
          })
          setDiscovery(ids)
        }
        if (!cancelled) timer = setTimeout(tick, latest.some((j) => j.state === 'running') ? 1000 : 5000)
      } catch (err) {
        if (!cancelled) {
          setError(err.message)
          timer = setTimeout(tick, 5000)
        }
      }
    }
    tick()
    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [open, gatewayKind, refreshGateway, apiBase])

  const startPull = async (model) => {
    setError(null)
    try {
      await api(apiBase, `/config/llm/gateway/pulls?endpoint=${gatewayKind}`, {
        method: 'POST',
        body: JSON.stringify({ model }),
      })
      await refreshGateway()
    } catch (err) {
      setError(err.message)
    }
  }

  const cancelPull = async (jobId) => {
    try {
      await api(apiBase, `/config/llm/gateway/pulls/${jobId}?endpoint=${gatewayKind}`, { method: 'DELETE' })
      await refreshGateway()
    } catch (err) {
      setError(err.message)
    }
  }

  const deleteModel = async (model) => {
    if (!window.confirm(`Xóa ${model} khỏi Kaggle?`)) return
    try {
      await api(apiBase, `/config/llm/gateway/models/${encodeURIComponent(model)}?endpoint=${gatewayKind}`, {
        method: 'DELETE',
      })
      await refreshGateway()
      discover(gatewayKind)
    } catch (err) {
      setError(err.message)
    }
  }

  const grouped = useMemo(() => {
    const groups = {}
    for (const m of discovery?.models || []) {
      const key = m.featured ? FAMILY_LABEL[m.family] || 'Nổi bật' : 'Khác'
      ;(groups[key] ||= []).push(m)
    }
    return Object.entries(groups).sort(([a], [b]) => (a === 'Khác') - (b === 'Khác'))
  }, [discovery])

  const [customPull, setCustomPull] = useState('')
  const active = config?.active
  const isActive = active && active.kind === tab && active.model === selected

  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-ink-900/30 backdrop-blur-[2px] sm:items-center sm:p-4">
      <button aria-label="Đóng" className="absolute inset-0" onClick={onClose} />
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="model-panel-title"
        className="relative flex max-h-[92dvh] w-full max-w-2xl flex-col overflow-hidden rounded-t-3xl border border-ink-200 bg-white shadow-xl sm:rounded-3xl"
      >
        <div className="flex items-center justify-between border-b border-ink-100 px-5 py-3">
          <div>
            <h2 id="model-panel-title" className="text-sm font-semibold text-ink-800">Endpoint & model</h2>
            {active && (
              <p className="text-[11px] text-ink-400">
                Đang dùng <span className="font-mono text-ink-600">{active.model}</span> · {active.base_url}
              </p>
            )}
          </div>
          <button onClick={onClose} className="grid h-8 w-8 place-items-center rounded-full text-ink-400 hover:bg-ink-100" aria-label="Đóng">
            <X size={16} />
          </button>
        </div>

        <div className="chat-scroll min-h-0 flex-1 space-y-4 overflow-y-auto px-5 py-4">
          {/* Endpoint tabs */}
          <div className="grid grid-cols-3 gap-2" role="tablist">
            {ENDPOINT_TABS.map((t) => {
              const ep = config?.endpoints.find((e) => e.kind === t.kind)
              return (
                <button
                  key={t.kind}
                  role="tab"
                  aria-selected={tab === t.kind}
                  onClick={() => switchTab(t.kind)}
                  className={`rounded-xl px-2 py-2 text-xs font-semibold transition ${
                    tab === t.kind ? 'bg-brand-500 text-white shadow-sm' : 'bg-ink-100 text-ink-500 hover:bg-brand-100 hover:text-brand-700'
                  }`}
                >
                  {t.label}
                  {active?.kind === t.kind && <span className="ml-1">•</span>}
                  {ep && !ep.configured && <span className="block text-[9px] font-normal opacity-80">chưa cấu hình</span>}
                </button>
              )
            })}
          </div>
          <p className="text-[11px] text-ink-400">
            {ENDPOINT_TABS.find((t) => t.kind === tab)?.hint}
            {tab !== 'custom' && config && (
              <span className="ml-1 font-mono">{config.endpoints.find((e) => e.kind === tab)?.base_url}</span>
            )}
          </p>

          {tab === 'custom' && (
            <form onSubmit={connectCustom} className="space-y-2 rounded-2xl border border-ink-200 p-3">
              <label className="block text-[11px] font-medium text-ink-500">
                Base URL
                <input
                  value={baseUrl}
                  onChange={(e) => setBaseUrl(e.target.value)}
                  placeholder="https://xxxx.ngrok-free.app/v1"
                  required
                  className="mt-1 w-full rounded-lg border border-ink-200 px-3 py-2 font-mono text-xs text-ink-800 outline-none focus:border-brand-300"
                />
              </label>
              <label className="block text-[11px] font-medium text-ink-500">
                API key / GATEWAY_TOKEN
                <input
                  type="password"
                  value={apiKey}
                  onChange={(e) => setApiKey(e.target.value)}
                  placeholder={config?.endpoints.find((e) => e.kind === 'custom')?.has_api_key ? 'đã lưu — để trống để giữ' : 'tùy chọn'}
                  autoComplete="off"
                  className="mt-1 w-full rounded-lg border border-ink-200 px-3 py-2 font-mono text-xs text-ink-800 outline-none focus:border-brand-300"
                />
              </label>
              <button
                type="submit"
                disabled={loading || !baseUrl.trim()}
                className="flex items-center gap-1.5 rounded-lg bg-brand-500 px-3 py-1.5 text-xs font-semibold text-white hover:bg-brand-600 disabled:opacity-50"
              >
                <PlugsConnected size={14} /> Kết nối
              </button>
            </form>
          )}

          {error && (
            <p className="flex items-start gap-1.5 rounded-xl bg-red-50 px-3 py-2 text-[11px] text-red-700">
              <Warning size={14} className="mt-px shrink-0" /> {error}
            </p>
          )}
          {notice && (
            <p className="flex items-center gap-1.5 rounded-xl bg-emerald-50 px-3 py-2 text-[11px] text-emerald-700">
              <CheckCircle size={14} /> {notice}
            </p>
          )}

          {/* Models */}
          <section className="space-y-2">
            <div className="flex items-center justify-between">
              <h3 className="text-[11px] font-semibold uppercase tracking-wide text-ink-400">Model trên endpoint</h3>
              {discovery && (
                <button onClick={() => discover(tab)} className="flex items-center gap-1 text-[10px] text-ink-400 hover:text-brand-700">
                  <ArrowClockwise size={11} /> Làm mới
                </button>
              )}
            </div>
            {loading && <p className="text-[11px] text-ink-400">Đang kết nối endpoint…</p>}
            {discovery && discovery.models.length === 0 && (
              <p className="text-[11px] text-ink-400">
                Endpoint chưa có model.{discovery.gateway ? ' Tải một model ở mục bên dưới.' : ''}
              </p>
            )}
            {grouped.map(([group, models]) => (
              <div key={group} className="space-y-1">
                <p className="text-[10px] font-medium text-ink-400">{group}</p>
                <div className="grid gap-1.5 sm:grid-cols-2">
                  {models.map((m) => (
                    <label
                      key={m.id}
                      className={`flex cursor-pointer items-start gap-2 rounded-xl border px-3 py-2 transition ${
                        selected === m.id ? 'border-brand-400 bg-brand-50' : 'border-ink-200 hover:border-brand-200'
                      }`}
                    >
                      <input
                        type="radio"
                        name="model"
                        value={m.id}
                        checked={selected === m.id}
                        onChange={() => setSelected(m.id)}
                        className="mt-0.5 accent-brand-600"
                      />
                      <span className="min-w-0 leading-tight">
                        <span className="block truncate font-mono text-[11px] font-semibold text-ink-700">{m.id}</span>
                        <span className="mt-0.5 flex flex-wrap gap-1 text-[9px]">
                          {m.light && <span className="rounded-full bg-emerald-100 px-1.5 text-emerald-700">nhẹ</span>}
                          {m.tools && <span className="rounded-full bg-brand-100 px-1.5 text-brand-700">tool calling</span>}
                          {active?.kind === tab && active?.model === m.id && (
                            <span className="rounded-full bg-amber-100 px-1.5 text-amber-700">đang dùng</span>
                          )}
                        </span>
                        {m.note && <span className="mt-0.5 block text-[10px] text-ink-400">{m.note}</span>}
                      </span>
                    </label>
                  ))}
                </div>
              </div>
            ))}
          </section>

          {/* Kaggle gateway: tải model */}
          {discovery?.gateway && (
            <section className="space-y-3 rounded-2xl border border-ink-200 p-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h3 className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-ink-400">
                  <HardDrives size={13} /> Kaggle Ollama gateway
                </h3>
                <span className="text-[10px] text-ink-400">
                  Ollama {discovery.gateway.ollama_version} · trống {discovery.gateway.disk_free_gb} GB
                  {discovery.gateway.gpus?.length > 0 && ` · ${discovery.gateway.gpus.length}× ${discovery.gateway.gpus[0].name}`}
                </span>
              </div>

              {jobs.filter((j) => j.state === 'running' || Date.now() / 1000 - (j.finished_at || 0) < 120).map((job) => (
                <div key={job.id} className="space-y-1 rounded-xl bg-ink-50 px-3 py-2">
                  <div className="flex items-center justify-between gap-2 text-[11px]">
                    <span className="font-mono font-semibold text-ink-700">{job.model}</span>
                    <span className={`text-[10px] ${job.state === 'error' ? 'text-red-600' : job.state === 'success' ? 'text-emerald-700' : 'text-ink-500'}`}>
                      {job.state === 'running'
                        ? `${job.percent.toFixed(1)}% · ${formatBytes(job.completed)} / ${formatBytes(job.total)} · ${formatBytes(job.speed_bps)}/s`
                        : job.state === 'error' ? `lỗi: ${job.error}` : job.state === 'success' ? 'hoàn tất' : 'đã hủy'}
                    </span>
                  </div>
                  <div
                    className="h-1.5 overflow-hidden rounded-full bg-ink-200"
                    role="progressbar"
                    aria-valuenow={Math.round(job.percent)}
                    aria-valuemin={0}
                    aria-valuemax={100}
                    aria-label={`Tiến trình tải ${job.model}`}
                  >
                    <div
                      className={`h-full rounded-full transition-[width] duration-700 ${job.state === 'error' ? 'bg-red-400' : 'bg-brand-500'}`}
                      style={{ width: `${job.state === 'success' ? 100 : job.percent}%` }}
                    />
                  </div>
                  <div className="flex items-center justify-between text-[10px] text-ink-400">
                    <span className="truncate">{job.status}</span>
                    {job.state === 'running' && (
                      <button onClick={() => cancelPull(job.id)} className="text-red-500 hover:underline">Hủy</button>
                    )}
                  </div>
                </div>
              ))}

              <div className="grid gap-1.5 sm:grid-cols-2">
                {catalog.map((m) => (
                  <div key={m.id} className="flex items-center gap-2 rounded-xl border border-ink-200 px-3 py-2">
                    <span className="min-w-0 flex-1 leading-tight">
                      <span className="block truncate font-mono text-[11px] font-semibold text-ink-700">{m.id}</span>
                      <span className="text-[10px] text-ink-400">
                        {m.size_gb} GB{m.light ? ' · nhẹ' : ''}
                      </span>
                    </span>
                    {m.installed ? (
                      <button
                        onClick={() => deleteModel(m.id)}
                        disabled={active?.model === m.id}
                        title={active?.model === m.id ? 'Đang dùng' : 'Xóa'}
                        className="grid h-7 w-7 place-items-center rounded-lg text-ink-300 hover:bg-red-50 hover:text-red-500 disabled:opacity-30"
                        aria-label={`Xóa ${m.id}`}
                      >
                        <Trash size={13} />
                      </button>
                    ) : (
                      <button
                        onClick={() => startPull(m.id)}
                        disabled={Boolean(m.pull)}
                        className="flex items-center gap-1 rounded-lg bg-brand-50 px-2 py-1 text-[10px] font-semibold text-brand-700 hover:bg-brand-100 disabled:opacity-50"
                      >
                        <CloudArrowDown size={12} /> {m.pull ? 'Đang tải' : 'Tải'}
                      </button>
                    )}
                  </div>
                ))}
              </div>

              <form
                onSubmit={(e) => {
                  e.preventDefault()
                  if (customPull.trim()) startPull(customPull.trim())
                  setCustomPull('')
                }}
                className="flex gap-2"
              >
                <input
                  value={customPull}
                  onChange={(e) => setCustomPull(e.target.value)}
                  placeholder="Tag Ollama khác, ví dụ gemma3:4b"
                  className="min-w-0 flex-1 rounded-lg border border-ink-200 px-3 py-1.5 font-mono text-[11px] outline-none focus:border-brand-300"
                />
                <button type="submit" disabled={!customPull.trim()} className="rounded-lg bg-ink-100 px-3 text-[11px] font-semibold text-ink-600 hover:bg-brand-100 disabled:opacity-50">
                  Tải
                </button>
              </form>
              {running && <p className="text-[10px] text-ink-400">Có thể đóng panel; model vẫn tải trên Kaggle.</p>}
            </section>
          )}
        </div>

        <div className="flex items-center justify-between gap-3 border-t border-ink-100 px-5 py-3">
          <p className="min-w-0 truncate text-[10px] text-ink-400">
            Đổi model áp dụng cho mọi phiên và thay đổi <span className="font-mono">target_config_hash</span>.
          </p>
          <button
            onClick={apply}
            disabled={!selected || applying || loading || isActive || !discovery}
            className="shrink-0 rounded-xl bg-brand-500 px-4 py-2 text-xs font-semibold text-white hover:bg-brand-600 disabled:opacity-40"
          >
            {applying ? 'Đang áp dụng…' : isActive ? 'Đang dùng' : 'Dùng model này'}
          </button>
        </div>
      </div>
    </div>
  )
}
