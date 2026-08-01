export const config = {
  runtime: 'edge',
};

export default async function handler(request) {
  try {
    const requestUrl = new URL(request.url);
    const increment = requestUrl.searchParams.get('increment') === 'true'
      || requestUrl.searchParams.get('mode') === 'up';
    const apiBaseUrl = process.env.VISITOR_API_BASE_URL
      || process.env.VITE_API_BASE_URL
      || 'https://anhfeee-hcmue-handbook-rag-api.hf.space';
    const metricsUrl = new URL('/api/metrics/visits', apiBaseUrl);
    metricsUrl.searchParams.set('increment', increment ? 'true' : 'false');

    const res = await fetch(metricsUrl.toString(), {
      headers: {
        'Accept': 'application/json'
      }
    });
    
    if (!res.ok) {
      return new Response(JSON.stringify({ error: 'API Error' }), {
        status: res.status,
        headers: { 'Content-Type': 'application/json' }
      });
    }

    const data = await res.json();
    
    // Add cache-control to ensure Vercel doesn't cache this response
    return new Response(JSON.stringify(data), {
      status: 200,
      headers: {
        'Content-Type': 'application/json',
        'Cache-Control': 'no-store, no-cache, must-revalidate, proxy-revalidate',
        'Pragma': 'no-cache',
        'Expires': '0'
      }
    });
  } catch (err) {
    return new Response(JSON.stringify({ error: err.message }), {
      status: 500,
      headers: { 'Content-Type': 'application/json' }
    });
  }
}
