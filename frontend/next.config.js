/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  reactStrictMode: true,
  async rewrites() {
    // API_BASE_URL is read at RUNTIME on the server (rewrites run server-side),
    // so it can be changed without rebuilding the frontend image.
    // Default "http://backend:8000" targets the backend service on the Docker
    // Compose network. Override via env for non-compose deployments.
    const apiBase = process.env.API_BASE_URL || "http://backend:8000";
    return [
      {
        source: "/api/:path*",
        destination: `${apiBase}/api/:path*`,
      },
    ];
  },
};
module.exports = nextConfig;
