/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Emit a self-contained server bundle so the Docker image stays slim.
  output: "standalone",
};
export default nextConfig;
