'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import gsap from 'gsap'
import { useGSAP } from '@gsap/react'
import {
  PaperPlaneTilt,
  House,
  ArrowClockwise,
  ShieldCheck,
  Lightning,
  ChatCircleDots,
  Plus,
  Trash,
  Clock,
  Sparkle,
  Copy,
} from '@phosphor-icons/react'

import HomeMatchMascot from './_shared/HomeMatchMascot'
import MarkdownMessage from './MarkdownMessage'

gsap.registerPlugin(useGSAP)

const QUICK_REPLIES = [
  'Chính sách vận chuyển như thế nào?',
  'Trạng thái đơn hàng của tôi?',
  'Đổi trả hàng ra sao?',
  'Tạo ticket hỗ trợ',
]

const MIN_LAUNCH_MS = 900 // giữ mascot "searching" tối thiểu để thấy hiệu ứng
const STORAGE_KEY = 'redline.chat.sessions.v1'

/** Sinh id ngắn cho phiên chat (client-side). */
function newSessionId() {
  return `s-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`
}

/** Lấy tiêu đề phiên từ message đầu tiên của user. */
function deriveTitle(msgs) {
  const first = msgs.find((m) => m.role === 'user')
  if (!first) return 'Phiên trống'
  const t = first.content.replace(/\s+/g, ' ').trim()
  return t.length > 38 ? `${t.slice(0, 38)}…` : t
}

