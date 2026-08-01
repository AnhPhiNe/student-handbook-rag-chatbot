export const config = {
  runtime: 'edge',
};

export default async function handler(request) {
  try {
    const requestUrl = new URL(request.url);
    const mode = requestUrl.searchParams.get('mode') === 'get' ? 'get' : 'up';
    const res = await fetch(`https://api.counterapi.dev/v1/hcmue-student-handbook/visits/${mode}`, {
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
    const count = typeof data.count === 'number'
      ? data.count
      : typeof data.value === 'number'
        ? data.value
        : null;
    const payload = count === null ? data : { ...data, count };
    
    // Add cache-control to ensure Vercel doesn't cache this response
    return new Response(JSON.stringify(payload), {
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
