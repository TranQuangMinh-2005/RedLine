// PORTED FROM: P-187 (HomeMatch AI Agent) frontend/src/app/components/_shared/HomeMatchMascot.js
// Asset gốc thuộc project HomeMatch (P-187). Tái sử dụng cho RedLine capstone target UI.
// Nếu cần chỉnh sửa, ưu tiên đồng bộ ngược lại P-187.

'use client'

// HomeMatchMascot — mascot robot-ngôi-nhà chính thức của HomeMatch (port từ
// mascot-homematch-agent.html), animation thuần GSAP 3:
//   - idle:     bồng bềnh + chớp mắt (dùng làm LOGO / trạng thái chờ)
//   - searching: sóng sonar radar quét + đầu nghiêng + dấu "?" (dùng khi ĐANG CHỜ
//                chatbot phản hồi — hiệu ứng tìm kiếm)
//   - success:  nhảy cẫng ăn mừng + mắt cười ^ ^ + tay giơ cao + lấp lánh
//                (dùng khi reccomendation HIỆN RA)
// GSAP là chuẩn animation của frontend HomeMatch từ đây về sau.

import { useEffect, useRef, useId } from 'react'
import gsap from 'gsap'

const STATE_TEXT = {
  idle: { status: 'Trợ Lý BĐS', text: 'Sẵn sàng tìm kiếm không gian sống lý tưởng!', border: 'rgba(20,184,166,0.45)', badge: '#0F766E' },
  searching: { status: 'Đang tìm kiếm...', text: 'Bạn chờ xíu nha, HomeMatch đang tìm căn phù hợp nhất cho bạn', border: 'rgba(245,158,11,0.55)', badge: '#f59e0b' },
  success: { status: 'Tìm kiếm thành công!', text: 'Đã tìm thấy căn BĐS phù hợp với bạn! ✨', border: 'rgba(52,211,153,0.8)', badge: '#10b981' },
}

