/**
 * /api/ticket — Verifica la sesión de Privy (server-side), valida que el email
 * sea el autorizado y emite un ticket HMAC de corta vida para auto-login en el panel.
 */
import { PrivyClient } from '@privy-io/server-auth';
import crypto from 'crypto';

const privy = new PrivyClient(process.env.PRIVY_APP_ID, process.env.PRIVY_APP_SECRET);
const TICKET_SECRET = process.env.PRIVY_TICKET_SECRET;
const ALLOWED_EMAIL = process.env.PRIVY_ALLOWED_EMAIL;
const GIST_RAW = 'https://gist.githubusercontent.com/DevCristobalvc/21a187027af69a8d8f4c5e19079e8d62/raw/panel_url.txt';

export default async function handler(req, res) {
  try {
    const token = req.query.token;
    if (!token) return res.status(400).json({ error: 'missing token' });
    if (!ALLOWED_EMAIL) return res.status(500).json({ error: 'PRIVY_ALLOWED_EMAIL no configurado' });

    const claims = await privy.verifyAuthToken(token);
    const user = await privy.getUser(claims.userId);
    const email = (user.email && user.email.address) || null;

    if (email !== ALLOWED_EMAIL) {
      return res.status(403).json({ error: 'not authorized', email });
    }

    const exp = Date.now() + 5 * 60 * 1000;
    const ticket = crypto
      .createHmac('sha256', TICKET_SECRET)
      .update(`${email}:${exp}`)
      .digest('hex');

    let panel = '';
    try {
      const r = await fetch(GIST_RAW, { signal: AbortSignal.timeout(5000) });
      const u = (await r.text()).trim();
      if (u.startsWith('https://')) panel = u;
    } catch (_) {}

    res.json({ ticket, email, exp, panel });
  } catch (e) {
    res.status(401).json({ error: e.message || 'invalid token' });
  }
}
