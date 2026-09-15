'use client'

import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

/**
 * Render Markdown cho bubble của assistant.
 * Tailwind typography thủ công (không dùng @tailwindcss/typography để kiểm soát
 * chính xác màu teal brand + mật độ trong khung chat).
 */
export default function MarkdownMessage({ content }) {
  return (
    <div className="md-chat">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          p: ({ children }) => <p className="mb-2 last:mb-0 leading-relaxed">{children}</p>,

          strong: ({ children }) => (
            <strong className="font-semibold text-brand-700">{children}</strong>
          ),
          em: ({ children }) => <em className="italic text-ink-600">{children}</em>,

          ul: ({ children }) => (
            <ul className="mb-2 last:mb-0 space-y-1 pl-0">{children}</ul>
          ),
          ol: ({ children }) => (
            <ol className="mb-2 last:mb-0 list-decimal space-y-1 pl-5 marker:font-medium marker:text-brand-500">
              {children}
            </ol>
          ),
          li: ({ children, ordered }) => (
            <li className={ordered ? 'pl-0.5' : 'flex gap-2 pl-0'}>
              {!ordered && (
                <span className="mt-[7px] h-1.5 w-1.5 shrink-0 rounded-full bg-brand-400" aria-hidden />
              )}
              <span className="min-w-0 flex-1">{children}</span>
            </li>
          ),

          h1: ({ children }) => (
            <h3 className="mb-1.5 mt-3 text-[15px] font-semibold tracking-tight text-ink-800 first:mt-0">{children}</h3>
          ),
          h2: ({ children }) => (
            <h3 className="mb-1.5 mt-3 text-[15px] font-semibold tracking-tight text-ink-800 first:mt-0">{children}</h3>
          ),
          h3: ({ children }) => (
            <h4 className="mb-1 mt-2.5 text-[13px] font-semibold uppercase tracking-wide text-brand-700 first:mt-0">
              {children}
            </h4>
          ),

          hr: () => <hr className="my-2.5 border-ink-100" />,

          blockquote: ({ children }) => (
            <blockquote className="mb-2 border-l-2 border-brand-300 bg-brand-50/60 py-1.5 pl-3 pr-2 text-ink-600">
              {children}
            </blockquote>
          ),

          code: ({ inline, children }) =>
            inline ? (
              <code className="rounded bg-ink-100 px-1.5 py-0.5 font-mono text-[12px] text-brand-800">{children}</code>
            ) : (
              <code className="block overflow-x-auto rounded-lg bg-ink-900 px-3 py-2 font-mono text-[12px] text-brand-100">
                {children}
              </code>
            ),
          pre: ({ children }) => <pre className="mb-2 last:mb-0">{children}</pre>,

          a: ({ href, children }) => (
            <a
              href={href}
              target="_blank"
              rel="noreferrer"
              className="font-medium text-brand-600 underline decoration-brand-300 underline-offset-2 transition hover:text-brand-700"
            >
              {children}
            </a>
          ),

          table: ({ children }) => (
            <div className="mb-2 overflow-x-auto">
              <table className="w-full border-collapse text-[12px]">{children}</table>
            </div>
          ),
          th: ({ children }) => (
            <th className="border-b border-ink-200 bg-ink-50 px-2 py-1.5 text-left font-semibold text-ink-700">
              {children}
            </th>
          ),
          td: ({ children }) => <td className="border-b border-ink-100 px-2 py-1.5 align-top">{children}</td>,
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  )
}