export default function HomeMatchMascot({ state = 'idle', size = 110, speech = null, celebrateKey = 0, speechHeader = true, animate = true }) {
  const rootRef = useRef(null)
  const uid = useId().replace(/[^a-zA-Z0-9]/g, '')

  useEffect(() => {
    const root = rootRef.current
    if (!root) return
    const q = gsap.utils.selector(root)
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches

    const ctx = gsap.context(() => {
      // ===== Nền tảng (luôn chạy): bồng bềnh + bóng + chớp mắt =====
      // animate=false → bản TĨNH (ChatbotWidget dùng cho avatar mini, tránh nhiều
      // mascot nhảy cùng lúc; advisor giữ nguyên animate=true mặc định).
      if (!reduced && animate) {
        gsap.to(q('#mascotBodyGroup'), { y: -10, duration: 2.2, repeat: -1, yoyo: true, ease: 'power1.inOut' })
        gsap.to(q('#mascotShadow'), { scaleX: 0.8, opacity: 0.1, duration: 2.2, repeat: -1, yoyo: true, ease: 'power1.inOut', transformOrigin: 'center center' })
        const blink = () => {
          gsap.timeline({ onComplete: () => gsap.delayedCall(gsap.utils.random(3, 6), blink) })
            .to(q('#eyesNeutral .bot-eye'), { scaleY: 0.1, duration: 0.08, transformOrigin: 'center center' })
            .to(q('#eyesNeutral .bot-eye'), { scaleY: 1, duration: 0.08 })
        }
        blink()
      }

      // ===== Timeline sóng sonar (paused, chỉ chạy khi searching) =====
      const sonar = gsap.timeline({ repeat: -1, paused: true })
      sonar
        .fromTo(q('#sonarRing1'), { r: 50, opacity: 0.65 }, { r: 155, opacity: 0, duration: 2.4, ease: 'power1.out' }, 0)
        .fromTo(q('#sonarRing2'), { r: 50, opacity: 0.5 }, { r: 135, opacity: 0, duration: 2.4, ease: 'power1.out' }, 0.7)
        .fromTo(q('#sonarRing3'), { r: 50, opacity: 0.4 }, { r: 115, opacity: 0, duration: 2.4, ease: 'power1.out' }, 1.4)

      const setStatic = (st) => {
        gsap.set(q('#sonarWaveGroup'), { opacity: st === 'searching' ? 1 : 0 })
        gsap.set(q('#eyesNeutral'), { opacity: st === 'idle' ? 1 : 0 })
        gsap.set(q('#mouthNeutral'), { opacity: st === 'idle' ? 1 : 0 })
        gsap.set(q('#eyesCuteConfused'), { opacity: st === 'searching' ? 1 : 0 })
        gsap.set(q('#mouthCuteConfused'), { opacity: st === 'searching' ? 1 : 0 })
        gsap.set(q('#eyesHappy'), { opacity: st === 'success' ? 1 : 0 })
        gsap.set(q('#mouthHappy'), { opacity: st === 'success' ? 1 : 0 })
      }

      const searchingState = () => {
        gsap.to(q('#sonarWaveGroup'), { opacity: 1, duration: 0.4 })
        sonar.play()
        // Chuyển động nghiêng trái rồi nghiêng phải liên tục (sway animation)
        gsap.fromTo(q('#mascotBodyGroup'),
          { rotation: -9, transformOrigin: 'center bottom' },
          { rotation: 9, duration: 0.9, repeat: -1, yoyo: true, ease: 'sine.inOut', transformOrigin: 'center bottom' }
        )
        gsap.fromTo(q('#handLeft'),
          { cx: 64, cy: 165 },
          { cx: 80, cy: 148, duration: 0.9, repeat: -1, yoyo: true, ease: 'sine.inOut' }
        )
        gsap.fromTo(q('#handRight'),
          { cx: 228, cy: 168 },
          { cx: 206, cy: 154, duration: 0.9, repeat: -1, yoyo: true, ease: 'sine.inOut' }
        )
        gsap.to(q('#cuteBlush'), { opacity: 1, duration: 0.3 })
        gsap.to([q('#eyesNeutral'), q('#eyesHappy'), q('#mouthNeutral'), q('#mouthHappy'), q('#successSparkles')], { opacity: 0, duration: 0.2 })
        gsap.to([q('#eyesCuteConfused'), q('#mouthCuteConfused')], { opacity: 1, duration: 0.2 })
        gsap.to(q('#antennaOrb'), { fill: '#f59e0b', duration: 0.3 })
        gsap.to(q('#cuteQuestionBubble'), { opacity: 1, y: -2, duration: 0.3 })
        gsap.to(q('#cuteQuestionBubble'), { y: -8, duration: 0.8, repeat: -1, yoyo: true, ease: 'sine.inOut' })
      }

      const successState = () => {
        gsap.to(q('#sonarWaveGroup'), { opacity: 0, duration: 0.4, onComplete: () => sonar.pause() })
        gsap.killTweensOf([q('#mascotBodyGroup'), q('#cuteQuestionBubble'), q('#handLeft'), q('#handRight')])
        gsap.to(q('#cuteQuestionBubble'), { opacity: 0, duration: 0.2 })
        gsap.timeline()
          .to(q('#mascotBodyGroup'), { y: -26, rotation: 0, duration: 0.22, ease: 'power2.out' })
          .to(q('#mascotBodyGroup'), { y: 0, duration: 0.4, ease: 'bounce.out' })
        gsap.to([q('#eyesNeutral'), q('#eyesCuteConfused'), q('#mouthNeutral'), q('#mouthCuteConfused')], { opacity: 0, duration: 0.2 })
        gsap.to([q('#eyesHappy'), q('#mouthHappy')], { opacity: 1, duration: 0.2 })
        gsap.to(q('#cuteBlush'), { opacity: 0.6, duration: 0.3 })
        gsap.to(q('#antennaOrb'), { fill: '#10b981', duration: 0.3 })
        gsap.to(q('#chestBadge'), { fill: '#10b981', duration: 0.3 })
        gsap.to(q('#handLeft'), { cx: 48, cy: 128, duration: 0.3 })
        gsap.to(q('#handRight'), { cx: 232, cy: 128, duration: 0.3 })
        gsap.to([q('#handLeft'), q('#handRight')], { y: -5, duration: 0.35, repeat: -1, yoyo: true, ease: 'sine.inOut' })
        gsap.fromTo(q('#successSparkles'), { opacity: 0, scale: 0.6, transformOrigin: 'center center' }, { opacity: 1, scale: 1.1, duration: 0.35 })
        gsap.to(q('.sparkle'), { rotation: 45, duration: 1.2, repeat: -1, yoyo: true, ease: 'sine.inOut', transformOrigin: 'center center' })

        // Confetti bùng nổ từ tâm (một lần, đúng lúc reccomendation hiện ra)
        const pieces = q('.confetti-piece')
        pieces.forEach((p, idx) => {
          const angle = (idx / pieces.length) * Math.PI * 2 + gsap.utils.random(-0.2, 0.2)
          const dist = gsap.utils.random(70, 135)
          gsap.fromTo(p,
            { x: 0, y: 0, rotation: 0, opacity: 1, scale: 1 },
            {
              x: Math.cos(angle) * dist,
              y: Math.sin(angle) * dist,
              rotation: gsap.utils.random(-200, 200),
              opacity: 0,
              scale: gsap.utils.random(0.7, 1.3),
              duration: gsap.utils.random(0.9, 1.4),
              ease: 'power2.out',
              delay: 0.12 + idx * 0.02,
              transformOrigin: 'center center',
            })
        })
      }

      const idleState = () => {
        sonar.pause()
        gsap.to(q('#sonarWaveGroup'), { opacity: 0, duration: 0.3 })
        gsap.killTweensOf([q('#mascotBodyGroup'), q('#cuteQuestionBubble'), q('#handLeft'), q('#handRight'), q('.sparkle'), q('.confetti-piece')])
        gsap.set(q('.confetti-piece'), { opacity: 0 })
        gsap.to(q('#mascotBodyGroup'), { rotation: 0, y: 0, duration: 0.4 })
        gsap.to(q('#handLeft'), { cx: 56, cy: 160, y: 0, duration: 0.4 })
        gsap.to(q('#handRight'), { cx: 224, cy: 160, y: 0, duration: 0.4 })
        gsap.to(q('#antennaOrb'), { fill: '#14B8A6', duration: 0.3 })
        gsap.to(q('#chestBadge'), { fill: '#0F766E', duration: 0.3 })
        gsap.to([q('#eyesCuteConfused'), q('#eyesHappy'), q('#cuteQuestionBubble'), q('#successSparkles'), q('#mouthCuteConfused'), q('#mouthHappy'), q('#cuteBlush')], { opacity: 0, duration: 0.2 })
        gsap.to([q('#eyesNeutral'), q('#mouthNeutral')], { opacity: 1, duration: 0.2 })
      }

      if (reduced || !animate) {
        setStatic(state)
      } else if (state === 'searching') {
        searchingState()
      } else if (state === 'success') {
        successState()
      } else {
        idleState()
      }
    }, root)

    return () => ctx.revert()
  }, [state, celebrateKey])

  const bubble = STATE_TEXT[state] || STATE_TEXT.idle

  // Khi có bong bóng -> wrapper đủ rộng để bong bóng KHÔNG tràn ra ngoài mascot
  const wrapperWidth = speech !== null ? Math.max(size, 208) : size

  return (
    <div ref={rootRef} style={{ position: 'relative', width: wrapperWidth, display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
      <style jsx>{`
        .hm-mascot-bubble {
          position: relative;
          background: rgba(255, 255, 255, 0.97);
          border-radius: 14px;
          padding: 7px 14px;
          margin-bottom: 2px;
          z-index: 10;
          width: 208px;
          text-align: center;
          box-shadow: 0 6px 18px -6px rgba(15, 118, 110, 0.18);
        }
        .hm-mascot-bubble::after {
          content: '';
          position: absolute;
          bottom: -6px;
          left: 50%;
          transform: translateX(-50%);
          border-width: 6px 6px 0;
          border-style: solid;
          border-color: rgba(255, 255, 255, 0.97) transparent transparent transparent;
        }
      `}</style>
      {speech !== null && (
        <div className="hm-mascot-bubble" style={{ border: `1.5px solid ${bubble.border}` }}>
          {speechHeader && (
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 5, fontSize: 10, fontWeight: 700, color: '#0F766E', letterSpacing: 0.4, textTransform: 'uppercase' }}>
              <span style={{ background: bubble.badge, color: '#fff', padding: '1px 7px', borderRadius: 6, fontSize: 8.5 }}>HomeMatch Agent</span>
              <span>{bubble.status}</span>
            </div>
          )}
          <div style={{ fontSize: speechHeader ? 13 : 14, fontWeight: 600, color: '#0f172a', marginTop: speechHeader ? 2 : 0, lineHeight: 1.4 }}>{speech || bubble.text}</div>
        </div>
      )}

      <svg viewBox="0 0 280 280" xmlns="http://www.w3.org/2000/svg"
        style={{ width: '100%', height: 'auto', overflow: 'visible', display: 'block', filter: 'drop-shadow(0 8px 14px rgba(37,99,235,0.18))' }}>
        <defs>
          <linearGradient id={`${uid}roofGrad`} x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#14B8A6" />
            <stop offset="100%" stopColor="#0F766E" />
          </linearGradient>
          <linearGradient id={`${uid}bodyGrad`} x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#ffffff" />
            <stop offset="100%" stopColor="#99F6E4" />
          </linearGradient>
          <linearGradient id={`${uid}goldBadge`} x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#fbbf24" />
            <stop offset="100%" stopColor="#d97706" />
          </linearGradient>
          <filter id={`${uid}softGlow`} x="-20%" y="-20%" width="140%" height="140%">
            <feGaussianBlur stdDeviation="2.5" result="blur" />
            <feComposite in="SourceGraphic" in2="blur" operator="over" />
          </filter>
          <filter id={`${uid}sonarGlow`} x="-30%" y="-30%" width="160%" height="160%">
            <feGaussianBlur stdDeviation="2" result="blur" />
            <feComposite in="SourceGraphic" in2="blur" operator="over" />
          </filter>
        </defs>

        {/* 1. Vòng sóng sonar/radar (hiệu ứng tìm kiếm) */}
        <g id="sonarWaveGroup" opacity="0">
          <circle id="sonarRing1" cx="140" cy="150" r="45" fill="none" stroke="#14B8A6" strokeWidth="1.4" opacity="0" filter={`url(#${uid}sonarGlow)`} />
          <circle id="sonarRing2" cx="140" cy="150" r="45" fill="none" stroke="#0D9488" strokeWidth="1.2" opacity="0" />
          <circle id="sonarRing3" cx="140" cy="150" r="45" fill="none" stroke="#99F6E4" strokeWidth="1" opacity="0" />
        </g>

        {/* Bóng tiếp đất */}
        <ellipse id="mascotShadow" cx="140" cy="256" rx="54" ry="9" fill="rgba(37,99,235,0.18)" />

        {/* 2. Khung thân mascot */}
        <g id="mascotBodyGroup" style={{ transformOrigin: '140px 180px' }}>

          {/* Dấu hỏi dễ thương */}
          <g id="cuteQuestionBubble" transform="translate(198, 48)" opacity="0">
            <circle cx="0" cy="0" r="13" fill={`url(#${uid}goldBadge)`} filter={`url(#${uid}softGlow)`} />
            <text x="0" y="4.5" fontSize="14" fontWeight="900" fill="#ffffff" textAnchor="middle" fontFamily="system-ui, sans-serif">?</text>
          </g>

          {/* Sparkles ăn mừng khi tìm thấy */}
          <g id="successSparkles" opacity="0">
            <path className="sparkle" d="M 62,72 Q 62,80 54,80 Q 62,80 62,88 Q 62,80 70,80 Q 62,80 62,72 Z" fill="#fbbf24" filter={`url(#${uid}softGlow)`} />
            <path className="sparkle" d="M 218,68 Q 218,74 212,74 Q 218,74 218,80 Q 218,74 224,74 Q 218,74 218,68 Z" fill="#14B8A6" />
            <path className="sparkle" d="M 226,170 Q 226,175 221,175 Q 226,175 226,180 Q 226,175 231,175 Q 226,175 226,170 Z" fill="#34d399" />
          </g>

          {/* Ăng-ten */}
          <g id="antennaGroup">
            <line x1="140" y1="72" x2="140" y2="50" stroke="#99F6E4" strokeWidth="3.5" strokeLinecap="round" />
            <circle id="antennaOrb" cx="140" cy="46" r="7.5" fill="#14B8A6" filter={`url(#${uid}softGlow)`} />
          </g>

          {/* Mái nhà BĐS */}
          <path d="M 62 112 L 140 54 L 218 112 Z" fill={`url(#${uid}roofGrad)`} />
          <g transform="translate(133, 76)" fill="#ffffff" opacity="0.9">
            <rect x="0" y="0" width="5.5" height="5.5" rx="1" />
            <rect x="7.5" y="0" width="5.5" height="5.5" rx="1" />
            <rect x="0" y="7.5" width="5.5" height="5.5" rx="1" />
            <rect x="7.5" y="7.5" width="5.5" height="5.5" rx="1" />
          </g>

          {/* Thân mascot */}
          <rect x="74" y="108" width="132" height="106" rx="28" fill={`url(#${uid}bodyGrad)`} stroke="#99F6E4" strokeWidth="2" />

          {/* Mặt kính visor */}
          <rect x="88" y="120" width="104" height="60" rx="18" fill="#0f172a" stroke="#14B8A6" strokeWidth="1.5" />

          {/* Má hồng chibi */}
          <g id="cuteBlush" opacity="0">
            <ellipse cx="102" cy="160" rx="6.5" ry="3.5" fill="#f43f5e" opacity="0.45" />
            <ellipse cx="178" cy="160" rx="6.5" ry="3.5" fill="#f43f5e" opacity="0.45" />
          </g>

          {/* Mắt: neutral */}
          <g id="eyesNeutral">
            <rect className="bot-eye" x="107" y="135" width="15" height="23" rx="7.5" fill="#14B8A6" filter={`url(#${uid}softGlow)`} />
            <rect className="bot-eye" x="158" y="135" width="15" height="23" rx="7.5" fill="#14B8A6" filter={`url(#${uid}softGlow)`} />
          </g>

          {/* Mắt: tò mò long lanh (searching) */}
          <g id="eyesCuteConfused" opacity="0">
            <g transform="translate(114, 145)">
              <ellipse cx="0" cy="0" rx="10" ry="11" fill="#14B8A6" filter={`url(#${uid}softGlow)`} />
              <ellipse cx="-2.5" cy="-3.5" rx="3.5" ry="4" fill="#ffffff" />
              <circle cx="3" cy="3" r="1.8" fill="#ffffff" />
            </g>
            <g transform="translate(166, 145)">
              <ellipse cx="0" cy="0" rx="9" ry="10" fill="#14B8A6" filter={`url(#${uid}softGlow)`} />
              <ellipse cx="-2" cy="-3" rx="3" ry="3.5" fill="#ffffff" />
              <circle cx="2.5" cy="2.5" r="1.5" fill="#ffffff" />
            </g>
          </g>

          {/* Mắt: cười tươi ^ ^ (success) */}
          <g id="eyesHappy" opacity="0">
            <path d="M 104 150 Q 115 134 126 150" stroke="#34d399" strokeWidth="4" strokeLinecap="round" fill="none" filter={`url(#${uid}softGlow)`} />
            <path d="M 154 150 Q 165 134 176 150" stroke="#34d399" strokeWidth="4" strokeLinecap="round" fill="none" filter={`url(#${uid}softGlow)`} />
          </g>

          {/* Miệng neutral */}
          <path id="mouthNeutral" d="M 130 164 Q 140 171 150 164" stroke="#14B8A6" strokeWidth="2.5" strokeLinecap="round" fill="none" />

          {/* Miệng chúm chím 'o' (searching) */}
          <ellipse id="mouthCuteConfused" cx="140" cy="165" rx="3.5" ry="4.5" fill="#14B8A6" opacity="0" filter={`url(#${uid}softGlow)`} />

          {/* Miệng cười rạng rỡ (success) */}
          <path id="mouthHappy" d="M 128 162 Q 140 176 152 162 Z" fill="#34d399" opacity="0" filter={`url(#${uid}softGlow)`} />

          {/* Huy hiệu ngực */}
          <circle id="chestBadge" cx="140" cy="195" r="12" fill="#0F766E" />
          <path d="M 134 198 L 140 191 L 146 198 L 144 198 L 144 202 L 136 202 L 136 198 Z" fill="#ffffff" />

          {/* Hai tay */}
          <circle id="handLeft" cx="56" cy="160" r="12" fill="#0D9488" />
          <circle id="handRight" cx="224" cy="160" r="12" fill="#0D9488" />
        </g>

        {/* 3. Confetti bùng nổ ăn mừng khi có kết quả (GSAP phóng từ tâm) */}
        <g id="confettiBurst">
          {['#10b981', '#34d399', '#fbbf24', '#14B8A6', '#f472b6', '#0F766E', '#0D9488'].flatMap((color, ci) =>
            [0, 1].map(k => (
              <rect key={`${ci}-${k}`} className="confetti-piece" x="136" y="146"
                width={9 - (ci % 3) * 2} height={9 - (ci % 3) * 2} rx="1.5" opacity="0"
                fill={color} style={{ transformOrigin: '140px 150px' }} />
            ))
          )}
        </g>
      </svg>
    </div>
  )
}
