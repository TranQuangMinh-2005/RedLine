'use client'

import { useCallback, useEffect, useState } from 'react'

/** Định nghĩa các chốt model bật/tắt runtime (độc lập profile). */
export const GUARDS = {
  promptGuard: {
    key: 'promptGuard',
    label: 'Prompt Guard',
    path: '/config/prompt-guard',
    healthKey: 'prompt_guard',
    upCommand: 'make prompt-guard-up',
    hint: 'Prompt Guard 2 — phát hiện prompt injection / jailbreak (model local)',
    // Server sống nếu test trả score số.
    reachable: (probe) => typeof probe?.score === 'number',
  },
  llamaGuard: {
    key: 'llamaGuard',
    label: 'Llama Guard',
    path: '/config/llama-guard',
    healthKey: 'llama_guard',
    upCommand: 'make llama-guard-up',
    hint: 'Llama Guard 3 — phân loại nội dung độc hại S1–S14 (model local)',
    reachable: (probe) => probe?.safe === true || probe?.safe === false,
  },
}

/**
 * Trạng thái + bật/tắt một chốt guard. status: null | 'checking' | 'ok' | 'unreachable'.
 * Khi bật (hoặc đã bật lúc tải trang) sẽ gọi thử để cảnh báo nếu server guard chưa chạy.
 */
export function useGuardToggle(apiBase, guard, { initial, onHash, onError }) {
  const [on, setOn] = useState(false)
  const [status, setStatus] = useState(null)
  const [busy, setBusy] = useState(false)

  const probe = useCallback(async () => {
    setStatus('checking')
    const result = await fetch(`${apiBase}${guard.path}/test`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: 'Xin chào' }),
    }).then((r) => r.json()).catch(() => null)
    setStatus(guard.reachable(result) ? 'ok' : 'unreachable')
  }, [apiBase, guard])

  useEffect(() => {
    if (typeof initial !== 'boolean') return
    setOn(initial)
    if (initial) probe()
  }, [initial, probe])

  const toggle = useCallback(async () => {
    if (busy) return
    setBusy(true)
    try {
      const res = await fetch(`${apiBase}${guard.path}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled: !on }),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(data?.detail || `HTTP ${res.status}`)
      setOn(Boolean(data.enabled))
      if (data.target_config_hash) onHash?.(data.target_config_hash)
      if (data.enabled) await probe()
      else setStatus(null)
    } catch (err) {
      onError?.(`Không đổi được ${guard.label}: ${err.message || 'lỗi'}`)
    } finally {
      setBusy(false)
    }
  }, [apiBase, busy, guard, on, onError, onHash, probe])

  return { on, status, busy, toggle, setOn, guard }
}

/** Nút pill trên header. */
export function GuardHeaderButton({ state, Icon }) {
  const { on, status, busy, toggle, guard } = state
  const unreachable = on && status === 'unreachable'
  return (
    <button
      type="button"
      onClick={toggle}
      disabled={busy}
      aria-pressed={on}
      title={unreachable
        ? `${guard.label} đã bật nhưng không kết nối được server — request sẽ bị chặn (fail closed). Chạy: ${guard.upCommand}`
        : `Bật/tắt ${guard.hint}`}
      className={`flex items-center gap-1.5 rounded-full border px-2.5 py-1.5 text-[11px] font-medium transition disabled:opacity-60 ${
        !on
          ? 'border-ink-200 bg-white text-ink-400 hover:border-brand-200'
          : unreachable
            ? 'border-amber-300 bg-amber-50 text-amber-700'
            : 'border-brand-300 bg-brand-50 text-brand-700'
      }`}
    >
      <Icon size={13} weight={on ? 'fill' : 'regular'} />
      <span className="hidden md:inline">{guard.label}</span>
      {busy || status === 'checking' ? '…' : on ? (unreachable ? 'lỗi' : 'bật') : 'tắt'}
    </button>
  )
}

/** Dòng công tắc trong thẻ Guardrail (cột phải). */
export function GuardSwitchRow({ state, Icon }) {
  const { on, status, busy, toggle, guard } = state
  return (
    <>
      <div className="flex items-center justify-between rounded-lg bg-ink-50 px-2 py-1.5" title={guard.hint}>
        <span className="flex items-center gap-1 text-[10px] font-semibold text-ink-600">
          <Icon size={12} className="text-brand-500" weight="duotone" /> {guard.label}
        </span>
        <button
          type="button"
          role="switch"
          aria-checked={on}
          aria-label={`Bật/tắt ${guard.label}`}
          onClick={toggle}
          disabled={busy}
          className={`relative h-4 w-7 rounded-full transition disabled:opacity-50 ${on ? 'bg-brand-500' : 'bg-ink-300'}`}
        >
          <span className={`absolute top-0.5 h-3 w-3 rounded-full bg-white shadow transition-all ${on ? 'left-3.5' : 'left-0.5'}`} />
        </button>
      </div>
      {on && status === 'unreachable' && (
        <p className="text-[9px] leading-snug text-amber-700">
          Không kết nối được server {guard.label} — request đang bị chặn. Chạy <span className="font-mono">{guard.upCommand}</span>.
        </p>
      )}
    </>
  )
}
