import "server-only";

import { Client } from "pg";
import {
  paintProjects as sampleProjects,
  timelineDates as sampleTimelineDates,
  type PaintProject,
} from "./form-responses";

type RawPaintingEntry = {
  id: number;
  timestamp: Date | string | null;
  cliente: string | null;
  display: string | null;
  numero_display: string | null;
  codigo_pintura: string | null;
  maquinario: string | null;
  processo: string | null;
  data_producao: Date | string | null;
  hora_lancamento: string | null;
  quantidade: number | string | null;
  quantidade_total: number | string | null;
  created_at: Date | string | null;
};

type Movement = "remessa" | "retorno";

type ParsedEntry = {
  date: Date;
  dateKey: string;
  movement: Movement;
  quantity: number;
  cliente: string;
  display: string;
  numeroDisplay: string;
  codigoPintura: string;
  color: string;
  updatedAt: Date;
};

export type PaintingDashboardData = {
  projects: PaintProject[];
  timelineDates: string[];
  source: "live" | "demo";
  updatedAt: string;
  warning?: string;
};

const DAY_MS = 86_400_000;

function cleanText(value: unknown) {
  if (value === null || value === undefined) return "";
  const text = String(value).trim();
  return ["", "none", "nan", "<na>"].includes(text.toLowerCase()) ? "" : text;
}

function normalized(value: string) {
  return value
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .trim()
    .toUpperCase();
}

function parseDate(value: Date | string | null) {
  if (value instanceof Date && !Number.isNaN(value.valueOf())) {
    return new Date(Date.UTC(value.getUTCFullYear(), value.getUTCMonth(), value.getUTCDate()));
  }

  const text = cleanText(value);
  if (!text) return null;
  const brazilian = text.match(/^(\d{1,2})\/(\d{1,2})\/(\d{2}|\d{4})$/);
  if (brazilian) {
    const yearValue = Number(brazilian[3]);
    const year = yearValue < 100 ? 2000 + yearValue : yearValue;
    return new Date(Date.UTC(year, Number(brazilian[2]) - 1, Number(brazilian[1])));
  }

  const iso = text.match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (iso) return new Date(Date.UTC(Number(iso[1]), Number(iso[2]) - 1, Number(iso[3])));

  const parsed = new Date(text);
  if (Number.isNaN(parsed.valueOf())) return null;
  return new Date(Date.UTC(parsed.getUTCFullYear(), parsed.getUTCMonth(), parsed.getUTCDate()));
}

function formatDateKey(date: Date) {
  return `${String(date.getUTCDate()).padStart(2, "0")}/${String(date.getUTCMonth() + 1).padStart(2, "0")}`;
}

function movementFromProcess(process: string, machinery: string): Movement | null {
  const key = normalized(process);
  if (key.includes("RETORNO")) return "retorno";
  if (key.includes("ENVIO") || key.includes("REMESSA")) return "remessa";
  const machineryKey = normalized(machinery);
  if (machineryKey.includes("RETORNO")) return "retorno";
  if (machineryKey.includes("ENVIO") || machineryKey.includes("REMESSA")) return "remessa";
  return null;
}

function colorFromProcess(process: string) {
  const color = process
    .replace(/^.*?\b(?:ENVIO|REMESSA|RETORNO)\b\s*[-:–—]?\s*/i, "")
    .trim();
  return color === process && process.includes(" - ")
    ? process.split(" - ").at(-1)?.trim() || "SEM COR"
    : color || "SEM COR";
}

function numberValue(value: number | string | null) {
  const parsed = Number(String(value ?? "0").replace(",", "."));
  return Number.isFinite(parsed) ? parsed : 0;
}

function uniqueParts(parts: string[]) {
  const result: string[] = [];
  for (const part of parts.map((value) => value.trim()).filter(Boolean)) {
    const normalizedPart = normalized(part);
    const containingIndex = result.findIndex((current) => normalized(current).includes(normalizedPart));
    if (containingIndex >= 0) continue;
    const containedIndex = result.findIndex((current) => normalizedPart.includes(normalized(current)));
    if (containedIndex >= 0) result.splice(containedIndex, 1, part);
    else result.push(part);
  }
  return result;
}

function daysBetween(start: Date, end: Date) {
  return Math.max(0, Math.round((end.valueOf() - start.valueOf()) / DAY_MS));
}

function dateRange(start: Date, end: Date) {
  const dates: string[] = [];
  for (let cursor = start.valueOf(); cursor <= end.valueOf(); cursor += DAY_MS) {
    dates.push(formatDateKey(new Date(cursor)));
  }
  return dates;
}

function parseRows(rows: RawPaintingEntry[]) {
  return rows.flatMap<ParsedEntry>((row) => {
    const date = parseDate(row.data_producao);
    const process = cleanText(row.processo);
    if (normalized(process).startsWith("TINTA ")) return [];
    const movement = movementFromProcess(process, cleanText(row.maquinario));
    if (!date || !movement) return [];

    const updatedAt = new Date(cleanText(row.timestamp) || cleanText(row.created_at) || date.toISOString());
    return [{
      date,
      dateKey: formatDateKey(date),
      movement,
      quantity: numberValue(row.quantidade),
      cliente: cleanText(row.cliente),
      display: cleanText(row.display).replace(/\s*-\s*lote.*$/i, "").trim(),
      numeroDisplay: cleanText(row.numero_display),
      codigoPintura: cleanText(row.codigo_pintura),
      color: colorFromProcess(process),
      updatedAt: Number.isNaN(updatedAt.valueOf()) ? date : updatedAt,
    }];
  });
}

