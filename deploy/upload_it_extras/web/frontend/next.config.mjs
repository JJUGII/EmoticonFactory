/** @type {import('next').NextConfig} */
function backendOrigin() {
  const raw =
    process.env.API_URL?.trim() ||
    process.env.NEXT_PUBLIC_API_URL?.trim() ||
    "";
  return raw.replace(/\/$/, "");
}

function apiHostPattern() {
  const backend = backendOrigin();
  const raw = backend || "http://localhost:8000";
  try {
    const u = new URL(raw);
    return {
      protocol: u.protocol.replace(":", ""),
      hostname: u.hostname,
      ...(u.port ? { port: u.port } : {}),
    };
  } catch {
    return { protocol: "http", hostname: "localhost", port: "8000" };
  }
}

const api = apiHostPattern();

const nextConfig = {
  async rewrites() {
    const backend = backendOrigin();
    if (!backend) return [];
    return [
      {
        source: "/api/:path*",
        destination: `${backend}/api/:path*`,
      },
    ];
  },
  images: {
    remotePatterns: [
      { protocol: "http", hostname: "localhost", port: "8000" },
      { protocol: "http", hostname: "127.0.0.1", port: "8000" },
      { protocol: api.protocol, hostname: api.hostname, ...(api.port ? { port: api.port } : {}) },
    ],
  },
};

export default nextConfig;
