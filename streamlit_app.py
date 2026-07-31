from __future__ import annotations

import html
import os
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from statistics import mean

import psycopg
import streamlit as st
import streamlit.components.v1 as components


st.set_page_config(
    page_title="Relatório Gerencial Consolidado — Pintura JDE",
    page_icon="🎨",
    layout="wide",
    initial_sidebar_state="collapsed",
)


CSS = """
<style>
  :root {
    --navy: #092d68;
    --blue: #0877c9;
    --teal: #088797;
    --green: #48b82f;
    --orange: #f39b24;
    --red: #e23b48;
    --ink: #17345d;
    --muted: #60728d;
    --line: #dce7f0;
    --soft: #f4f8fb;
  }
  .stApp { background: #edf3f8; color: var(--ink); }
  [data-testid="stHeader"], [data-testid="stToolbar"], footer { display: none !important; }
  .block-container {
    max-width: 1540px;
    padding: 18px 20px 32px;
  }
  .report-shell {
    background: #fff;
    border: 1px solid #d9e3ec;
    border-radius: 18px;
    box-shadow: 0 18px 55px rgba(12, 48, 88, .12);
    padding: 20px;
  }
  .report-head {
    display: flex; align-items: center; gap: 16px; margin-bottom: 16px;
  }
  .brand-mark {
    width: 66px; height: 66px; display: grid; place-items: center;
    border-radius: 16px; color: white; font-size: 34px;
    background: linear-gradient(145deg, var(--navy), var(--blue));
    box-shadow: 0 8px 20px rgba(9, 45, 104, .22);
  }
  .report-head h1 {
    margin: 0; color: var(--navy); font-size: clamp(24px, 2.4vw, 40px);
    line-height: 1.02; text-transform: uppercase; letter-spacing: -.6px;
  }
  .report-head p {
    color: var(--teal); margin: 7px 0 0; font-size: 17px; font-weight: 700;
  }
  .live-strip {
    display: flex; justify-content: space-between; gap: 14px; align-items: center;
    background: #eef9f1; border: 1px solid #b9e3bf; color: #246a32;
    border-radius: 12px; padding: 9px 13px; margin: 0 0 14px;
    font-size: 13px; font-weight: 700;
  }
  .live-dot {
    display: inline-block; width: 9px; height: 9px; border-radius: 50%;
    background: var(--green); margin-right: 7px; box-shadow: 0 0 0 4px #d8f2dc;
  }
  .kpi-grid {
    display: grid; grid-template-columns: repeat(5, minmax(150px, 1fr));
    gap: 12px; margin: 12px 0 18px;
  }
  .kpi {
    min-height: 92px; background: linear-gradient(180deg, #fff, #f8fbfd);
    border: 1px solid var(--line); border-radius: 14px; padding: 13px;
    display: flex; align-items: center; gap: 12px;
    box-shadow: 0 4px 12px rgba(10, 50, 90, .06);
  }
  .kpi-icon {
    flex: 0 0 48px; width: 48px; height: 48px; border-radius: 13px;
    display: grid; place-items: center; font-size: 24px; color: var(--navy);
    background: #e6f1fb;
  }
  .kpi:nth-child(2) .kpi-icon { background: #ddf3f3; color: var(--teal); }
  .kpi:nth-child(3) .kpi-icon { background: #edf8e8; color: #4d8c2b; }
  .kpi strong { color: var(--navy); font-size: 31px; line-height: 1; }
  .kpi p { margin: 4px 0 0; color: var(--muted); font-size: 12px; line-height: 1.2; font-weight: 700; }
  .panel {
    background: #fff; border: 1px solid var(--line); border-radius: 14px;
    overflow: hidden; margin-top: 12px;
  }
  .panel-title {
    padding: 12px 15px; color: var(--navy); text-transform: uppercase;
    text-align: center; font-size: 16px; font-weight: 900; letter-spacing: .2px;
    border-bottom: 1px solid var(--line);
  }
  .legend { font-size: 12px; font-weight: 700; color: var(--muted); margin-left: 12px; }
  .legend .sq { color: var(--blue); } .legend .dot { color: var(--green); }
  .timeline-wrap { overflow-x: auto; padding: 9px 10px 13px; }
  .timeline-grid {
    display: grid; min-width: 980px; align-items: stretch; font-size: 11px;
  }
  .tl-cell {
    min-height: 38px; display: flex; align-items: center; justify-content: center;
    border-bottom: 1px solid #edf2f6; border-right: 1px dotted #e4eaf0;
    position: relative;
  }
  .tl-head { min-height: 32px; font-weight: 900; color: var(--navy); }
  .tl-project { justify-content: flex-start; padding: 0 9px; font-weight: 700; font-size: 11px; }
  .tl-index {
    display: inline-grid; place-items: center; flex: 0 0 21px; width: 21px; height: 21px;
    border-radius: 50%; background: var(--navy); color: white; margin-right: 8px; font-size: 10px;
  }
  .mark-sent { width: 10px; height: 10px; background: var(--blue); box-shadow: 0 0 0 2px #d9ecfa; }
  .mark-return { width: 11px; height: 11px; border-radius: 50%; background: var(--green); box-shadow: 0 0 0 2px #e3f5df; }
  .mark-both { display: flex; gap: 3px; align-items: center; }
  .status {
    display: inline-flex; align-items: center; justify-content: center; gap: 5px;
    border-radius: 999px; padding: 5px 10px; font-size: 11px; font-weight: 900;
    white-space: nowrap;
  }
  .status-done { background: #edf8e8; color: #398029; border: 1px solid #cce9c2; }
  .status-partial { background: #fff6e5; color: #bf7412; border: 1px solid #f3d79f; }
  .status-none { background: #ffeff1; color: #bd2e3b; border: 1px solid #f0bdc3; }
  .bottom-grid { display: grid; grid-template-columns: 1.13fr 1fr; gap: 12px; margin-top: 12px; }
  .summary-table { width: 100%; border-collapse: collapse; font-size: 12px; }
  .summary-table th { background: var(--navy); color: white; padding: 8px 7px; text-align: center; }
  .summary-table th:first-child, .summary-table td:first-child { text-align: left; }
  .summary-table td { padding: 7px; border-bottom: 1px solid #e5ecf2; text-align: center; }
  .summary-table tbody tr:nth-child(even) { background: #f7fafc; }
  .summary-name { font-weight: 700; color: var(--ink); }
  .insights { padding: 13px 16px; }
  .insights h2 { color: var(--teal); font-size: 17px; text-transform: uppercase; margin: 0 0 7px; }
  .insight { display: flex; gap: 10px; align-items: flex-start; padding: 10px 0; border-top: 1px dotted #ccdbe5; font-size: 12px; }
  .insight:first-of-type { border-top: 0; }
  .insight-icon { font-size: 19px; line-height: 1; }
  .footnote {
    margin-top: 13px; padding: 12px 14px; border-radius: 12px;
    background: #eef6fd; color: #37516f; font-size: 11px; line-height: 1.45;
    display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px;
  }
  .empty {
    padding: 32px; text-align: center; color: var(--muted); background: #fff;
    border: 1px solid var(--line); border-radius: 14px;
  }
  @media (max-width: 980px) {
    .kpi-grid { grid-template-columns: repeat(2, 1fr); }
    .bottom-grid { grid-template-columns: 1fr; }
    .footnote { grid-template-columns: 1fr; }
  }
  @media (max-width: 600px) {
    .block-container { padding: 8px; }
    .report-shell { padding: 12px; border-radius: 12px; }
    .report-head { align-items: flex-start; }
    .brand-mark { width: 48px; height: 48px; flex-basis: 48px; font-size: 25px; }
    .report-head h1 { font-size: 22px; }
    .report-head p { font-size: 13px; }
    .kpi-grid { grid-template-columns: 1fr; }
    .live-strip { align-items: flex-start; flex-direction: column; }
  }
</style>
"""


