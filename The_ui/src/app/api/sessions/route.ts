export const dynamic = 'force-dynamic';

export async function GET() {
  try {
    const res = await fetch('http://localhost:8000/api/sessions');
    const data = await res.json();
    return Response.json(data, { status: res.status });
  } catch {
    return Response.json(
      { detail: 'Backend unavailable. Start the Python API server on port 8000.' },
      { status: 503 }
    );
  }
}
