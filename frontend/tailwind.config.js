/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ['./src/**/*.{js,jsx,ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // Brand teal (giữ từ mascot HomeMatch P-187)
        brand: {
          50: '#F0FDFA',
          100: '#CCFBF1',
          200: '#99F6E4',
          300: '#5EEAD4',
          400: '#2DD4BF',
          500: '#14B8A6',
          600: '#0D9488',
          700: '#0F766E',
          800: '#115E59',
          900: '#134E4A',
        },
        // Neutral ấm nhẹ cho light theme (không dùng slate-xám lạnh)
        ink: {
          50: '#F8FAFA',
          100: '#F1F5F4',
          200: '#E4EAE9',
          300: '#CFD9D7',
          400: '#94A5A2',
          500: '#64748B',
          600: '#475569',
          700: '#334155',
          800: '#1E293B',
          900: '#0F172A',
        },
      },
      fontFamily: {
        sans: ['var(--font-sans)', 'system-ui', 'sans-serif'],
        mono: ['var(--font-mono)', 'ui-monospace', 'monospace'],
      },
      keyframes: {
        'bubble-in': {
          '0%': { opacity: '0', transform: 'translateY(8px) scale(0.98)' },
          '100%': { opacity: '1', transform: 'translateY(0) scale(1)' },
        },
        'dot-pulse': {
          '0%, 60%, 100%': { opacity: '0.25', transform: 'translateY(0)' },
          '30%': { opacity: '1', transform: 'translateY(-3px)' },
        },
        shimmer: {
          '100%': { transform: 'translateX(100%)' },
        },
      },
      animation: {
        'bubble-in': 'bubble-in 0.35s cubic-bezier(0.22, 1, 0.36, 1)',
        'dot-pulse': 'dot-pulse 1.2s infinite ease-in-out',
        shimmer: 'shimmer 1.8s infinite',
      },
    },
  },
  plugins: [],
}
