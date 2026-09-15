import './globals.css'

export const metadata = {
  title: 'Customer Assistant — RedLine Target',
  description: 'Giao diện chat cho Target ChatBot (Customer Assistant). RedLine capstone — VinUni x VinSOC.',
}

export default function RootLayout({ children }) {
  return (
    <html lang="vi">
      <body className="min-h-[100dvh] antialiased bg-ink-50 text-ink-800">
        {children}
      </body>
    </html>
  )
}