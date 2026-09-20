export const dynamic = 'force-dynamic';

export async function POST(request: Request) {
  const body = await request.json();

  try {
    const upstream = await fetch('http://localhost:8000/api/digest', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });

    return new Response(upstream.body, {
      headers: {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache',
        Connection: 'keep-alive',
      },
    });
  } catch {
    return Response.json(
      { detail: 'Backend unavailable. Start the Python API server on port 8000.' },
      { status: 503 }
    );
  }
}
