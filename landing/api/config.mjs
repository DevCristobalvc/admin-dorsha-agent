/**
 * /api/config — expone config pública (email autorizado) para la landing.
 * No expone secretos.
 */
export default function handler(req, res) {
  res.setHeader('Cache-Control', 'no-store');
  res.json({
    email: process.env.PRIVY_ALLOWED_EMAIL || null
  });
}
