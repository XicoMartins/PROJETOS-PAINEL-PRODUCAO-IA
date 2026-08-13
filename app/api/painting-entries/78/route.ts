import { Client } from "pg";

export async function POST(request: Request) {
  const databaseUrl = process.env.DATABASE_URL?.trim();
  if (!databaseUrl) return new Response("Conexão indisponível", { status: 503 });

  const client = new Client({ connectionString: databaseUrl, connectionTimeoutMillis: 12000 });
  await client.connect();
  try {
    const result = await client.query(
      `DELETE FROM painting_entries
        WHERE id = $1
          AND UPPER(COALESCE(cliente, '')) LIKE '%SOLAR%'
          AND UPPER(COALESCE(display, '')) LIKE '%RACK%SLIM%'
          AND UPPER(COALESCE(codigo_pintura, '')) LIKE '%335%'
      RETURNING id`,
      [78],
    );
    if (result.rowCount !== 1) return new Response("Lançamento 78 não encontrado ou não corresponde ao duplicado validado.", { status: 404 });
    return Response.redirect(new URL("/lancamentos?excluido=78", request.url), 303);
  } finally {
    await client.end();
  }
}
