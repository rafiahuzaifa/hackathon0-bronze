import { NextResponse } from 'next/server';

export async function POST(_req: Request, { params }: { params: { id: string } }) {
  return NextResponse.json({ ok: true, id: params.id, message: 'Rejected successfully' });
}