@dataclass
class Entry:
    occurred_on: date
    movement: str
    quantity: float
    cliente: str
    display: str
    numero_display: str
    codigo_pintura: str
    color: str
    updated_at: datetime


@dataclass
class Project:
    name: str
    sent_dates: list[date]
    return_dates: list[date]
    sent_day_count: int
    first_return_days: int | None
    conclusion_days: int | None
    status: str
    updated_at: datetime


def normalize(value: object) -> str:
    text = unicodedata.normalize("NFD", str(value or ""))
    return "".join(char for char in text if unicodedata.category(char) != "Mn").strip().upper()


def parse_date(value: object) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value or "").strip()
    for pattern in ("%d/%m/%y", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text[:10], pattern).date()
        except ValueError:
            pass
    return None


def parse_datetime(value: object, fallback: date) -> datetime:
    if isinstance(value, datetime):
        return value
    text = str(value or "").strip()
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return datetime.combine(fallback, datetime.min.time())


def movement_from_process(process: object) -> str | None:
    key = normalize(process)
    if "RETORNO" in key:
        return "retorno"
    if "ENVIO" in key or "REMESSA" in key:
        return "remessa"
    return None


def color_from_process(process: object) -> str:
    text = str(process or "").strip()
    color = re.sub(r"^.*?\b(?:ENVIO|REMESSA|RETORNO)\b\s*[-:–—]?\s*", "", text, flags=re.I)
    return color.strip() or "SEM COR"