/** Format thời gian tương đối cho danh sách lịch sử. */
function timeAgo(ts) {
  const diff = Date.now() - ts
  const m = Math.floor(diff / 60000)
  if (m < 1) return 'vừa xong'
  if (m < 60) return `${m} phút`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h} giờ`
  return `${Math.floor(h / 24)} ngày`
}

export default function ChatShell({ apiBase = '/api' }) {
  // ===== Phiên hiện tại =====
  const [messages, setMessages] = useState([])
  const [serverSessionId, setServerSessionId] = useState(null)
  const [localSessionId, setLocalSessionId] = useState(() => newSessionId())

  // ===== Lịch sử các phiên (lưu localStorage) =====
  const [sessions, setSessions] = useState([])

  const [input, setInput] = useState('')
  const [mascotState, setMascotState] = useState('idle')
  const [profile, setProfile] = useState('none')
  const [profileOptions, setProfileOptions] = useState([])
  const [switching, setSwitching] = useState(false)
  const [configHash, setConfigHash] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [historyOpen, setHistoryOpen] = useState(false)

  const scrollRef = useRef(null)
  const rootRef = useRef(null)
  const firstRender = useRef(true)

  // ===== GSAP: intro nhẹ khi vào trang =====
  useGSAP(() => {
    const q = gsap.utils.selector(rootRef.current)
    if (firstRender.current) {
      firstRender.current = false
      gsap.fromTo(
        q('.intro-elem'),
        { opacity: 0, y: 12 },
        { opacity: 1, y: 0, duration: 0.5, stagger: 0.08, ease: 'power2.out' },
      )
    }
  }, { scope: rootRef })

  // ===== Nạp lịch sử từ localStorage =====
  useEffect(() => {
    try {
      const raw = localStorage.getItem(STORAGE_KEY)
      if (raw) setSessions(JSON.parse(raw))
    } catch { /* localStorage hỏng — bỏ qua, dùng state rỗng */ }
  }, [])

  const persist = useCallback((next) => {
    setSessions(next)
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(next))
    } catch { /* hết quota — bỏ qua */ }
  }, [])

  // ===== Auto-scroll =====
  useEffect(() => {
    const el = scrollRef.current
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' })
  }, [messages, busy])

  // ===== Health + config guardrail =====
  useEffect(() => {
    fetch(`${apiBase}/health`)
      .then((r) => r.json())
      .then((d) => {
        if (d.defense_profile) setProfile(d.defense_profile)
        if (d.target_config_hash) setConfigHash(d.target_config_hash)
      })
      .catch(() => { /* backend chưa lên */ })

    fetch(`${apiBase}/config/defense-profile`)
      .then((r) => r.json())
      .then((d) => {
        if (d.active) setProfile(d.active)
        if (d.target_config_hash) setConfigHash(d.target_config_hash)
        if (Array.isArray(d.options)) setProfileOptions(d.options)
      })
      .catch(() => { /* chưa có endpoint — bỏ qua */ })
  }, [apiBase])

  // ===== Đổi guardrail mode (chạy runtime, không restart container) =====
  const switchProfile = useCallback(async (name) => {
    if (switching) return
    setSwitching(true)
    try {
      const res = await fetch(`${apiBase}/config/defense-profile`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ profile: name }),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(data?.detail || `HTTP ${res.status}`)
      setProfile(data.active || name)
      if (data.capabilities) setProfileOptions([]) // reload options sau khi đổi
      const reload = await fetch(`${apiBase}/config/defense-profile`).then((r) => r.json()).catch(() => null)
      if (reload?.options) setProfileOptions(reload.options)
    } catch (err) {
      setError(`Không đổi được guardrail: ${err.message || 'lỗi'}`)
    } finally {
      setSwitching(false)
    }
  }, [apiBase, switching])

  // ===== Đồng bộ phiên hiện tại vào lịch sử =====
  const syncCurrentSession = useCallback((msgs, sid) => {
    if (msgs.length === 0) return
    const entry = {
      id: localSessionId,
      serverId: sid,
      title: deriveTitle(msgs),
      updatedAt: Date.now(),
      count: msgs.length,
      messages: msgs,
    }
    setSessions((prev) => {
      const rest = prev.filter((s) => s.id !== localSessionId)
      const next = [entry, ...rest].slice(0, 30)
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(next))
      } catch { /* bỏ qua */ }
      return next
    })
  }, [localSessionId])

  const sendMessage = useCallback(async (raw) => {
    const text = (raw ?? input).trim()
    if (!text || busy) return
    setInput('')
    setError(null)
    setBusy(true)
    setMascotState('searching')

    const userMsg = { role: 'user', content: text }
    const optimistic = [...messages, userMsg]
    setMessages(optimistic)

    const launchedAt = Date.now()
    try {
      const res = await fetch(`${apiBase}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text, session_id: serverSessionId ?? undefined }),
      })
      const data = await res.json().catch(() => ({ detail: 'Phản hồi không hợp lệ từ server' }))
      if (!res.ok) throw new Error(data?.detail || `HTTP ${res.status}`)

      // Giữ hiệu ứng searching đủ lâu để nhìn thấy
      const elapsed = Date.now() - launchedAt
      if (elapsed < MIN_LAUNCH_MS) await new Promise((r) => setTimeout(r, MIN_LAUNCH_MS - elapsed))

      setServerSessionId(data.session_id)
      if (data.defense_profile) setProfile(data.defense_profile)
      if (data.target_config_hash) setConfigHash(data.target_config_hash)
      setMascotState(data.guardrail_blocked ? 'idle' : 'success')

      const assistantMsg = {
        role: 'assistant',
        content: data.reply,
        meta: {
          model: data.model,
          latency: data.latency_s,
          tokens: data.total_tokens,
          blocked: data.guardrail_blocked,
          actions: data.guardrail_actions,
        },
      }
      const finalMsgs = [...optimistic, assistantMsg]
      setMessages(finalMsgs)
      syncCurrentSession(finalMsgs, data.session_id)
    } catch (err) {
      setError(err.message || 'Không kết nối được backend')
      setMascotState('idle')
      const failMsgs = [
        ...optimistic,
        { role: 'assistant', content: `Không gửi được tin nhắn: ${err.message || 'lỗi kết nối'}`, meta: { error: true } },
      ]
      setMessages(failMsgs)
      syncCurrentSession(failMsgs, serverSessionId)
    } finally {
      setBusy(false)
    }
  }, [input, busy, messages, serverSessionId, apiBase, syncCurrentSession])

  /** Bắt đầu phiên mới (không xoá lịch sử). */
  const startNewSession = useCallback(() => {
    setMessages([])
    setServerSessionId(null)
    setLocalSessionId(newSessionId())
    setError(null)
    setMascotState('idle')
    setHistoryOpen(false)
  }, [])

  /** Mở lại một phiên từ lịch sử. */
  const openSession = useCallback((s) => {
    setMessages(s.messages || [])
    setServerSessionId(s.serverId ?? null)
    setLocalSessionId(s.id)
    setError(null)
    setMascotState('idle')
    setHistoryOpen(false)
  }, [])

  const deleteSession = useCallback((e, id) => {
    e.stopPropagation()
    persist(sessions.filter((s) => s.id !== id))
    if (id === localSessionId) startNewSession()
  }, [sessions, persist, localSessionId, startNewSession])

  const clearAll = useCallback(() => {
    persist([])
    startNewSession()
  }, [persist, startNewSession])

  const historyList = useMemo(
    () => [...sessions].sort((a, b) => b.updatedAt - a.updatedAt),
    [sessions],
  )

  return (
    <div
      ref={rootRef}
      className="relative isolate z-10 mx-auto flex h-[100dvh] max-w-[1400px] flex-col overflow-hidden px-3 sm:px-5"
    >
      {/* ===== Header ===== */}
      <header className="intro-elem flex items-center justify-between pb-2 pt-4">
        <div className="flex items-center gap-2">
          {/* Nút mở lịch sử (mobile) */}
          <button
            onClick={() => setHistoryOpen((v) => !v)}
            className="grid h-9 w-9 place-items-center rounded-full border border-ink-200 bg-white text-ink-500 transition hover:border-brand-300 hover:text-brand-700 lg:hidden"
            aria-label="Lịch sử hội thoại"
          >
            <ChatCircleDots size={17} weight="duotone" />
          </button>

          <button
            onClick={startNewSession}
            className="group flex items-center gap-2.5 rounded-full pr-3 transition hover:opacity-90"
          >
            <span className="grid h-9 w-9 place-items-center rounded-full bg-brand-100 text-brand-700 transition group-hover:scale-105">
              <House size={18} weight="duotone" />
            </span>
            <span className="text-left leading-tight">
              <span className="block text-sm font-semibold tracking-tight text-ink-800">Customer Assistant</span>
              <span className="block text-[11px] text-ink-400">RedLine · Sandbox Target</span>
            </span>
          </button>
        </div>

        <div className="flex items-center gap-2">
          <span className="hidden items-center gap-1.5 rounded-full border border-ink-200 bg-white px-3 py-1.5 text-[11px] text-ink-400 sm:flex">
            <ShieldCheck size={13} className="text-brand-500" weight="duotone" />
            defense <span className="font-mono font-medium text-ink-600">{profile}</span>
          </span>
          <button
            onClick={startNewSession}
            className="flex items-center gap-1.5 rounded-full bg-brand-500 px-3.5 py-1.5 text-[11px] font-semibold text-white transition hover:bg-brand-600 active:scale-95"
          >
            <Plus size={13} weight="bold" />
            <span className="hidden sm:inline">Hội thoại mới</span>
            <span className="sm:hidden">Mới</span>
          </button>
        </div>
      </header>

      {/* ===== Body: 3 cột ===== */}
      <div className="flex min-h-0 flex-1 gap-3 sm:gap-5">
        {/* ---------- Cột trái: Lịch sử chat ---------- */}
        <aside
          className={`${
            historyOpen ? 'absolute inset-x-3 top-16 z-30 flex' : 'hidden'
          } max-h-[70dvh] w-auto shrink-0 flex-col overflow-hidden rounded-3xl border border-ink-200 bg-white shadow-lg lg:relative lg:inset-auto lg:z-auto lg:flex lg:max-h-none lg:w-64 lg:bg-white/70 lg:shadow-none lg:backdrop-blur-sm`}
        >
          <div className="flex items-center justify-between border-b border-ink-100 px-4 py-3">
            <span className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-ink-400">
              <Clock size={13} weight="duotone" />
              Lịch sử
            </span>
            {historyList.length > 0 && (
              <button
                onClick={clearAll}
                className="flex items-center gap-1 rounded-full px-2 py-1 text-[10px] font-medium text-ink-400 transition hover:bg-red-50 hover:text-red-600"
              >
                <Trash size={11} />
                Xoá hết
              </button>
            )}
          </div>

          <div className="chat-scroll min-h-0 flex-1 space-y-1 overflow-y-auto p-2">
            {historyList.length === 0 && (
              <p className="px-3 py-6 text-center text-[11px] leading-relaxed text-ink-300">
                Chưa có hội thoại nào.<br />Bắt đầu trò chuyện để lưu lịch sử.
              </p>
            )}

            {historyList.map((s) => {
              const active = s.id === localSessionId
              return (
                <button
                  key={s.id}
                  onClick={() => openSession(s)}
                  className={`group flex w-full items-start gap-2 rounded-2xl px-3 py-2.5 text-left transition ${
                    active
                      ? 'bg-brand-50 ring-1 ring-brand-200'
                      : 'hover:bg-ink-100'
                  }`}
                >
                  <ChatCircleDots
                    size={15}
                    weight={active ? 'fill' : 'regular'}
                    className={`mt-0.5 shrink-0 ${active ? 'text-brand-600' : 'text-ink-300'}`}
                  />
                  <span className="min-w-0 flex-1">
                    <span className={`block truncate text-[12px] font-medium ${active ? 'text-brand-800' : 'text-ink-600'}`}>
                      {s.title}
                    </span>
                    <span className="mt-0.5 flex items-center gap-1.5 text-[10px] text-ink-400">
                      <span>{timeAgo(s.updatedAt)}</span>
                      <span className="text-ink-300">·</span>
                      <span>{s.count} tin</span>
                    </span>
                  </span>
                  <span
                    role="button"
                    tabIndex={0}
                    onClick={(e) => deleteSession(e, s.id)}
                    onKeyDown={(e) => e.key === 'Enter' && deleteSession(e, s.id)}
                    className="mt-0.5 shrink-0 rounded-full p-1 text-ink-300 opacity-0 transition hover:bg-red-50 hover:text-red-500 group-hover:opacity-100"
                    aria-label="Xoá hội thoại"
                  >
                    <Trash size={12} />
                  </span>
                </button>
              )
            })}
          </div>
        </aside>

        {/* Backdrop khi mở lịch sử trên mobile */}
        {historyOpen && (
          <button
            aria-label="Đóng lịch sử"
            onClick={() => setHistoryOpen(false)}
            className="fixed inset-0 z-20 bg-ink-900/20 backdrop-blur-[2px] lg:hidden"
          />
        )}

        {/* ---------- Cột giữa: Chat ---------- */}
        <main className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden rounded-2xl border border-ink-200 bg-white shadow-[0_1px_2px_rgba(15,23,42,0.04),0_8px_24px_-8px_rgba(15,23,42,0.10)]">
          {/* Header của khung chat */}
          <div className="flex shrink-0 items-center justify-between gap-3 border-b border-ink-100 bg-gradient-to-r from-brand-50/80 via-white to-white px-3 py-2.5 sm:px-5">
            <div className="flex min-w-0 items-center gap-2.5">
              <span className="grid h-7 w-7 shrink-0 place-items-center rounded-lg bg-brand-100 text-brand-600">
                <Sparkle size={14} weight="fill" />
              </span>
              <div className="min-w-0 leading-tight">
                <p className="truncate text-[13px] font-semibold tracking-tight text-ink-800">
                  {messages.length > 0 ? deriveTitle(messages) : 'Cuộc trò chuyện mới'}
                </p>
                <p className="flex items-center gap-1.5 text-[10px] text-ink-400">
                  <span
                    className={`h-1.5 w-1.5 rounded-full ${
                      busy ? 'bg-amber-500 animate-pulse' : 'bg-emerald-500'
                    }`}
                  />
                  {busy ? 'Đang trả lời...' : 'Trực tuyến'}
                  <span className="text-ink-300">·</span>
                  <span className="font-mono">{profile}</span>
                </p>
              </div>
            </div>

            <div className="flex shrink-0 items-center gap-1">
              <button
                onClick={() => {
                  const text = messages
                    .map((m) => `${m.role === 'user' ? 'Bạn' : 'Assistant'}: ${m.content}`)
                    .join('\n\n')
                  if (text) navigator.clipboard?.writeText(text)
                }}
                title="Sao chép hội thoại"
                className="grid h-7 w-7 place-items-center rounded-lg text-ink-400 transition hover:bg-brand-50 hover:text-brand-600"
              >
                <Copy size={14} />
              </button>
            </div>
          </div>

          <div ref={scrollRef} className="chat-scroll min-h-0 flex-1 space-y-3 overflow-y-auto px-3 pb-3 pt-3 sm:px-5">
            {messages.length === 0 && (
              <div className="intro-elem flex h-full flex-col items-center justify-center gap-5">
                <div className="grid place-items-center rounded-3xl border border-ink-200 bg-white px-5 py-4 shadow-sm">
                  <HomeMatchMascot state="idle" size={116} animate={false} />
                </div>
                <div className="max-w-md text-center">
                  <h1 className="text-lg font-semibold tracking-tight text-ink-800">Xin chào! Tôi có thể giúp gì cho bạn?</h1>
                  <p className="mt-1.5 text-sm leading-relaxed text-ink-400">
                    Hỏi về vận chuyển, đổi trả, đơn hàng, tài khoản hay chính sách ShopeeFood.
                  </p>
                </div>
                <div className="grid w-full max-w-md grid-cols-1 gap-2 sm:grid-cols-2">
                  {QUICK_REPLIES.map((q) => (
                    <button
                      key={q}
                      onClick={() => sendMessage(q)}
                      disabled={busy}
                      className="rounded-2xl border border-ink-200 bg-white px-3.5 py-2.5 text-left text-xs font-medium text-ink-600 shadow-sm transition duration-300 hover:-translate-y-0.5 hover:border-brand-300 hover:text-brand-700 disabled:opacity-50"
                    >
                      {q}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {messages.map((m, i) => (
              <div key={i} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'} animate-bubble-in`}>
                {m.role === 'assistant' && (
                  <div className="mr-2 mt-1 hidden shrink-0 sm:block">
                    <HomeMatchMascot state="idle" size={34} animate={false} />
                  </div>
                )}
                <div
                  className={`max-w-[90%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed shadow-sm sm:max-w-[85%]
                    ${m.role === 'user'
                      ? 'rounded-br-md bg-brand-500 text-white'
                      : m.meta?.error
                        ? 'rounded-bl-md border border-red-200 bg-red-50 text-red-700'
                        : 'rounded-bl-md border border-ink-200 bg-white text-ink-700'}`}
                >
                  {m.role === 'assistant' && !m.meta?.error ? (
                    <MarkdownMessage content={m.content} />
                  ) : (
                    <div className="whitespace-pre-wrap">{m.content}</div>
                  )}
                  {m.meta && !m.meta.error && (
                    <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 border-t border-ink-100 pt-1.5 text-[10px] text-ink-400">
                      <span className="font-mono">{m.meta.model}</span>
                      <span className="font-mono">{m.meta.tokens} tok</span>
                      <span className="font-mono">{Number(m.meta.latency).toFixed(1)}s</span>
                      {m.meta.blocked && (
                        <span className="inline-flex items-center gap-1 rounded-full bg-amber-100 px-2 py-0.5 font-medium text-amber-700">
                          <ShieldCheck size={10} /> chặn: {m.meta.actions?.join(', ')}
                        </span>
                      )}
                    </div>
                  )}
                </div>
              </div>
            ))}

            {busy && (
              <div className="flex items-end justify-start animate-bubble-in">
                <div className="mr-2 hidden shrink-0 sm:block">
                  <HomeMatchMascot state="searching" size={34} />
                </div>
                <div className="rounded-2xl rounded-bl-md border border-ink-200 bg-white px-4 py-3 shadow-sm">
                  <div className="flex items-center gap-1.5">
                    <span className="h-1.5 w-1.5 rounded-full bg-brand-400 animate-dot-pulse" />
                    <span className="h-1.5 w-1.5 rounded-full bg-brand-400 animate-dot-pulse [animation-delay:0.15s]" />
                    <span className="h-1.5 w-1.5 rounded-full bg-brand-400 animate-dot-pulse [animation-delay:0.3s]" />
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Input */}
          <div className="border-t border-ink-100 bg-ink-50/60 px-3 py-3 sm:px-5">
            <form
              onSubmit={(e) => {
                e.preventDefault()
                sendMessage()
              }}
              className="flex items-center gap-2 rounded-xl border border-ink-200 bg-white p-1.5 pl-4 shadow-sm transition focus-within:border-brand-300 focus-within:shadow-md"
            >
              <input
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder={busy ? 'Customer Assistant đang xử lý...' : 'Nhập tin nhắn...'}
                disabled={busy}
                className="min-w-0 flex-1 bg-transparent text-sm text-ink-800 outline-none placeholder:text-ink-400 disabled:opacity-60"
              />
              <button
                type="submit"
                disabled={busy || !input.trim()}
                className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-brand-500 text-white transition duration-200 hover:bg-brand-600 active:scale-95 disabled:opacity-40"
                aria-label="Gửi"
              >
                <PaperPlaneTilt size={16} weight="bold" />
              </button>
            </form>
            {error && <p className="mt-1.5 text-[11px] text-red-600">{error}</p>}
          </div>
        </main>

        {/* ---------- Cột phải: Mascot + trạng thái ---------- */}
        <aside className="hidden w-56 shrink-0 flex-col items-center justify-center rounded-3xl border border-ink-200 bg-white/70 backdrop-blur-sm xl:flex">
          <div className="flex w-full flex-col items-center gap-4 px-4 text-center">
            {/* Mascot trần, KHÔNG speech bubble — giữ đúng tỉ lệ SVG */}
            <div className="grid h-[168px] w-[168px] place-items-center">
              <HomeMatchMascot state={mascotState} size={160} />
            </div>

            <div className="space-y-1.5">
              <span
                className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-[11px] font-semibold transition-colors ${
                  mascotState === 'searching'
                    ? 'bg-amber-100 text-amber-700'
                    : mascotState === 'success'
                      ? 'bg-emerald-100 text-emerald-700'
                      : 'bg-brand-50 text-brand-700'
                }`}
              >
                <span
                  className={`h-1.5 w-1.5 rounded-full ${
                    mascotState === 'searching' ? 'bg-amber-500' : mascotState === 'success' ? 'bg-emerald-500' : 'bg-brand-500'
                  }`}
                />
                {mascotState === 'searching' ? 'Đang tìm kiếm' : mascotState === 'success' ? 'Đã trả lời' : 'Sẵn sàng'}
              </span>

              <p className="min-h-[32px] px-1 text-[11px] leading-relaxed text-ink-400">
                {mascotState === 'searching'
                  ? 'Assistant đang tra cứu tài liệu và gọi model...'
                  : mascotState === 'success'
                    ? 'Đã tìm thấy câu trả lời phù hợp.'
                    : 'Hỏi tôi về chính sách, đơn hàng hoặc tài khoản.'}
              </p>

              {configHash && <p className="font-mono text-[10px] text-ink-300">cfg {configHash.slice(0, 12)}</p>}
            </div>

            {/* ===== Guardrail mode switcher ===== */}
            <div className="w-full space-y-2 rounded-2xl border border-ink-200 bg-white/80 p-3">
              <div className="flex items-center justify-between">
                <span className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wide text-ink-400">
                  <ShieldCheck size={12} className="text-brand-500" weight="duotone" />
                  Guardrail
                </span>
                <span
                  className={`rounded-full px-2 py-0.5 font-mono text-[10px] font-semibold ${
                    profile === 'strict'
                      ? 'bg-emerald-100 text-emerald-700'
                      : profile === 'basic'
                        ? 'bg-amber-100 text-amber-700'
                        : 'bg-ink-100 text-ink-500'
                  }`}
                >
                  {profile}
                </span>
              </div>

              <div className="grid grid-cols-3 gap-1">
                {['none', 'basic', 'strict'].map((name) => {
                  const cap = profileOptions.find((o) => o.name === name)
                  const active = profile === name
                  return (
                    <button
                      key={name}
                      onClick={() => switchProfile(name)}
                      disabled={switching}
                      title={
                        cap
                          ? `input:${cap.input_filter ? 'ON' : 'off'} · output:${cap.output_filter ? 'ON' : 'off'}`
                          : name
                      }
                      className={`rounded-lg px-1 py-1.5 text-[10px] font-medium transition duration-200 active:scale-95 disabled:opacity-50 ${
                        active
                          ? 'bg-brand-500 text-white shadow-sm'
                          : 'bg-ink-100 text-ink-500 hover:bg-brand-100 hover:text-brand-700'
                      }`}
                    >
                      {name}
                    </button>
                  )
                })}
              </div>

              <p className="text-[9px] leading-snug text-ink-400">
                {profile === 'strict'
                  ? 'Chặn input + lọc output + canary check'
                  : profile === 'basic'
                    ? 'Chặn input + canary check'
                    : 'Không phòng thủ — đo lỗ hổng nguyên bản'}
              </p>
            </div>

            <div className="flex items-center gap-1.5 rounded-full bg-brand-50 px-3 py-1 text-[10px] font-medium text-brand-700">
              <Lightning size={11} weight="fill" />
              GSAP motion
            </div>
          </div>
        </aside>
      </div>
    </div>
  )
}