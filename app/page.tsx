import type { CSSProperties } from "react";
import { AutoRefresh } from "./auto-refresh";
import type { PaintProject } from "./data/form-responses";
import { loadPaintingDashboardData } from "./data/painting-data";
import { DownloadReportButton } from "./download-report";

export const dynamic = "force-dynamic";

export const metadata = {
  title: "Relatório Gerencial Consolidado — Pintura MTECH",
  description: "Controle de remessas e retornos por projeto da MTECH.",
};

const statusConfig = {
  "Concluído": { icon: "✓", className: "done" },
  Parcial: { icon: "◷", className: "partial" },
  "Sem retorno": { icon: "×", className: "missing" },
} as const;

function formatDecimal(value: number) {
  return value.toLocaleString("pt-BR", {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  });
}

function StatusPill({ status }: { status: PaintProject["status"] }) {
  const config = statusConfig[status];

  return (
    <span className={`status-pill ${config.className}`}>
      <span aria-hidden="true">{config.icon}</span>
      {status}
    </span>
  );
}

function MetricCard({
  icon,
  label,
  value,
  suffix,
  tone,
}: {
  icon: string;
  label: string;
  value: string | number;
  suffix?: string;
  tone: "navy" | "cyan" | "green" | "blue";
}) {
  return (
    <article className="metric-card">
      <div className={`metric-icon ${tone}`} aria-hidden="true">
        {icon}
      </div>
      <div className="metric-copy">
        <p>{label}</p>
        <strong>
          {value}
          {suffix && <small>{suffix}</small>}
        </strong>
      </div>
    </article>
  );
}

function Timeline({
  projects,
  timelineDates,
}: {
  projects: PaintProject[];
  timelineDates: string[];
}) {
  const timelineStyle = {
    "--timeline-columns": Math.max(timelineDates.length, 1),
    "--timeline-width": `${Math.max(820, timelineDates.length * 43)}px`,
  } as CSSProperties;

  return (
    <section className="timeline-card" aria-labelledby="timeline-title">
      <div className="timeline-heading">
        <div className="legend" aria-label="Legenda da linha do tempo">
          <span><i className="legend-remessa" /> Remessa</span>
          <span><i className="legend-retorno" /> Retorno</span>
        </div>
        <h2 id="timeline-title">Linha do tempo — remessas e retornos por projeto</h2>
        <span className="timeline-spacer" aria-hidden="true" />
      </div>

      <div className="timeline-scroll" style={timelineStyle}>
        <div className="timeline-grid timeline-header">
          <strong className="project-heading">Projeto</strong>
          <div className="dates-row">
            {timelineDates.map((date) => <span key={date}>{date}</span>)}
          </div>
          <strong>Status</strong>
        </div>

        {projects.map((project, projectIndex) => {
          const allEvents = [...project.remessas, ...project.retornos]
            .filter((date) => timelineDates.includes(date))
            .sort((a, b) => timelineDates.indexOf(a) - timelineDates.indexOf(b));
          const first = allEvents[0];
          const last = allEvents[allEvents.length - 1];
          const firstIndex = first ? timelineDates.indexOf(first) : 0;
          const lastIndex = last ? timelineDates.indexOf(last) : firstIndex;
          const trackStyle = {
            "--track-start": `${((firstIndex + 0.5) / Math.max(timelineDates.length, 1)) * 100}%`,
            "--track-width": `${((lastIndex - firstIndex) / Math.max(timelineDates.length, 1)) * 100}%`,
          } as CSSProperties;

          return (
            <div className="timeline-grid timeline-project" key={`${project.name}-${projectIndex}`}>
              <div className="project-name">
                <span className="project-number">{projectIndex + 1}</span>
                <span>{project.name}</span>
              </div>
              <div className="event-row" style={trackStyle}>
                {allEvents.length > 1 && <i className="event-track" />}
                {timelineDates.map((date) => {
                  const isRemessa = project.remessas.includes(date);
                  const isRetorno = project.retornos.includes(date);

                  return (
                    <span className="event-cell" key={date}>
                      {isRemessa && <i className="event remessa" title={`Remessa em ${date}`} />}
                      {isRetorno && <i className="event retorno" title={`Retorno em ${date}`} />}
                    </span>
                  );
                })}
              </div>
              <div className="timeline-status"><StatusPill status={project.status} /></div>
            </div>
          );
        })}
      </div>
    </section>
  );
}

