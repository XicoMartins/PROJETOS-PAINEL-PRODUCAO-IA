import { createHash } from "node:crypto";
import fs from "node:fs/promises";
import path from "node:path";
import { pathToFileURL } from "node:url";

const IMPORT_NAMESPACE = "mtech-historico-anisio-2026/v1";

const EXACT_SHEET_MAPPINGS = {
  "JDE ARAMADO P MARATA 40": {
    cliente: "JDE COFFEE",
    display: "DISPLAY ARAMADO P LOR",
    numero_display: "26070225",
    codigo_pintura: "AM - 0040",
    color: "AMARELO",
  },
  "JDE ARAMADO P LOR 185": {
    cliente: "JDE COFFEE",
    display: "DISPLAY ARAMADO P LOR",
    numero_display: "26070225",
    codigo_pintura: "PR - 0185",
    color: "PRETO",
  },
  "JDE ARAMADO P PILÃO 211": {
    cliente: "JDE COFFEE",
    display: "DISPLAY ARAMADO P PILÃO",
    numero_display: "26070211",
    codigo_pintura: "VM - 0211",
    color: "VERMELHO",
  },
  "JDE ARAMADO G LOR 322": {
    cliente: "JDE COFFEE",
    display: "DISPLAY ARAMADO G",
    numero_display: "26061198",
    codigo_pintura: "PR - 0322",
    color: "PRETO",
  },
  "JDE ARAMADO G DAMASCO 54": {
    cliente: "JDE COFFEE",
    display: "DISPLAY ARAMADO G",
    numero_display: "26061198",
    codigo_pintura: "BD - 0054",
    color: "BORDO",
  },
  "JDE ARAMADO G PELE 85": {
    cliente: "JDE COFFEE",
    display: "DISPLAY ARAMADO G",
    numero_display: "26061198",
    codigo_pintura: "MR - 0085",
    color: "MARROM",
  },
  "JDE ARAMADO G MARATÁ 261": {
    cliente: "JDE COFFEE",
    display: "DISPLAY ARAMADO G",
    numero_display: "26061198",
    codigo_pintura: "AM - 0261",
    color: "AMARELO",
  },
  "JDE ARAMADO G PILAO VERM 406+70": {
    cliente: "JDE COFFEE",
    display: "DISPLAY ARAMADO G",
    numero_display: "26061198",
    codigo_pintura: "VM - 0476",
    color: "VERMELHO",
  },
  "ARAMADO P PILAO 1500": {
    cliente: "JDE COFFEE",
    display: "DISPLAY ARAMADO P PILÃO",
    numero_display: "HIST-ANISIO-2026-037",
    codigo_pintura: "VM - 1500",
    color: "VERMELHO",
  },
};