function buildDashboard(rows: RawPaintingEntry[]): PaintingDashboardData | null {
  const parsed = parseRows(rows);
  if (!parsed.length) return null;

  const clientFilter = normalized(process.env.MTECH_PAINTING_CLIENT_FILTER ?? "");
  const clientRows = clientFilter
    ? parsed.filter((entry) => normalized(entry.cliente).includes(clientFilter))
    : parsed;
  if (!clientRows.length) return null;

  const configuredYear = Number(process.env.MTECH_PAINTING_YEAR ?? "");
  const latestYear = Math.max(...clientRows.map((entry) => entry.date.getUTCFullYear()));
  const reportYear = Number.isInteger(configuredYear) && configuredYear > 2000 ? configuredYear : latestYear;
  const yearRows = clientRows.filter((entry) => entry.date.getUTCFullYear() === reportYear);
  if (!yearRows.length) return null;

  const grouped = new Map<string, ParsedEntry[]>();
  for (const entry of yearRows) {
    const key = [entry.cliente, entry.display, entry.numeroDisplay, entry.color, entry.codigoPintura].map(normalized).join("|");
    const current = grouped.get(key) ?? [];
    current.push(entry);
    grouped.set(key, current);
  }

  const maxProjects = Math.max(1, Number(process.env.MTECH_PAINTING_MAX_PROJECTS ?? "20") || 20);
  const selectedGroups = [...grouped.values()]
    .sort((left, right) => Math.max(...right.map((entry) => entry.date.valueOf())) - Math.max(...left.map((entry) => entry.date.valueOf())))
    .slice(0, maxProjects)
    .sort((left, right) => Math.min(...left.map((entry) => entry.date.valueOf())) - Math.min(...right.map((entry) => entry.date.valueOf())));

  const projects = selectedGroups.map<PaintProject>((entries) => {
    const remittanceEntries = entries.filter((entry) => entry.movement === "remessa");
    const returnEntries = entries.filter((entry) => entry.movement === "retorno");
    const remittanceDates = [...new Set(remittanceEntries.map((entry) => entry.dateKey))];
    const returnDates = [...new Set(returnEntries.map((entry) => entry.dateKey))];
    const firstRemittance = remittanceEntries.reduce<Date | null>(
      (first, entry) => !first || entry.date < first ? entry.date : first,
      null,
    );
    const firstReturn = returnEntries.reduce<Date | null>(
      (first, entry) => !first || entry.date < first ? entry.date : first,
      null,
    );
    const lastReturn = returnEntries.reduce<Date | null>(
      (last, entry) => !last || entry.date > last ? entry.date : last,
      null,
    );
    const totalSent = remittanceEntries.reduce((sum, entry) => sum + entry.quantity, 0);
    const totalReturned = returnEntries.reduce((sum, entry) => sum + entry.quantity, 0);
    const hasReturn = returnEntries.length > 0;
    const isPartial = hasReturn && totalSent > 0 && totalReturned < totalSent;
    const reference = entries[0];

    return {
      name: uniqueParts([reference.cliente, reference.display, reference.color, reference.codigoPintura]).join(" "),
      remessas: remittanceDates,
      retornos: returnDates,
      remittanceDayCount: remittanceDates.length,
      firstReturnDays: firstRemittance && firstReturn ? daysBetween(firstRemittance, firstReturn) : undefined,
      conclusionDays: firstRemittance && lastReturn ? daysBetween(firstRemittance, lastReturn) : undefined,
      status: !hasReturn ? "Sem retorno" : isPartial ? "Parcial" : "Concluído",
    };
  });

  const selectedEntries = selectedGroups.flat();
  const firstDate = new Date(Math.min(...selectedEntries.map((entry) => entry.date.valueOf())));
  const lastDate = new Date(Math.max(...selectedEntries.map((entry) => entry.date.valueOf())));
  const maxDays = Math.max(7, Number(process.env.MTECH_PAINTING_MAX_TIMELINE_DAYS ?? "45") || 45);
  const visibleStart = daysBetween(firstDate, lastDate) + 1 > maxDays
    ? new Date(lastDate.valueOf() - (maxDays - 1) * DAY_MS)
    : firstDate;
  const updatedAt = new Date(Math.max(...selectedEntries.map((entry) => entry.updatedAt.valueOf())));

  return {
    projects,
    timelineDates: dateRange(visibleStart, lastDate),
    source: "live",
    updatedAt: updatedAt.toISOString(),
  };
}

function demoData(warning?: string): PaintingDashboardData {
  return {
    projects: sampleProjects,
    timelineDates: sampleTimelineDates,
    source: "demo",
    updatedAt: "2026-07-31T11:00:00.000Z",
    warning,
  };
}

export async function loadPaintingDashboardData(): Promise<PaintingDashboardData> {
  const databaseUrl = process.env.DATABASE_URL?.trim();
  if (!databaseUrl) return demoData("A conexão com o Formulário MTECH ainda não foi ativada.");

  const client = new Client({ connectionString: databaseUrl });
  try {
    await client.connect();
    const result = await client.query<RawPaintingEntry>(`
      SELECT
        id, timestamp, cliente, display, numero_display, codigo_pintura,
        maquinario, processo, data_producao, hora_lancamento,
        quantidade, quantidade_total, created_at
      FROM painting_entries
      ORDER BY timestamp DESC NULLS LAST, id DESC
    `);
    return buildDashboard(result.rows) ?? demoData("Nenhum lançamento de pintura foi encontrado na fonte atual.");
  } catch (error) {
    console.error("Falha ao carregar painting_entries", error);
    return demoData("A fonte do formulário está temporariamente indisponível; os dados de referência foram mantidos.");
  } finally {
    await client.end().catch(() => undefined);
  }
}
