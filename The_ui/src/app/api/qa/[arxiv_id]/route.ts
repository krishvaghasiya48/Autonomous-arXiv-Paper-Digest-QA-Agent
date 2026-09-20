export const dynamic = 'force-dynamic';

export async function POST(
  request: Request,
  { params }: { params: Promise<{ arxiv_id: string }> }
) {
  const { arxiv_id } = await params;
  const body = await request.json();
  try {
    const res = await fetch(`http://localhost:8000/api/qa/${arxiv_id}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    return Response.json(data, { status: res.status });
  } catch {
    return Response.json(
      { detail: 'Backend unavailable. Start the Python API server on port 8000.' },
      { status: 503 }
    );
  }
}
