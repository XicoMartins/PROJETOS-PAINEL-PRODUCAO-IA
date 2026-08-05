"use client";

import { useState } from "react";

const EXPORT_WIDTH = 1500;

function nextFrame() {
  return new Promise<void>((resolve) => requestAnimationFrame(() => resolve()));
}

export function DownloadReportButton() {
  const [isExporting, setIsExporting] = useState(false);
  const [message, setMessage] = useState("");

  async function downloadReport() {
    const report = document.getElementById("painting-report");

    if (!report || isExporting) return;

    setIsExporting(true);
    setMessage("Preparando imagem…");

    const stage = document.createElement("div");

    try {
      const { toPng } = await import("html-to-image");
      const clone = report.cloneNode(true) as HTMLElement;

      clone.removeAttribute("id");
      clone.classList.add("capture-mode");
      stage.className = "capture-stage";
      stage.setAttribute("aria-hidden", "true");
      stage.appendChild(clone);
      document.body.appendChild(stage);

      await document.fonts.ready;
      await nextFrame();

      const exportHeight = Math.ceil(clone.scrollHeight);
      const dataUrl = await toPng(clone, {
        backgroundColor: "#ffffff",
        cacheBust: true,
        height: exportHeight,
        pixelRatio: 2,
        width: EXPORT_WIDTH,
      });
      const date = new Intl.DateTimeFormat("sv-SE", {
        timeZone: "America/Sao_Paulo",
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
      }).format(new Date());
      const link = document.createElement("a");

      link.download = `painel-pintura-mtech-${date}.png`;
      link.href = dataUrl;
      link.click();
      setMessage("Imagem baixada.");
    } catch (error) {
      console.error("Não foi possível gerar a imagem do painel.", error);
      setMessage("Não foi possível baixar a imagem. Tente novamente.");
    } finally {
      stage.remove();
      setIsExporting(false);
      window.setTimeout(() => setMessage(""), 3500);
    }
  }

  return (
    <div className="download-control">
      <button
        className="download-button"
        type="button"
        onClick={downloadReport}
        disabled={isExporting}
        aria-describedby="download-status"
      >
        <span aria-hidden="true">↓</span>
        {isExporting ? "Gerando imagem…" : "Baixar painel em PNG"}
      </button>
      <span className="sr-only" id="download-status" aria-live="polite">{message}</span>
    </div>
  );
}
