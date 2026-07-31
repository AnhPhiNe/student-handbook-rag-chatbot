export const config = {
  runtime: 'edge',
};

export default async function handler(request) {
  try {
    const res = await fetch('https://api.counterapi.dev/v1/hcmue-student-handbook/visits/up', {
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