def number_value(value: object) -> float:
    try:
        result = float(str(value or "0").replace(",", "."))
        return result if result > 0 else 0
    except ValueError:
        return 0


def database_url() -> str:
    try:
        return str(st.secrets["DATABASE_URL"]).strip()
    except (KeyError, FileNotFoundError):
        return os.getenv("DATABASE_URL", "").strip()


@st.cache_data(ttl=55, show_spinner=False)
def load_rows(db_url: str) -> list[dict]:
    if not db_url:
        raise RuntimeError("DATABASE_URL ainda não foi configurada neste aplicativo.")
    with psycopg.connect(db_url, connect_timeout=12) as connection:
        with connection.cursor(row_factory=psycopg.rows.dict_row) as cursor:
            cursor.execute(
                """
                SELECT id, timestamp, cliente, display, numero_display, codigo_pintura,
                       processo, data_producao, quantidade, quantidade_total, created_at
                  FROM painting_entries
              ORDER BY timestamp DESC NULLS LAST, id DESC
                 LIMIT 5000
                """
            )
            return list(cursor.fetchall())


def build_projects(rows: list[dict], client_filter: str = "JDE") -> tuple[list[Project], list[date]]:
    parsed: list[Entry] = []
    wanted = normalize(client_filter)
    for row in rows:
        cliente = str(row.get("cliente") or "").strip()
        if wanted and wanted not in normalize(cliente):
            continue
        occurred_on = parse_date(row.get("data_producao"))
        movement = movement_from_process(row.get("processo"))
        if not occurred_on or not movement:
            continue
        parsed.append(
            Entry(
                occurred_on=occurred_on,
                movement=movement,
                quantity=number_value(row.get("quantidade")),
                cliente=cliente,
                display=re.sub(r"\s*-\s*lote.*$", "", str(row.get("display") or "").strip(), flags=re.I),
                numero_display=str(row.get("numero_display") or "").strip(),
                codigo_pintura=str(row.get("codigo_pintura") or "").strip(),
                color=color_from_process(row.get("processo")),
                updated_at=parse_datetime(row.get("timestamp") or row.get("created_at"), occurred_on),
            )
        )
    if not parsed:
        return [], []

    report_year = max(entry.occurred_on.year for entry in parsed)
    parsed = [entry for entry in parsed if entry.occurred_on.year == report_year]
    groups: dict[tuple[str, str, str, str, str], list[Entry]] = defaultdict(list)
    for entry in parsed:
        key = tuple(
            normalize(value)
            for value in (
                entry.cliente,
                entry.display,
                entry.numero_display,
                entry.codigo_pintura,
                entry.color,
            )
        )
        groups[key].append(entry)

    selected = sorted(groups.values(), key=lambda items: max(item.occurred_on for item in items), reverse=True)[:20]
    selected.sort(key=lambda items: min(item.occurred_on for item in items))
    projects: list[Project] = []
    for entries in selected:
        sent = [entry for entry in entries if entry.movement == "remessa"]
        returned = [entry for entry in entries if entry.movement == "retorno"]
        sent_dates = sorted({entry.occurred_on for entry in sent})
        return_dates = sorted({entry.occurred_on for entry in returned})
        sent_total = sum(entry.quantity for entry in sent)
        returned_total = sum(entry.quantity for entry in returned)
        if not returned:
            status = "Sem retorno"
        elif sent_total > 0 and returned_total < sent_total:
            status = "Parcial"
        else:
            status = "Concluído"
        reference = entries[0]
        client_label = re.sub(r"\s+COFFEE$", "", reference.cliente, flags=re.I)
        display_label = re.sub(r"^DISPLAY\s+", "", reference.display, flags=re.I)
        code_number = re.sub(r"^.*?-\s*", "", reference.codigo_pintura).lstrip("0") or reference.codigo_pintura
        name = " ".join(part for part in (client_label, display_label, reference.color, code_number) if part)
        first_sent = sent_dates[0] if sent_dates else None
        first_return = return_dates[0] if return_dates else None
        last_return = return_dates[-1] if return_dates else None
        projects.append(
            Project(
                name=name,
                sent_dates=sent_dates,
                return_dates=return_dates,
                sent_day_count=len(sent_dates),
                first_return_days=(first_return - first_sent).days if first_sent and first_return else None,
                conclusion_days=(last_return - first_sent).days if first_sent and last_return else None,
                status=status,
                updated_at=max(entry.updated_at for entry in entries),
            )
        )

    all_dates = [entry.occurred_on for entries in selected for entry in entries]
    start, end = min(all_dates), max(all_dates)
    if (end - start).days >= 45:
        start = end - timedelta(days=44)
    timeline = [start + timedelta(days=offset) for offset in range((end - start).days + 1)]
    return projects, timeline


