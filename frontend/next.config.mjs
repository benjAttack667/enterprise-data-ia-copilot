/** @type {import('next').NextConfig} */
const nextConfig = {
  poweredByHeader: false,
  // Produit un serveur Node minimal pour l'image Docker de production.
  output: 'standalone',
  // Robot Framework peut lancer une seconde instance sans toucher au serveur
  // de développement déjà ouvert par l'utilisateur.
  distDir: process.env.NEXT_DIST_DIR ?? '.next',
  async headers() {
    return [
      {
        source: '/:path*',
        headers: [
          { key: 'X-Content-Type-Options', value: 'nosniff' },
          { key: 'X-Frame-Options', value: 'DENY' },
          { key: 'Referrer-Policy', value: 'no-referrer' },
          {
            key: 'Permissions-Policy',
            value: 'camera=(), microphone=(), geolocation=()',
          },
          { key: 'Cross-Origin-Opener-Policy', value: 'same-origin' },
          {
            key: 'Strict-Transport-Security',
            value: 'max-age=31536000; includeSubDomains',
          },
        ],
      },
    ]
  },
}

export default nextConfig