export default async function Home() {
  const dashboard = await loadPaintingDashboardData();
  const projects = dashboard.projects;
  const returnedProjects = projects.filter((project) => project.retornos.length > 0);
  const concludedProjects = projects.filter((project) => project.status === "Concluído");
  const averageRemittanceDays = projects.length
    ? projects.reduce((sum, project) => sum + project.remittanceDayCount, 0) / projects.length
    : 0;
  const averageFirstReturn = returnedProjects.length
    ? returnedProjects.reduce((sum, project) => sum + (project.firstReturnDays ?? 0), 0) / returnedProjects.length
    : 0;
  const averageConclusion = returnedProjects.length
    ? returnedProjects.reduce((sum, project) => sum + (project.conclusionDays ?? 0), 0) / returnedProjects.length
    : 0;
  const noReturn = projects.filter((project) => project.status === "Sem retorno");
  const partial = projects.find((project) => project.status === "Parcial");
  const slowestFirstReturn = returnedProjects.length
    ? returnedProjects.reduce((slowest, project) =>
      (project.firstReturnDays ?? 0) > (slowest.firstReturnDays ?? 0) ? project : slowest,
    )
    : null;
  const longestCycle = concludedProjects.length
    ? concludedProjects.reduce((longest, project) =>
      (project.conclusionDays ?? 0) > (longest.conclusionDays ?? 0) ? project : longest,
    )
    : null;
  const updatedAt = new Date(dashboard.updatedAt).toLocaleString("pt-BR", {
    timeZone: "America/Sao_Paulo",
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
  const baseLabel = dashboard.source === "live" ? "Formulário MTECH — Pintura" : "Controle Anísio 2026";

  return (
    <main className="dashboard-page">
      <AutoRefresh />

      <div className="report-toolbar">
        <div className="refresh-state" role="status">
          <i className={dashboard.source} aria-hidden="true" />
          {dashboard.source === "live" ? `Dados atualizados em ${updatedAt}` : "Base demonstrativa"}
        </div>
        <DownloadReportButton />
      </div>

      <div className="report-shell" id="painting-report">
        <header className="report-header">
          <div className="brand-mark" aria-label="MTECH Pintura">
            <span className="spray-can" aria-hidden="true" />
            <span className="spray-dots" aria-hidden="true">••••</span>
          </div>
          <div className="title-block">
            <h1>Relatório gerencial consolidado — pintura JDE</h1>
            <p>Controle de Remessas e Retornos por Projeto <i /> Base: {baseLabel}</p>
          </div>
          <div className="header-stamp">
            <span>PAINEL MTECH</span>
            <small>{dashboard.source === "live" ? `Atualizado ${updatedAt}` : "Base histórica"}</small>
          </div>
        </header>

        {dashboard.warning && <div className="data-warning" role="status">{dashboard.warning}</div>}

        <section className="metrics" aria-label="Indicadores principais">
          <MetricCard icon="▣" label="projetos analisados" value={projects.length} tone="navy" />
          <MetricCard icon="↻" label="projetos com retorno registrado" value={returnedProjects.length} tone="cyan" />
          <MetricCard icon="▦" label="Média de dias de remessa:" value={formatDecimal(averageRemittanceDays)} tone="green" />
          <MetricCard icon="◷" label="Média até 1º retorno*:" value={formatDecimal(averageFirstReturn)} suffix="dias" tone="blue" />
          <MetricCard icon="◷" label="Média até conclusão**:" value={formatDecimal(averageConclusion)} suffix="dias" tone="blue" />
          <aside className="metric-notes">
            <p><b>*</b> Da 1ª remessa até o 1º retorno registrado</p>
            <p><b>**</b> Da 1ª remessa até o último retorno registrado</p>
            <em>Médias calculadas apenas para projetos com retorno registrado</em>
          </aside>
        </section>

        <Timeline projects={projects} timelineDates={dashboard.timelineDates} />

        <section className="lower-grid">
          <div className="summary-table-card">
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Projeto</th>
                    <th>Dias Rem.</th>
                    <th>1º Ret. (dias)</th>
                    <th>Conclusão (dias)</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {projects.map((project, index) => (
                    <tr key={`${project.name}-${index}`}>
                      <td><span className="table-number">{index + 1}</span>{project.name}</td>
                      <td>{project.remittanceDayCount}</td>
                      <td>{project.firstReturnDays != null ? `${project.firstReturnDays} dias` : "—"}</td>
                      <td>{project.conclusionDays != null ? `${project.conclusionDays} dias` : "não concluído"}</td>
                      <td><StatusPill status={project.status} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <aside className="insights-card" aria-labelledby="insights-title">
            <div className="insights-title-row">
              <div className="bulb" aria-hidden="true"><i /></div>
              <h2 id="insights-title">Insights / alertas</h2>
            </div>
            {noReturn.length > 0 && (
              <div className="insight alert">
                <span aria-hidden="true">!</span>
                <p><strong>Projetos sem retorno até a data-base:</strong><br />{noReturn.map((project) => project.name).join(" e ")}.</p>
              </div>
            )}
            {partial && (
              <div className="insight warning">
                <span aria-hidden="true">◷</span>
                <p><strong>Projeto com retorno parcial:</strong> {partial.name}.</p>
              </div>
            )}
            {slowestFirstReturn && (
              <div className="insight calendar">
                <span aria-hidden="true">▦</span>
                <p><strong>Maior prazo até o 1º retorno:</strong> {slowestFirstReturn.name}, com {slowestFirstReturn.firstReturnDays} dias.</p>
              </div>
            )}
            {longestCycle && (
              <div className="insight trend">
                <span aria-hidden="true">▥</span>
                <p><strong>Maior ciclo de conclusão:</strong> {longestCycle.name}, com {longestCycle.conclusionDays} dias.</p>
              </div>
            )}
          </aside>
        </section>

        <footer className="report-footer">
          <span className="info-icon" aria-hidden="true">i</span>
          <div className="definitions">
            <p><strong>Dias Rem.</strong> = quantidade de datas com remessa registrada.</p>
            <p><strong>1º Ret. (dias)</strong> = dias corridos entre a 1ª remessa e a 1ª data de retorno registrada.</p>
            <p><strong>Conclusão (dias)</strong> = dias corridos entre a 1ª remessa e o último retorno registrado.</p>
          </div>
          <div className="source-note">
            {dashboard.source === "live" ? (
              <><strong>Fonte:</strong> Formulário MTECH — tabela de pintura.<span>Atualização automática a cada 60 segundos.</span></>
            ) : (
              <><strong>Base:</strong> histórico consolidado de remessas e retornos.<span>Indicadores calculados conforme a sequência dos lançamentos.</span></>
            )}
          </div>
          <div className="paint-brush" aria-hidden="true"><i /><b /></div>
        </footer>
      </div>
    </main>
  );
}
