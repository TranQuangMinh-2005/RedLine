/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Ollama có thể mất hơn 30 giây, đặc biệt khi Agent gọi nhiều lượt tool.
  experimental: { proxyTimeout: 600000 },
  // Proxy tới backend FastAPI trong docker (target:8000 hoặc localhost:8000)
  async rewrites() {
    const api = process.env.BACKEND_URL || 'http://localhost:8000'
    return [{ source: '/api/:path*', destination: `${api}/:path*` }]
  },
}

module.exports = nextConfig
