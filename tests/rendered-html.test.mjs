import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

async function render() {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);

  return worker.fetch(
    new Request("http://localhost/", { headers: { accept: "text/html" } }),
    { ASSETS: { fetch: async () => new Response("Not found", { status: 404 }) } },
    { waitUntil() {}, passThroughOnException() {} },
  );
}

test("server-renders the painting dashboard with project totals", async () => {
  const response = await render();
  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type") ?? "", /^text\/html\b/i);

  const html = await response.text();
  assert.match(html, /<title>Relatório Gerencial Consolidado — Pintura MTECH<\/title>/i);
  assert.match(html, /Linha do tempo — remessas e retornos por projeto/i);
  assert.match(html, /Enviado total/i);
  assert.match(html, /Retornado total/i);
  assert.match(html, /independentemente do período/i);
  assert.doesNotMatch(html, /codex-preview|Your site is taking shape/i);
});

test("keeps project totals independent from the visible-period fields", async () => {
  const [page, data, styles] = await Promise.all([
    readFile(new URL("../app/page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/data/painting-data.ts", import.meta.url), "utf8"),
    readFile(new URL("../app/globals.css", import.meta.url), "utf8"),
  ]);

  assert.match(page, /project\.totalSent \?\? 0/);
  assert.match(page, /project\.totalReturned \?\? 0/);
  assert.match(data, /totalSent = entries\.filter\(\(entry\) => entry\.movement === "remessa"\)\.reduce/);
  assert.match(data, /totalReturned = entries\.filter\(\(entry\) => entry\.movement === "retorno"\)\.reduce/);
  assert.match(page, /Display \/ Processo/);
  assert.match(page, /project\.processes/);
  assert.match(styles, /\.process-row/);
  assert.match(styles, /\.total-heading/);
  assert.match(styles, /\.total-value/);
});
