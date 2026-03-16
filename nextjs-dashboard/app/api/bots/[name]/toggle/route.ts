import { NextResponse } from 'next/server';

export async function POST(_req: Request, { params }: { params: { name: string } }) {
  return NextResponse.json({
    ok: true,
    name: params.name,
    status: 'running',
    message: `Bot ${params.name} toggled`,
  });
}