function normalize(value) {
  return String(value ?? "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toUpperCase()
    .replace(/[^A-Z0-9]+/g, " ")
    .trim();
}

function excelSerialToIso(value) {
  if (typeof value !== "number" || value < 40_000 || value > 60_000) return null;
  return new Date(Math.round((value - 25_569) * 86_400_000)).toISOString().slice(0, 10);
}

function columnName(index) {
  let result = "";
  for (let value = index + 1; value > 0; value = Math.floor((value - 1) / 26)) {
    result = String.fromCharCode(65 + ((value - 1) % 26)) + result;
  }
  return result;
}

function colorCode(color) {
  const key = normalize(color);
  if (key.includes("PRETO") && key.includes("VERMELHO")) return "PV";
  if (key.includes("PRETO") && key.includes("TEXT")) return "PT";
  if (key.includes("PRETO")) return "PR";
  if (key.includes("BRANCO")) return "BR";
  if (key.includes("VERMELHO")) return "VM";
  if (key.includes("AZUL")) return "AZ";
  if (key.includes("LARANJA")) return "LJ";
  if (key.includes("AMARELO")) return "AM";
  if (key.includes("MARR")) return "MR";
  if (key.includes("DAMASCO") || key.includes("BORDO")) return "BD";
  return "HIST";
}

function paddedLot(value) {
  const digits = String(value ?? "").replace(/\.0+$/, "").replace(/\D/g, "");
  return digits ? digits.padStart(4, "0") : "0000";
}

function mapProject(event) {
  const exact = EXACT_SHEET_MAPPINGS[event.sheet];
  if (exact) return { ...event, ...exact };
  return {
    ...event,
    cliente: "HISTÓRICO ANISIO",
    display: event.sheet,
    numero_display: `HIST-ANISIO-2026-${String(event.sheetIndex).padStart(3, "0")}`,
    codigo_pintura: `${colorCode(event.color)} - ${paddedLot(event.lot)}`,
    color: String(event.color || "HISTÓRICO").toUpperCase(),
  };
}

function correctedDate(sheet, isoDate, column, audit) {
  if (sheet === "JDE ARAMADO G LOR 322" && column === "M" && isoDate === "2026-09-22") {
    audit.dateCorrections.push({ sheet, from: isoDate, to: "2026-07-22", reason: "sequência lógica 20/07–24/07" });
    return "2026-07-22";
  }
  if (sheet === "RACK + ECONOMIA 1700" && column === "CQ" && isoDate === "2026-04-23") {
    audit.dateCorrections.push({ sheet, from: isoDate, to: "2026-05-23", reason: "sequência lógica 22/05–25/05" });
    return "2026-05-23";
  }
  return isoDate;
}

function extractHistoricalEvents(workbook) {
  const rawEvents = [];
  const audit = { dateCorrections: [], ignoredNonDatePairs: [], signedAdjustments: [] };

  for (let sheetIndex = 0; sheetIndex < workbook.worksheets.items.length; sheetIndex += 1) {
    const sheet = workbook.worksheets.getItemAt(sheetIndex);
    const values = sheet.getUsedRange().values;
    const model = String(values?.[1]?.[0] ?? sheet.name).trim();
    const color = String(values?.[3]?.[0] ?? "").trim();
    const lot = String(values?.[3]?.[9] ?? "").trim();
    const maxColumns = Math.max(...values.map((row) => row.length));

    let componentEnd = 4;
    while (
      componentEnd < values.length
      && typeof values[componentEnd]?.[0] === "string"
      && String(values[componentEnd][0]).trim()
    ) {
      const isPaintInput = normalize(values[componentEnd][0]) === "TINTA";
      componentEnd += 1;
      if (isPaintInput) break;
    }

    for (let column = 10; column < maxColumns; column += 2) {
      const rawDate = excelSerialToIso(values?.[2]?.[column]);
      if (!rawDate) {
        if (values?.[2]?.[column] !== null && values?.[2]?.[column] !== undefined && values?.[2]?.[column] !== "") {
          audit.ignoredNonDatePairs.push({
            sheet: sheet.name,
            columns: `${columnName(column)}:${columnName(column + 1)}`,
            header: String(values[2][column]),
          });
        }
        continue;
      }
      const date = correctedDate(sheet.name, rawDate, columnName(column), audit);

      for (let row = 4; row < componentEnd; row += 1) {
        const component = String(values?.[row]?.[0] ?? "").trim();
        if (!component) continue;
        const quantities = [
          { movement: "REMESSA", quantity: Number(values?.[row]?.[column]) },
          { movement: "RETORNO", quantity: Number(values?.[row]?.[column + 1]) },
        ];
        for (const item of quantities) {
          if (Number.isFinite(item.quantity) && item.quantity < 0) {
            audit.signedAdjustments.push({
              sheet: sheet.name,
              cell: `${columnName(column + (item.movement === "RETORNO" ? 1 : 0))}${row + 1}`,
              date,
              component,
              movement: item.movement,
              quantity: item.quantity,
            });
          }
          if (!Number.isFinite(item.quantity) || item.quantity === 0) continue;
          rawEvents.push({
            sheet: sheet.name,
            sheetIndex: sheetIndex + 1,
            model,
            color,
            lot,
            component,
            date,
            movement: item.movement,
            quantity: Math.round(item.quantity),
          });
        }
      }
    }
  }

  const aggregate = new Map();
  for (const event of rawEvents) {
    const key = [event.sheet, event.date, event.component, event.movement].join("|");
    const current = aggregate.get(key);
    if (!current) aggregate.set(key, { ...event, sourceCells: 1 });
    else {
      current.quantity += event.quantity;
      current.sourceCells += 1;
    }
  }

  return {
    events: [...aggregate.values()].map(mapProject),
    sourceCellEvents: rawEvents.length,
    sheetCount: workbook.worksheets.items.length,
    audit,
  };
}

function movementFromExisting(process, machinery) {
  const processKey = normalize(process);
  if (processKey.includes("RETORNO")) return "RETORNO";
  if (processKey.includes("ENVIO") || processKey.includes("REMESSA")) return "REMESSA";
  const machineryKey = normalize(machinery);
  if (machineryKey.includes("RETORNO")) return "RETORNO";
  if (machineryKey.includes("ENVIO") || machineryKey.includes("REMESSA")) return "REMESSA";
  return null;
}

function componentFromExisting(process) {
  const text = String(process ?? "");
  const match = text.match(/^(.*?)\s+(?:ENVIO|REMESSA|RETORNO)\b/i);
  if (match) return match[1].trim();
  return text.split(/\s+-\s+/)[0].trim();
}

function productionDateToIso(value) {
  if (value instanceof Date && !Number.isNaN(value.valueOf())) return value.toISOString().slice(0, 10);
  const text = String(value ?? "").trim();
  const brazilian = text.match(/^(\d{1,2})\/(\d{1,2})\/(\d{2}|\d{4})$/);
  if (brazilian) {
    const year = brazilian[3].length === 2 ? `20${brazilian[3]}` : brazilian[3];
    return `${year}-${brazilian[2].padStart(2, "0")}-${brazilian[1].padStart(2, "0")}`;
  }
  return text.slice(0, 10);
}

function groupKey(event) {
  return [
    event.cliente,
    event.display,
    event.numero_display,
    event.codigo_pintura,
    normalize(event.component),
    event.movement,
  ].join("|");
}

function existingGroupKey(row, movement) {
  return [
    row.cliente,
    row.display,
    row.numero_display,
    row.codigo_pintura,
    normalize(componentFromExisting(row.processo)),
    movement,
  ].join("|");
}

function allocateMissingHistory(events, existingRows) {
  const eventGroups = new Map();
  for (const event of events) {
    const key = groupKey(event);
    if (!eventGroups.has(key)) eventGroups.set(key, []);
    eventGroups.get(key).push(event);
  }

  const existingGroupTotals = new Map();
  const existingDateTotals = new Map();
  for (const row of existingRows) {
    const movement = movementFromExisting(row.processo, row.maquinario);
    if (!movement) continue;
    const key = existingGroupKey(row, movement);
    const dateKey = `${key}|${productionDateToIso(row.data_producao)}`;
    const quantity = Number(row.quantidade) || 0;
    existingGroupTotals.set(key, (existingGroupTotals.get(key) || 0) + quantity);
    existingDateTotals.set(dateKey, (existingDateTotals.get(dateKey) || 0) + quantity);
  }

  const planned = [];
  const reconciliation = [];
  for (const [key, groupEvents] of eventGroups) {
    const ordered = [...groupEvents].sort((left, right) => left.date.localeCompare(right.date));
    const targetQuantity = ordered.reduce((sum, event) => sum + event.quantity, 0);
    const existingQuantity = existingGroupTotals.get(key) || 0;
    if (!existingGroupTotals.has(key)) {
      for (const event of ordered) {
        planned.push({ ...event, importQuantity: event.quantity, targetEventQuantity: event.quantity });
      }
      reconciliation.push({
        key,
        sheet: ordered[0].sheet,
        component: ordered[0].component,
        movement: ordered[0].movement,
        targetQuantity,
        existingQuantity: 0,
        plannedQuantity: targetQuantity,
        unallocatedQuantity: 0,
      });
      continue;
    }
    let missingQuantity = Math.max(0, targetQuantity - existingQuantity);
    const originalMissing = missingQuantity;

    for (const event of ordered) {
      if (missingQuantity <= 0) break;
      const exactDateQuantity = existingDateTotals.get(`${key}|${event.date}`) || 0;
      const available = Math.max(0, event.quantity - exactDateQuantity);
      const importQuantity = Math.min(available, missingQuantity);
      if (importQuantity > 0) {
        planned.push({ ...event, importQuantity, targetEventQuantity: event.quantity });
        missingQuantity -= importQuantity;
      }
    }

    reconciliation.push({
      key,
      sheet: ordered[0].sheet,
      component: ordered[0].component,
      movement: ordered[0].movement,
      targetQuantity,
      existingQuantity,
      plannedQuantity: originalMissing - missingQuantity,
      unallocatedQuantity: missingQuantity,
    });
  }

  const unallocated = reconciliation.filter((item) => item.unallocatedQuantity > 0);
  if (unallocated.length) throw new Error(`Falha ao alocar ${unallocated.length} grupos históricos.`);
  return { planned, reconciliation };
}

function formatBrazilianDate(isoDate) {
  const [year, month, day] = isoDate.split("-");
  return `${day}/${month}/${year.slice(-2)}`;
}

function sourceHash(row) {
  return createHash("sha256").update(JSON.stringify({
    namespace: IMPORT_NAMESPACE,
    sheet: row.sheet,
    date: row.date,
    component: normalize(row.component),
    movement: row.movement,
    targetEventQuantity: row.targetEventQuantity,
    importQuantity: row.importQuantity,
    cliente: row.cliente,
    display: row.display,
    numero_display: row.numero_display,
    codigo_pintura: row.codigo_pintura,
    color: row.color,
  })).digest("hex");
}

function rowsForInsert(planned) {
  return planned.map((row) => ({
    schema_version: "historical-xlsx-v1",
    timestamp: new Date(`${row.date}T12:00:00-03:00`).toISOString(),
    cliente: row.cliente,
    display: row.display,
    numero_display: row.numero_display,
    codigo_pintura: row.codigo_pintura,
    maquinario: "PINTURA",
    processo: `${row.component} ${row.movement === "REMESSA" ? "ENVIO" : "RETORNO"} - ${row.color}`,
    data_producao: formatBrazilianDate(row.date),
    hora_lancamento: "12:00",
    quantidade: row.importQuantity,
    quantidade_total: row.importQuantity,
    source_hash: sourceHash(row),
  }));
}

async function insertRows(client, rows) {
  if (!rows.length) return [];
  const result = await client.query(
    `
      INSERT INTO painting_entries (
        schema_version, timestamp, cliente, display, numero_display,
        codigo_pintura, maquinario, processo, data_producao,
        hora_lancamento, quantidade, quantidade_total, source_hash
      )
      SELECT
        payload.schema_version, payload.timestamp, payload.cliente, payload.display,
        payload.numero_display, payload.codigo_pintura, payload.maquinario,
        payload.processo, payload.data_producao, payload.hora_lancamento,
        payload.quantidade, payload.quantidade_total, payload.source_hash
      FROM jsonb_to_recordset($1::jsonb) AS payload(
        schema_version text, timestamp timestamptz, cliente text, display text,
        numero_display text, codigo_pintura text, maquinario text, processo text,
        data_producao text, hora_lancamento text, quantidade integer,
        quantidade_total integer, source_hash text
      )
      ON CONFLICT (source_hash) DO NOTHING
      RETURNING id, source_hash
    `,
    [JSON.stringify(rows)],
  );
  return result.rows;
}

function compactRunResult(manifest) {
  return {
    mode: manifest.mode,
    workbookSha256: manifest.workbook.sha256,
    workbookSheets: manifest.workbook.sheets,
    sourceEvents: manifest.workbook.aggregatedEvents,
    databaseRowsBefore: manifest.database.rowsBefore,
    plannedRows: manifest.import.plannedRows,
    insertedRows: manifest.import.insertedRows,
    plannedQuantity: manifest.import.plannedQuantity,
    auditDirectory: manifest.auditDirectory,
  };
}

export async function runHistoricalImport({
  workbookPath,
  databaseUrl,
  apply = false,
  outputRoot = path.join(path.dirname(workbookPath), "work", "historical-imports"),
  artifactModuleSpecifier = globalThis.process?.env?.ARTIFACT_TOOL_MODULE || "@oai/artifact-tool",
} = {}) {
  if (!workbookPath) throw new Error("workbookPath é obrigatório.");
  if (!databaseUrl) throw new Error("databaseUrl é obrigatório.");

  const [{ FileBlob, SpreadsheetFile }, { Client }] = await Promise.all([
    import(artifactModuleSpecifier),
    import("pg"),
  ]);
  const workbookBytes = await fs.readFile(workbookPath);
  const workbookSha256 = createHash("sha256").update(workbookBytes).digest("hex");
  const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(workbookPath));
  const extracted = extractHistoricalEvents(workbook);
  const runId = new Date().toISOString().replace(/[:.]/g, "-");
  const auditDirectory = path.join(outputRoot, runId);
  await fs.mkdir(auditDirectory, { recursive: true });

  const client = new Client({ connectionString: databaseUrl, ssl: { rejectUnauthorized: false } });
  await client.connect();
  let committed = false;
  try {
    if (apply) {
      await client.query("BEGIN");
      await client.query("SELECT pg_advisory_xact_lock(hashtext($1))", [IMPORT_NAMESPACE]);
    }

    const existingRows = (await client.query(`
      SELECT id, schema_version, timestamp, cliente, display, numero_display,
             codigo_pintura, maquinario, processo, data_producao,
             hora_lancamento, quantidade, quantidade_total, source_hash, created_at
      FROM painting_entries
      ORDER BY id
    `)).rows;
    await fs.writeFile(
      path.join(auditDirectory, "backup-before.json"),
      `${JSON.stringify(existingRows, null, 2)}\n`,
      "utf8",
    );

    const allocation = allocateMissingHistory(extracted.events, existingRows);
    const insertPayload = rowsForInsert(allocation.planned);
    let inserted = [];
    if (apply) {
      inserted = await insertRows(client, insertPayload);
      await client.query("COMMIT");
      committed = true;
    }

    const verification = apply ? (await client.query(`
      SELECT
        COUNT(*)::int AS total_rows,
        COUNT(*) FILTER (WHERE source_hash = ANY($1::text[]))::int AS imported_rows,
        MIN(timestamp) FILTER (WHERE source_hash = ANY($1::text[])) AS imported_min_timestamp,
        MAX(timestamp) FILTER (WHERE source_hash = ANY($1::text[])) AS imported_max_timestamp
      FROM painting_entries
    `, [insertPayload.map((row) => row.source_hash)])).rows[0] : null;

    const manifest = {
      namespace: IMPORT_NAMESPACE,
      mode: apply ? "apply" : "dry-run",
      generatedAt: new Date().toISOString(),
      auditDirectory,
      workbook: {
        path: workbookPath,
        sha256: workbookSha256,
        sheets: extracted.sheetCount,
        sourceCellEvents: extracted.sourceCellEvents,
        aggregatedEvents: extracted.events.length,
        audit: extracted.audit,
      },
      database: { rowsBefore: existingRows.length, verification },
      import: {
        plannedRows: insertPayload.length,
        plannedQuantity: insertPayload.reduce((sum, row) => sum + row.quantidade, 0),
        insertedRows: inserted.length,
        insertedIds: inserted.map((row) => String(row.id)),
        insertedHashes: inserted.map((row) => row.source_hash),
        skippedByReconciliation: extracted.events.length - insertPayload.length,
      },
      reconciliation: allocation.reconciliation,
      mapping: {
        exactSheets: Object.keys(EXACT_SHEET_MAPPINGS),
        defaultClient: "HISTÓRICO ANISIO",
        rule: "abate o total já existente por projeto, componente e movimento; aloca apenas o saldo histórico não coberto",
      },
    };
    await fs.writeFile(path.join(auditDirectory, "manifest.json"), `${JSON.stringify(manifest, null, 2)}\n`, "utf8");
    return { ...compactRunResult(manifest), manifest };
  } catch (error) {
    if (apply && !committed) await client.query("ROLLBACK").catch(() => undefined);
    throw error;
  } finally {
    await client.end().catch(() => undefined);
  }
}

const runtimeProcess = globalThis.process;
const isDirectRun = runtimeProcess?.argv?.[1]
  && import.meta.url === pathToFileURL(path.resolve(runtimeProcess.argv[1])).href;
if (isDirectRun) {
  const workbookPath = runtimeProcess.env.HISTORICAL_PAINTING_WORKBOOK;
  const databaseUrl = runtimeProcess.env.DATABASE_URL;
  const apply = runtimeProcess.argv.includes("--apply");
  const result = await runHistoricalImport({ workbookPath, databaseUrl, apply });
  console.log(JSON.stringify(compactRunResult(result.manifest), null, 2));
}
