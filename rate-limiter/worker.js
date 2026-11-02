const encoder = new TextEncoder();
async function digest(value) { return new Uint8Array(await crypto.subtle.digest('SHA-256', encoder.encode(value))); }
function equal(a, b) { let diff = a.length ^ b.length; for (let i=0; i<a.length; i++) diff |= a[i] ^ b[i]; return diff === 0; }
export default {
  async fetch(request, env) {
    if (request.method !== 'POST') return new Response('Not found', {status: 404});
    const token = request.headers.get('Authorization') || '';
    if (!env.GATE_SECRET || !equal(await digest(token), await digest(`Bearer ${env.GATE_SECRET}`))) return new Response('Unauthorized', {status: 401});
    try {
      const day = new Intl.DateTimeFormat('en-CA', {timeZone:'America/Los_Angeles', year:'numeric', month:'2-digit', day:'2-digit'}).format(new Date());
      const row = await env.DB.prepare(`INSERT INTO daily_usage(day, calls) VALUES (?, 1)
        ON CONFLICT(day) DO UPDATE SET calls = calls + 1 WHERE calls < 100 RETURNING calls`).bind(day).first();
      if (!row) return Response.json({error:'Daily limit reached. Try again after midnight Pacific time.'}, {status:429, headers:{'Cache-Control':'no-store'}});
      return Response.json({remaining:100-row.calls, day}, {headers:{'Cache-Control':'no-store'}});
    } catch { return Response.json({error:'Daily limit service unavailable.'}, {status:503, headers:{'Cache-Control':'no-store'}}); }
  }
};
