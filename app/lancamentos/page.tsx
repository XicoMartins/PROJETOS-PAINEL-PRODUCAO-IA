import { Client } from "pg";

export const dynamic = "force-dynamic";

type PaintingEntry = {
  id: number | string;
  timestamp: Date | string | null;
  cliente: string | null;
  display: string | null;
  numero_display: string | null;
  codigo_pintura: string | null;
  maquinario: string | null;
  processo: string | null;
  data_producao: Date | string | null;
  quantidade: number | string | null;
  quantidade_total: number | string | null;
  created_at: Date | string | null;
  projeto_auditoria: string;
};

const PROJECTS = [
  "SOLAR RACK SLIM SEM AÇÚCAR PRETO 335",
  "FEMSA PG+ ECONOMIA HÍBRIDO VERMELHO 1000",
] as const;

function formatDate(value: Date | string | null, withTime = false) {
  if (!value) return "—";
  const parsed = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(parsed.valueOf())) return String(value);
  return new Intl.DateTimeFormat("pt-BR", {
    timeZone: "America/Sao_Paulo",
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    ...(withTime ? { hour: "2-digit", minute: "2-digit" } : {}),
  }).format(parsed);
}

function formatQuantity(value: number | string | null) {
  const number = Number(value ?? 0);
  return new Intl.NumberFormat("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 }).format(number);
}

function movement(process: string | null, machinery: string | null) {
  const value = `${process ?? ""} ${machinery ?? ""}`.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toUpperCase();
  if (value.includes("RETORNO")) return "Retorno";
  if (value.includes("ENVIO") || value.includes("REMESSA")) return "Envio";
  return "Não identificado";
}

async function loadEntries() {
  const databaseUrl = process.env.DATABASE_URL?.trim();
  if (!databaseUrl) throw new Error("A conexão da painting_entries não está configurada.");

  const client = new Client({ connectionString: databaseUrl, connectionTimeoutMillis: 12000 });
  await client.connect();
  try {
    const result = await client.query<PaintingEntry>(`
      SELECT id, timestamp, cliente, display, numero_display, codigo_pintura,
             maquinario, processo, data_producao, quantidade, quantidade_total, created_at,
             CASE
               WHEN UPPER(COALESCE(cliente, '')) LIKE '%SOLAR%'
                 THEN 'SOLAR RACK SLIM SEM AÇÚCAR PRETO 335'
               ELSE 'FEMSA PG+ ECONOMIA HÍBRIDO VERMELHO 1000'
             END AS projeto_auditoria
        FROM painting_entries
       WHERE (
              UPPER(COALESCE(cliente, '')) LIKE '%SOLAR%'
              AND UPPER(COALESCE(display, '')) LIKE '%RACK%SLIM%'
              AND UPPER(COALESCE(codigo_pintura, '')) LIKE '%335%'
             )
          OR (
              UPPER(COALESCE(cliente, '')) LIKE '%FEMSA%'
              AND UPPER(COALESCE(display, '')) LIKE '%ECONOMIA%HIBRIDO%'
              AND UPPER(COALESCE(codigo_pintura, '')) LIKE '%1000%'
             )
       ORDER BY projeto_auditoria, data_producao, timestamp NULLS LAST, id
    `);
    return result.rows;
  } finally {
    await client.end();
  }
}

export default async function PaintingEntriesAudit() {
  let entries: PaintingEntry[] = [];
  let error = "";
  try {
    entries = await loadEntries();
  } catch (reason) {
    error = reason instanceof Error ? reason.message : "Falha ao consultar a painting_entries.";
  }

  return (
    <main className="entries-page">
      <header className="entries-header">
        <div>
          <p className="entries-eyebrow">AUDITORIA DA BASE</p>
          <h1>Lançamentos da painting_entries</h1>
          <p>Fonte exclusiva: tabela painting_entries. Dois projetos, sem filtro de período.</p>
        </div>
        <a className="entries-back" href="/">← Voltar ao painel</a>
      </header>

      {error ? <section className="entries-message"><strong>Não foi possível abrir os lançamentos.</strong><br />{error}</section> : null}
      {!error && entries.length === 0 ? <section className="entries-message">Nenhum lançamento correspondente foi encontrado.</section> : null}

      {!error && entries.length > 0 && PROJECTS.map((project) => {
        const rows = entries.filter((entry) => entry.projeto_auditoria === project);
        const totalSent = rows.filter((entry) => movement(entry.processo, entry.maquinario) === "Envio").reduce((sum, entry) => sum + Number(entry.quantidade ?? 0), 0);
        const totalReturned = rows.filter((entry) => movement(entry.processo, entry.maquinario) === "Retorno").reduce((sum, entry) => sum + Number(entry.quantidade ?? 0), 0);
        return (
          <section className="entries-card" key={project}>
            <div className="entries-card-head">
              <div><h2>{project}</h2><p>{rows.length} lançamento(s) encontrado(s)</p></div>
              <div className="entries-totals"><span>Enviado <strong>{formatQuantity(totalSent)}</strong></span><span>Retornado <strong>{formatQuantity(totalReturned)}</strong></span></div>
            </div>
            <div className="entries-scroll">
              <table className="entries-table">
                <thead><tr><th>ID</th><th>Data produção</th><th>Movimento</th><th>Quantidade</th><th>Quantidade total</th><th>Cliente</th><th>Display</th><th>Nº display</th><th>Código pintura</th><th>Maquinário</th><th>Processo</th><th>Registrado em</th></tr></thead>
                <tbody>
                  {rows.map((entry) => <tr key={String(entry.id)}>
                    <td>{entry.id}</td><td>{formatDate(entry.data_producao)}</td><td><span className={`movement movement-${movement(entry.processo, entry.maquinario) === "Retorno" ? "return" : "sent"}`}>{movement(entry.processo, entry.maquinario)}</span></td>
                    <td className="entries-number">{formatQuantity(entry.quantidade)}</td><td className="entries-number">{formatQuantity(entry.quantidade_total)}</td><td>{entry.cliente || "—"}</td><td>{entry.display || "—"}</td><td>{entry.numero_display || "—"}</td><td>{entry.codigo_pintura || "—"}</td><td>{entry.maquinario || "—"}</td><td>{entry.processo || "—"}</td><td>{formatDate(entry.timestamp || entry.created_at, true)}</td>
                  </tr>)}
                </tbody>
              </table>
            </div>
          </section>
        );
      })}
    </main>
  );
}
