export const dynamic = 'force-dynamic';

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ arxiv_id: string }> }
) {
  const { arxiv_id } = await params;
  try {
    const res = await fetch(`http://localhost:8000/api/briefing/${arxiv_id}`);
    const data = await res.json();
    return Response.json(data, { status: res.status });
  } catch {
    return Response.json(
      { detail: 'Backend unavailable. Start the Python API server on port 8000.' },
      { status: 503 }
    );
  }
}
