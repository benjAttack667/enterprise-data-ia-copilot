/** @type {import('next').NextConfig} */
const nextConfig = {
  // Produit un serveur Node minimal pour l'image Docker de production.
  output: 'standalone',
  // Robot Framework peut lancer une seconde instance sans toucher au serveur
  // de développement déjà ouvert par l'utilisateur.
  distDir: process.env.NEXT_DIST_DIR ?? '.next',
}

export default nextConfig
