/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // The API_BASE_URL env var is read at build time via NEXT_PUBLIC_API_URL.
  // See lib/api.ts for the runtime read.
  experimental: {
    typedRoutes: false,
  },
};

export default nextConfig;