def safe(value: object) -> str:
    return html.escape(str(value))


def status_html(status: str) -> str:
    if status == "Concluído":
        return '<span class="status status-done">✓ Concluído</span>'
    if status == "Parcial":
        return '<span class="status status-partial">◷ Parcial</span>'
    return '<span class="status status-none">× Sem retorno</span>'


def render_dashboard(projects: list[Project], timeline: list[date]) -> None:
    returned_projects = [project for project in projects if project.return_dates]
    avg_sent = mean(project.sent_day_count for project in projects) if projects else 0
    first_return_values = [
        project.first_return_days for project in returned_projects if project.first_return_days is not None
    ]
    conclusion_values = [
        project.conclusion_days for project in returned_projects if project.conclusion_days is not None
    ]
    avg_first = mean(first_return_values) if first_return_values else 0
    avg_conclusion = mean(conclusion_values) if conclusion_values else 0
    updated_at = max(project.updated_at for project in projects)
    report_year = timeline[-1].year

    kpis = [
        ("▣", len(projects), "projetos analisados"),
        ("↺", len(returned_projects), "projetos com retorno registrado"),
        ("▦", f"{avg_sent:.1f}".replace(".", ","), "média de dias de remessa"),
        ("◷", f"{avg_first:.1f}".replace(".", ","), "dias até o 1º retorno"),
        ("◷", f"{avg_conclusion:.1f}".replace(".", ","), "dias até a conclusão"),
    ]
    kpi_html = "".join(
        f'<article class="kpi"><div class="kpi-icon">{icon}</div>'
        f'<div><strong>{safe(value)}</strong><p>{safe(label)}</p></div></article>'
        for icon, value, label in kpis
    )

    columns = f"minmax(250px,1.8fr) repeat({len(timeline)}, minmax(40px,1fr)) 116px"
    timeline_cells = [
        '<div class="tl-cell tl-head tl-project">Projeto</div>',
        *[f'<div class="tl-cell tl-head">{day.strftime("%d/%m")}</div>' for day in timeline],
        '<div class="tl-cell tl-head">Status</div>',
    ]
    for index, project in enumerate(projects, 1):
        timeline_cells.append(
            f'<div class="tl-cell tl-project"><span class="tl-index">{index}</span>{safe(project.name)}</div>'
        )
        sent = set(project.sent_dates)
        returned = set(project.return_dates)
        for day in timeline:
            if day in sent and day in returned:
                mark = '<span class="mark-both"><i class="mark-sent"></i><i class="mark-return"></i></span>'
            elif day in sent:
                mark = '<i class="mark-sent"></i>'
            elif day in returned:
                mark = '<i class="mark-return"></i>'
            else:
                mark = ""
            timeline_cells.append(f'<div class="tl-cell">{mark}</div>')
        timeline_cells.append(f'<div class="tl-cell">{status_html(project.status)}</div>')

    summary_rows = []
    for index, project in enumerate(projects, 1):
        first_return = "—" if project.first_return_days is None else f"{project.first_return_days} dias"
        conclusion = "não concluído" if project.conclusion_days is None else f"{project.conclusion_days} dias"
        summary_rows.append(
            f"<tr><td class='summary-name'><span class='tl-index'>{index}</span>{safe(project.name)}</td>"
            f"<td>{project.sent_day_count}</td><td>{first_return}</td><td>{conclusion}</td>"
            f"<td>{status_html(project.status)}</td></tr>"
        )

    no_return = [project.name for project in projects if project.status == "Sem retorno"]
    partial = [project.name for project in projects if project.status == "Parcial"]
    longest_first = max(
        (project for project in returned_projects if project.first_return_days is not None),
        key=lambda project: project.first_return_days,
        default=None,
    )
    longest_cycle = max(
        (project for project in returned_projects if project.conclusion_days is not None),
        key=lambda project: project.conclusion_days,
        default=None,
    )
    insight_rows = [
        ("⚠", "Projetos sem retorno até a data-base", ", ".join(no_return) or "Nenhum"),
        ("◷", "Projetos com retorno parcial", ", ".join(partial) or "Nenhum"),
        (
            "▦",
            "Maior prazo até o 1º retorno",
            f"{longest_first.name}, com {longest_first.first_return_days} dias" if longest_first else "Sem dados",
        ),
        (
            "▥",
            "Maior ciclo de conclusão",
            f"{longest_cycle.name}, com {longest_cycle.conclusion_days} dias" if longest_cycle else "Sem dados",
        ),
    ]
    insights_html = "".join(
        f'<div class="insight"><span class="insight-icon">{icon}</span>'
        f'<div><strong>{safe(title)}:</strong> {safe(text)}.</div></div>'
        for icon, title, text in insight_rows
    )

    content = f"""
    <div class="report-shell">
      <header class="report-head">
        <div class="brand-mark">▰</div>
        <div>
          <h1>Relatório gerencial consolidado — pintura JDE</h1>
          <p>Controle de Remessas e Retornos por Projeto &nbsp;|&nbsp; Base: Formulário MTECH {report_year}</p>
        </div>
      </header>
      <div class="live-strip">
        <span><i class="live-dot"></i>Base ativa: painting_entries · dados reais</span>
        <span>Último lançamento: {updated_at.strftime("%d/%m/%Y %H:%M")}</span>
      </div>
      <section class="kpi-grid">{kpi_html}</section>
      <section class="panel">
        <div class="panel-title">
          Linha do tempo — remessas e retornos por projeto
          <span class="legend"><span class="sq">■</span> Remessa &nbsp; <span class="dot">●</span> Retorno</span>
        </div>
        <div class="timeline-wrap">
          <div class="timeline-grid" style="grid-template-columns:{columns}">
            {''.join(timeline_cells)}
          </div>
        </div>
      </section>
      <div class="bottom-grid">
        <section class="panel">
          <table class="summary-table">
            <thead><tr><th>Projeto</th><th>Dias Rem.</th><th>1º Ret.</th><th>Conclusão</th><th>Status</th></tr></thead>
            <tbody>{''.join(summary_rows)}</tbody>
          </table>
        </section>
        <aside class="panel insights">
          <h2>Insights / alertas</h2>
          {insights_html}
        </aside>
      </div>
      <div class="footnote">
        <div><strong>Dias Rem.</strong> = quantidade de datas com remessa registrada.</div>
        <div><strong>1º Ret.</strong> = dias corridos entre a primeira remessa e o primeiro retorno.</div>
        <div><strong>Conclusão</strong> = dias corridos entre a primeira remessa e o último retorno.</div>
      </div>
    </div>
    """
    st.markdown(content, unsafe_allow_html=True)


def main() -> None:
    st.markdown(CSS, unsafe_allow_html=True)
    try:
        raw_rows = load_rows(database_url())
        project_data, timeline_dates = build_projects(raw_rows)
        if not project_data:
            st.markdown(
                '<div class="empty"><h3>Nenhum lançamento JDE encontrado</h3>'
                '<p>A conexão funcionou, mas não há movimentos de envio ou retorno para o filtro atual.</p></div>',
                unsafe_allow_html=True,
            )
        else:
            render_dashboard(project_data, timeline_dates)
    except Exception as exc:
        st.error(f"Não foi possível sincronizar o painel com o Formulário MTECH: {exc}")

    components.html(
        "<script>setTimeout(function(){window.parent.location.reload();}, 60000);</script>",
        height=0,
    )


if __name__ == "__main__":
    main()
