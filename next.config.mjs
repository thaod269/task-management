/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,

  // The whole app is client-side (no server components fetching data, no route
  // handlers, no middleware), so `next build` can emit a plain static site into
  // `out/` for Firebase Hosting.
  output: "export",

  // Static export has no image optimisation server. Harmless today since the
  // app uses no <Image>, but it keeps the build working if one is added.
  images: { unoptimized: true },
};

export default nextConfig;
