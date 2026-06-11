/** @type {import('next').NextConfig} */
const nextConfig = {
  // static export — FastAPI serves web/out at / (same origin, no CORS)
  output: "export",
  images: { unoptimized: true },
  // dev-only proxy so `next dev` can hit the local FastAPI; ignored by export
  async rewrites() {
    return [
      { source: "/api/:path*", destination: "http://localhost:8000/api/:path*" },
    ];
  },
};

export default nextConfig;
