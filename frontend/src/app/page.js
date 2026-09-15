import ChatShell from './components/ChatShell'

export default function Page() {
  return (
    <main className="grain relative min-h-[100dvh] w-full max-w-full overflow-x-hidden">
      <ChatShell apiBase="/api" />
    </main>
  )
}