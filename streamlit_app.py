from __future__ import annotations

import html
import math
import os
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from statistics import mean, pstdev

import psycopg
import streamlit as st

from dashboard_png import build_dashboard_png


st.set_page_config(
    page_title="Relatório Gerencial Consolidado — Pintura MTECH",
    page_icon="🎨",
    layout="wide",
    initial_sidebar_state="collapsed",
)


CSS = """
<style>
  :root {
    --navy: #082e69;
    --blue: #0879c9;
    --teal: #087f90;
    --green: #48b62f;
    --orange: #ef9b25;
    --red: #df3947;
    --ink: #17365f;
    --muted: #5e718d;
    --line: #d8e3ed;
    --soft: #f4f8fb;
  }
  .stApp { background: #eaf1f6; color: var(--ink); font-family: Arial, Aptos, "Segoe UI", sans-serif; }
  [data-testid="stHeader"], [data-testid="stToolbar"], footer { display: none !important; }
  .block-container { max-width: 1720px; padding: 10px 14px 26px; }
  .report-shell {
    background: #fff; border: 1px solid #cfdbe5; border-radius: 4px;
    box-shadow: 0 9px 28px rgba(11, 46, 83, .10); padding: 13px 15px 12px;
  }
  .report-head {
    display: grid; grid-template-columns: 78px minmax(0, 1fr) 245px;
    align-items: center; gap: 13px; min-height: 78px; margin-bottom: 4px;
  }
  .brand-mark { width: 70px; height: 66px; position: relative; color: var(--navy); }
  .spray-cup {
    position: absolute; left: 27px; top: 2px; width: 25px; height: 17px;
    border-radius: 2px 2px 5px 5px; background: var(--navy); transform: rotate(7deg);
  }
  .spray-cup::before {
    content: ""; position: absolute; left: -3px; top: -5px; width: 31px; height: 5px;
    border-radius: 2px; background: var(--navy);
  }
  .spray-body {
    position: absolute; left: 18px; top: 25px; width: 41px; height: 18px;
    border-radius: 4px 8px 5px 4px; background: var(--navy); transform: rotate(5deg);
  }
  .spray-body::before {
    content: ""; position: absolute; left: -15px; top: 3px; width: 18px; height: 7px;
    border-radius: 4px 1px 1px 4px; background: var(--navy);
  }
  .spray-handle {
    position: absolute; left: 24px; top: 39px; width: 14px; height: 28px;
    border-radius: 3px 3px 6px 6px; background: var(--navy); transform: skew(-13deg) rotate(5deg);
  }
  .spray-dots { position: absolute; left: 2px; top: 22px; font-size: 19px; letter-spacing: 1px; transform: rotate(-8deg); }
  .report-head h1 {
    margin: 0; color: var(--navy); font-size: clamp(27px, 2.35vw, 42px);
    line-height: 1; text-transform: uppercase; letter-spacing: -.7px; font-weight: 900;
  }
  .report-head p { color: var(--teal); margin: 6px 0 0; font-size: 17px; font-weight: 800; }
  .source-line { margin-top: 5px; color: #59708b; font-size: 10px; font-weight: 700; }
  .live-dot {
    display: inline-block; width: 7px; height: 7px; border-radius: 50%;
    background: var(--green); margin-right: 5px; box-shadow: 0 0 0 3px #dff3dc;
  }
  .method-note {
    border-left: 1px solid #d7e3ec; padding-left: 13px; color: #415776;
    font-size: 10px; line-height: 1.35; font-style: italic; font-weight: 700;
  }
  .method-note div + div { margin-top: 4px; }
  .toolbar-help { margin: 1px 0 5px; color: var(--muted); font-size: 11px; font-weight: 700; }
  div[data-testid="stPopover"] > button,
  div[data-testid="stDownloadButton"] > button {
    min-height: 42px; border: 1px solid #bfcfdd; border-radius: 9px;
    background: #fff; color: var(--navy); font-weight: 800; box-shadow: 0 3px 10px rgba(10, 50, 90, .06);
  }
  div[data-testid="stDownloadButton"] > button {
    border-color: var(--navy); background: var(--navy); color: #fff;
  }
  div[data-testid="stPopover"] > button:hover { border-color: var(--blue); color: var(--blue); }
  div[data-testid="stDownloadButton"] > button:hover { border-color: var(--blue); background: var(--blue); color: #fff; }
  [data-testid="stMultiSelect"] label, [data-testid="stDateInput"] label,
  [data-testid="stSlider"] label, [data-testid="stToggle"] label { color: var(--ink); font-weight: 800; }
  .selection-note {
    margin: 0 0 7px; padding: 6px 10px; border-radius: 7px; background: #f5f9fc;
    color: var(--muted); font-size: 10px; font-weight: 700; text-align: center;
  }
  .kpi-grid {
    display: grid; grid-template-columns: repeat(7, minmax(128px, 1fr));
    gap: 10px; margin: 5px 0 9px;
  }
  .kpi {
    min-height: 76px; background: linear-gradient(180deg, #fff, #f9fbfd);
    border: 1px solid var(--line); border-radius: 10px; padding: 10px;
    display: flex; align-items: center; gap: 9px; box-shadow: 0 3px 9px rgba(10, 50, 90, .07);
  }
  .kpi-icon {
    flex: 0 0 44px; width: 44px; height: 44px; border-radius: 10px;
    display: grid; place-items: center; font-size: 23px; color: var(--navy); background: #e7f1fa;
  }
  .kpi:nth-child(2) .kpi-icon { background: #ddf3f3; color: var(--teal); }
  .kpi:nth-child(3) .kpi-icon { background: #edf8e8; color: #4d8c2b; }
  .kpi strong { color: var(--navy); font-size: 28px; line-height: 1; }
  .kpi p { margin: 4px 0 0; color: var(--muted); font-size: 10px; line-height: 1.12; font-weight: 800; }
  .panel {
    background: #fff; border: 1px solid var(--line); border-radius: 10px; overflow: hidden; margin-top: 8px;
  }
  .panel-title {
    padding: 9px 13px; color: var(--navy); text-transform: uppercase;
    text-align: center; font-size: 14px; font-weight: 900; letter-spacing: .15px; border-bottom: 1px solid var(--line);
  }
  .legend { font-size: 10px; font-weight: 800; color: var(--muted); margin-left: 10px; }
  .legend .sq { color: var(--blue); } .legend .dot { color: var(--green); }
  .timeline-wrap { overflow-x: auto; padding: 6px 9px 8px; }
  .timeline-grid { display: grid; min-width: 980px; align-items: stretch; font-size: 10px; }
  .tl-cell {
    min-height: 31px; display: flex; align-items: center; justify-content: center;
    border-bottom: 1px solid #edf2f6; border-right: 1px dotted #e4eaf0;
    position: relative;
  }
  .tl-head { min-height: 27px; font-weight: 900; color: var(--navy); }
  .tl-project { justify-content: flex-start; padding: 0 8px; font-weight: 800; font-size: 10px; }
  .tl-index {
    display: inline-grid; place-items: center; flex: 0 0 20px; width: 20px; height: 20px;
    border-radius: 50%; background: var(--navy); color: white; margin-right: 7px; font-size: 9px;
  }
  .event-line {
    position: absolute; left: 0; right: 0; height: 2px; z-index: 1;
    pointer-events: none;
  }
  .event-line.line-sent { top: calc(50% - 3px); background: #51a9dc; }
  .event-line.line-return { top: calc(50% + 3px); background: #76c95a; }
  .event-line.line-start { left: 50%; }
  .event-line.line-end { right: 50%; }
  .mark-sent {
    position: relative; z-index: 3; width: 10px; height: 10px; background: var(--blue);
    box-shadow: 0 0 0 2px #d9ecfa;
  }
  .mark-return {
    position: relative; z-index: 3; width: 10px; height: 10px; border-radius: 50%;
    background: var(--green); box-shadow: 0 0 0 2px #e3f5df;
  }
  .mark-both { position: relative; z-index: 3; display: flex; gap: 3px; align-items: center; }
  .status {
    display: inline-flex; align-items: center; justify-content: center; gap: 5px;
    border-radius: 999px; padding: 4px 8px; font-size: 10px; font-weight: 900;
    white-space: nowrap;
  }
  .status-done { background: #edf8e8; color: #398029; border: 1px solid #cce9c2; }
  .status-partial { background: #fff6e5; color: #bf7412; border: 1px solid #f3d79f; }
  .status-none { background: #ffeff1; color: #bd2e3b; border: 1px solid #f0bdc3; }
  .bottom-grid {
    display: grid; grid-template-columns: 1.06fr .94fr; align-items: start;
    gap: 10px; margin-top: 2px;
  }
  .summary-table-wrap { width: 100%; overflow-x: auto; }
  .summary-table { width: 100%; min-width: 760px; border-collapse: collapse; font-size: 10px; }
  .summary-table th { background: var(--navy); color: white; padding: 6px 5px; text-align: center; }
  .summary-table th:first-child, .summary-table td:first-child { text-align: left; }
  .summary-table td { padding: 5px; border-bottom: 1px solid #e5ecf2; text-align: center; }
  .summary-table tbody tr:nth-child(even) { background: #f7fafc; }
  .summary-name { font-weight: 800; color: var(--ink); }
  .insights {
    position: relative; align-self: start; height: fit-content; min-height: 0;
    padding: 8px 14px 8px 82px; border: 1.5px solid var(--teal); border-radius: 9px;
  }
  .insights-head { display: flex; align-items: center; min-height: 30px; margin: 0; }
  .bulb-mark {
    position: absolute; left: 13px; top: 8px; width: 56px; height: 56px;
    display: grid; place-items: center; border-radius: 50%; background: var(--teal);
  }
  .bulb-core {
    position: relative; width: 20px; height: 24px; margin-top: -7px;
    border: 2px solid #fff; border-radius: 50% 50% 43% 43%;
  }
  .bulb-core::before {
    content: ""; position: absolute; left: 4px; bottom: -8px; width: 8px; height: 6px;
    border: 2px solid #fff; border-top: 0; border-radius: 0 0 3px 3px;
  }
  .bulb-core::after {
    content: ""; position: absolute; left: 4px; bottom: -12px; width: 12px; height: 2px;
    border-radius: 2px; background: #fff;
  }
  .insights h2 {
    color: var(--teal); font-size: 17px; line-height: 1.1;
    text-transform: uppercase; margin: 0; font-weight: 900;
  }
  .insight {
    display: grid; grid-template-columns: 31px minmax(0, 1fr); gap: 7px;
    align-items: center; min-height: 38px; padding: 5px 0;
    border-top: 1px dotted #ccdbe5; font-size: 10.5px; line-height: 1.28;
  }
  .insights-head + .insight { border-top: 0; }
  .insight-icon {
    display: grid; width: 27px; height: 27px; place-items: center;
    color: var(--teal); font-size: 21px; line-height: 1; font-weight: 900;
  }
  .insight-overview .insight-icon { color: var(--teal); }
  .insight-critical .insight-icon { color: #d92f45; }
  .insight-success .insight-icon, .insight-cycle .insight-icon,
  .insight-response .insight-icon { color: #5a9b2f; }
  .insight-partial .insight-icon { color: #e89a14; }
  .insight-rhythm .insight-icon { color: #078b98; }
  .footnote {
    position: relative; margin-top: 9px; padding: 9px 130px 9px 52px; border-radius: 8px;
    background: #eaf4fc; color: #37516f; font-size: 9px; line-height: 1.35;
    display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px 14px; overflow: hidden;
  }
  .footnote::before {
    content: "i"; position: absolute; left: 14px; top: 50%; transform: translateY(-50%);
    width: 25px; height: 25px; display: grid; place-items: center; border-radius: 50%;
    background: var(--navy); color: #fff; font-family: Georgia, serif; font-size: 17px; font-weight: 900;
  }
  .footer-brush {
    position: absolute; right: 18px; bottom: 13px; width: 86px; height: 18px;
    border-radius: 2px 10px 10px 2px; background: linear-gradient(90deg, #0c8f9e 0 40%, #0b4d82 40% 68%, #082e69 68%);
    transform: rotate(-7deg); opacity: .96;
  }
  .footer-brush::before {
    content: ""; position: absolute; left: -48px; top: 2px; width: 48px; height: 15px;
    clip-path: polygon(0 34%,100% 0,100% 100%,0 68%); background: #0b8e9d;
  }
  .empty {
    padding: 32px; text-align: center; color: var(--muted); background: #fff;
    border: 1px solid var(--line); border-radius: 14px;
  }
  @media (max-width: 1220px) {
    .kpi-grid { grid-template-columns: repeat(4, 1fr); }
    .report-head { grid-template-columns: 68px minmax(0, 1fr); }
    .method-note { display: none; }
  }
  @media (max-width: 980px) {
    .kpi-grid { grid-template-columns: repeat(2, 1fr); }
    .bottom-grid { grid-template-columns: 1fr; }
    .footnote { grid-template-columns: 1fr; }
  }
  @media (max-width: 600px) {
    .block-container { padding: 7px; }
    .report-shell { padding: 10px; }
    .report-head { grid-template-columns: 50px minmax(0,1fr); align-items: start; }
    .brand-mark { width: 48px; height: 52px; transform: scale(.72); transform-origin: top left; }
    .report-head h1 { font-size: 21px; }
    .report-head p { font-size: 13px; }
    .kpi-grid { grid-template-columns: 1fr; }
    .footnote { padding-right: 12px; padding-left: 45px; }
    .footer-brush { display: none; }
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
    first_sent: date | None
    last_activity: date
    sent_quantity: float
    returned_quantity: float
    completion_rate: float


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


def movement_from_process(process: object, machinery: object = "") -> str | None:
    key = normalize(process)
    if "RETORNO" in key:
        return "retorno"
    if "ENVIO" in key or "REMESSA" in key:
        return "remessa"
    machinery_key = normalize(machinery)
    if "RETORNO" in machinery_key:
        return "retorno"
    if "ENVIO" in machinery_key or "REMESSA" in machinery_key:
        return "remessa"
    return None


def color_from_process(process: object) -> str:
    text = str(process or "").strip()
    color = re.sub(r"^.*?\b(?:ENVIO|REMESSA|RETORNO)\b\s*[-:–—]?\s*", "", text, flags=re.I)
    if color == text and " - " in text:
        color = text.rsplit(" - ", maxsplit=1)[-1]
    return color.strip() or "SEM COR"


def number_value(value: object) -> float:
    try:
        result = float(str(value or "0").replace(",", "."))
        return result if math.isfinite(result) else 0
    except ValueError:
        return 0


def iso_week_count(start_date: date, end_date: date) -> int:
    """Count ISO weeks (Monday-Sunday) touched by an inclusive date range."""
    first_monday = start_date - timedelta(days=start_date.weekday())
    last_monday = end_date - timedelta(days=end_date.weekday())
    return max(1, ((last_monday - first_monday).days // 7) + 1)


def format_quantity(value: float) -> str:
    formatted = f"{value:,.1f}"
    return formatted.replace(",", "#").replace(".", ",").replace("#", ".")


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
                       maquinario, processo, data_producao, quantidade, quantidade_total, created_at
                  FROM painting_entries
              ORDER BY timestamp DESC NULLS LAST, id DESC
                """
            )
            return list(cursor.fetchall())


def project_name(entry: Entry) -> str:
    client_label = re.sub(r"\s+COFFEE$", "", entry.cliente, flags=re.I)
    display_label = re.sub(r"^DISPLAY\s+", "", entry.display, flags=re.I)
    code_number = re.sub(r"^.*?-\s*", "", entry.codigo_pintura).lstrip("0") or entry.codigo_pintura
    return " ".join(part for part in (client_label, display_label, entry.color, code_number) if part)


def build_projects(
    rows: list[dict],
    client_filter: str = "",
    selected_names: set[str] | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> tuple[list[Project], list[date]]:
    parsed: list[Entry] = []
    wanted = normalize(client_filter)
    for row in rows:
        cliente = str(row.get("cliente") or "").strip()
        if wanted and wanted not in normalize(cliente):
            continue
        if normalize(row.get("processo")).startswith("TINTA "):
            continue
        occurred_on = parse_date(row.get("data_producao"))
        movement = movement_from_process(row.get("processo"), row.get("maquinario"))
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

    selected = sorted(groups.values(), key=lambda items: max(item.occurred_on for item in items), reverse=True)
    selected.sort(key=lambda items: min(item.occurred_on for item in items))
    projects: list[Project] = []
    visible_entries: list[Entry] = []
    for all_entries in selected:
        name = project_name(all_entries[0])
        if selected_names is not None and name not in selected_names:
            continue
        entries = [
            entry
            for entry in all_entries
            if (start_date is None or entry.occurred_on >= start_date)
            and (end_date is None or entry.occurred_on <= end_date)
        ]
        if not entries:
            continue
        visible_entries.extend(entries)
        sent = [entry for entry in entries if entry.movement == "remessa"]
        returned = [entry for entry in entries if entry.movement == "retorno"]
        sent_dates = sorted({entry.occurred_on for entry in sent})
        return_dates = sorted({entry.occurred_on for entry in returned})
        sent_total = sum(entry.quantity for entry in sent)
        returned_total = sum(entry.quantity for entry in returned)
        if returned and not sent:
            status = "Parcial"
        elif not returned:
            status = "Sem retorno"
        elif sent_total > 0 and returned_total < sent_total:
            status = "Parcial"
        else:
            status = "Concluído"
        first_sent = sent_dates[0] if sent_dates else None
        first_return = return_dates[0] if return_dates else None
        last_return = return_dates[-1] if return_dates else None
        completion_rate = min(100.0, (returned_total / sent_total * 100)) if sent_total > 0 else 0
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
                first_sent=first_sent,
                last_activity=max(entry.occurred_on for entry in entries),
                sent_quantity=sent_total,
                returned_quantity=returned_total,
                completion_rate=completion_rate,
            )
        )

    if not visible_entries:
        return [], []
    start = start_date or min(entry.occurred_on for entry in visible_entries)
    end = end_date or max(entry.occurred_on for entry in visible_entries)
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


def connector_html(day: date, event_dates: list[date], movement: str) -> str:
    if len(event_dates) < 2:
        return ""
    first, last = event_dates[0], event_dates[-1]
    if day < first or day > last:
        return ""
    edge_class = ""
    if day == first:
        edge_class = " line-start"
    elif day == last:
        edge_class = " line-end"
    return f'<i class="event-line line-{movement}{edge_class}"></i>'


def render_header(report_year: int, updated_at: datetime) -> str:
    return f"""
      <header class="report-head">
        <div class="brand-mark" aria-hidden="true">
          <i class="spray-cup"></i><i class="spray-body"></i><i class="spray-handle"></i>
          <span class="spray-dots">···</span>
        </div>
        <div>
          <h1>Relatório gerencial consolidado — pintura MTECH</h1>
          <p>Controle de Remessas e Retornos por Projeto &nbsp;|&nbsp; Base: Formulário MTECH {report_year}</p>
          <div class="source-line"><i class="live-dot"></i>Base sincronizada automaticamente · último lançamento: {updated_at.strftime("%d/%m/%Y %H:%M")}</div>
        </div>
        <aside class="method-note">
          <div>*Da 1ª remessa até o 1º retorno registrado</div>
          <div>**Da 1ª remessa até o último retorno registrado</div>
          <div>Médias calculadas apenas para projetos com retorno registrado</div>
        </aside>
      </header>
    """


def smart_insights(projects: list[Project], timeline: list[date]) -> list[tuple[str, str, str]]:
    period_end = timeline[-1]
    returned_projects = [project for project in projects if project.return_dates]
    no_return = sorted(
        (project for project in projects if project.status == "Sem retorno"),
        key=lambda project: (period_end - (project.first_sent or project.last_activity)).days,
        reverse=True,
    )
    partial = sorted(
        (project for project in projects if project.status == "Parcial"),
        key=lambda project: project.completion_rate,
    )
    return_rate = (len(returned_projects) / len(projects) * 100) if projects else 0

    insights: list[tuple[str, str, str]] = [
        (
            "✦",
            "Leitura inteligente do recorte",
            f"{len(returned_projects)} de {len(projects)} projetos têm retorno no período "
            f"({return_rate:.0f}% de cobertura)",
        )
    ]

    if no_return:
        highest_risk = no_return[0]
        waiting_days = (period_end - (highest_risk.first_sent or highest_risk.last_activity)).days
        insights.append(
            (
                "⚠",
                "Prioridade de acompanhamento",
                f"{highest_risk.name} está sem retorno no recorte há {waiting_days} dias",
            )
        )
    else:
        insights.append(("✓", "Risco de ausência de retorno", "nenhum projeto selecionado está sem retorno"))

    if partial:
        lowest_completion = partial[0]
        if lowest_completion.sent_quantity <= 0:
            partial_message = (
                f"{lowest_completion.name} registrou retorno sem uma remessa no mesmo recorte; "
                "consulte o histórico acumulado do projeto"
            )
        else:
            partial_message = (
                f"{lowest_completion.name} atingiu aproximadamente {lowest_completion.completion_rate:.1f}% "
                "do volume enviado no período"
            )
        insights.append(
            (
                "◷",
                "Retorno parcial mais crítico",
                partial_message,
            )
        )

    weeks_in_period = iso_week_count(timeline[0], timeline[-1])
    sent_leader = max(projects, key=lambda project: project.sent_quantity)
    return_leader = max(projects, key=lambda project: project.returned_quantity)
    weekly_leaders: list[str] = []
    if sent_leader.sent_quantity > 0:
        weekly_leaders.append(
            f"maior envio médio: {sent_leader.name}, com "
            f"{format_quantity(sent_leader.sent_quantity / weeks_in_period)} peças/sem."
        )
    if return_leader.returned_quantity > 0:
        weekly_leaders.append(
            f"maior retorno médio: {return_leader.name}, com "
            f"{format_quantity(return_leader.returned_quantity / weeks_in_period)} peças/sem."
        )
    if weekly_leaders:
        insights.append(("⇅", "Ritmo semanal por projeto", "; ".join(weekly_leaders)))

    cycle_projects = [project for project in projects if project.conclusion_days is not None]
    if cycle_projects:
        cycles = [project.conclusion_days for project in cycle_projects if project.conclusion_days is not None]
        average_cycle = mean(cycles)
        deviation = pstdev(cycles) if len(cycles) > 1 else 0
        longest = max(cycle_projects, key=lambda project: project.conclusion_days or 0)
        threshold = average_cycle + max(2, deviation)
        title = "Prazo fora do padrão" if (longest.conclusion_days or 0) > threshold else "Maior ciclo do recorte"
        insights.append(
            (
                "▥",
                title,
                f"{longest.name}, com {longest.conclusion_days} dias; média filtrada de {average_cycle:.1f} dias",
            )
        )

    first_return_projects = [project for project in projects if project.first_return_days is not None]
    if first_return_projects:
        fastest = min(first_return_projects, key=lambda project: project.first_return_days or 0)
        insights.append(
            (
                "↗",
                "Melhor resposta no período",
                f"{fastest.name} registrou o primeiro retorno em {fastest.first_return_days} dias",
            )
        )
    return insights[:5]


def render_dashboard(
    projects: list[Project],
    timeline: list[date],
    report_year: int,
    updated_at: datetime,
) -> None:
    returned_projects = [project for project in projects if project.return_dates]
    avg_sent_days = mean(project.sent_day_count for project in projects) if projects else 0
    weeks_in_period = iso_week_count(timeline[0], timeline[-1])
    avg_weekly_sent = mean(project.sent_quantity / weeks_in_period for project in projects) if projects else 0
    avg_weekly_return = mean(project.returned_quantity / weeks_in_period for project in projects) if projects else 0
    first_return_values = [
        project.first_return_days for project in returned_projects if project.first_return_days is not None
    ]
    conclusion_values = [
        project.conclusion_days for project in returned_projects if project.conclusion_days is not None
    ]
    avg_first = mean(first_return_values) if first_return_values else 0
    avg_conclusion = mean(conclusion_values) if conclusion_values else 0
    kpis = [
        ("▣", len(projects), "projetos analisados"),
        ("↺", len(returned_projects), "projetos com retorno registrado"),
        ("▦", f"{avg_sent_days:.1f}".replace(".", ","), "média de dias de remessa"),
        ("⇧", format_quantity(avg_weekly_sent), "envio médio por projeto/sem."),
        ("⇩", format_quantity(avg_weekly_return), "retorno médio por projeto/sem."),
        ("◷", f"{avg_first:.1f}".replace(".", ","), "dias até o 1º retorno"),
        ("◷", f"{avg_conclusion:.1f}".replace(".", ","), "dias até a conclusão"),
    ]
    kpi_html = "".join(
        f'<article class="kpi"><div class="kpi-icon">{icon}</div>'
        f'<div><strong>{safe(value)}</strong><p>{safe(label)}</p></div></article>'
        for icon, value, label in kpis
    )

    columns = f"minmax(245px,1.8fr) repeat({len(timeline)}, minmax(36px,1fr)) 108px"
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
            connector = (
                connector_html(day, project.sent_dates, "sent")
                + connector_html(day, project.return_dates, "return")
            )
            if day in sent and day in returned:
                mark = '<span class="mark-both"><i class="mark-sent"></i><i class="mark-return"></i></span>'
            elif day in sent:
                mark = '<i class="mark-sent"></i>'
            elif day in returned:
                mark = '<i class="mark-return"></i>'
            else:
                mark = ""
            timeline_cells.append(f'<div class="tl-cell">{connector}{mark}</div>')
        timeline_cells.append(f'<div class="tl-cell">{status_html(project.status)}</div>')

    summary_rows = []
    for index, project in enumerate(projects, 1):
        first_return = "—" if project.first_return_days is None else f"{project.first_return_days} dias"
        conclusion = "não concluído" if project.conclusion_days is None else f"{project.conclusion_days} dias"
        weekly_sent = format_quantity(project.sent_quantity / weeks_in_period)
        weekly_return = format_quantity(project.returned_quantity / weeks_in_period)
        summary_rows.append(
            f"<tr><td class='summary-name'><span class='tl-index'>{index}</span>{safe(project.name)}</td>"
            f"<td>{project.sent_day_count}</td>"
            f"<td title='Base: {weeks_in_period} semana(s) ISO'>{weekly_sent}</td>"
            f"<td title='Base: {weeks_in_period} semana(s) ISO'>{weekly_return}</td>"
            f"<td>{first_return}</td><td>{conclusion}</td>"
            f"<td>{status_html(project.status)}</td></tr>"
        )

    insight_rows = smart_insights(projects, timeline)
    insight_classes = {
        "✦": "overview",
        "⚠": "critical",
        "✓": "success",
        "◷": "partial",
        "⇅": "rhythm",
        "▥": "cycle",
        "↗": "response",
    }
    insights_html = "".join(
        f'<div class="insight insight-{insight_classes.get(icon, "overview")}">'
        f'<span class="insight-icon" aria-hidden="true">{icon}</span>'
        f'<div><strong>{safe(title)}:</strong> {safe(text)}.</div></div>'
        for icon, title, text in insight_rows
    )

    content = f"""
    <div class="report-shell report-canvas" id="painel-pintura-exportavel">
      {render_header(report_year, updated_at)}
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
          <div class="summary-table-wrap">
            <table class="summary-table">
              <thead><tr><th>Projeto</th><th>Dias Rem.</th><th>Env./sem.</th><th>Ret./sem.</th><th>1º Ret.</th><th>Conclusão</th><th>Status</th></tr></thead>
              <tbody>{''.join(summary_rows)}</tbody>
            </table>
          </div>
        </section>
        <aside class="panel insights">
          <div class="insights-head"><span class="bulb-mark" aria-hidden="true"><i class="bulb-core"></i></span><h2>Insights / alertas</h2></div>
          {insights_html}
        </aside>
      </div>
      <div class="footnote">
        <div><strong>Dias Rem.</strong> = quantidade de datas com remessa registrada.</div>
        <div><strong>Env./sem.</strong> = quantidade líquida enviada ÷ semanas ISO do filtro.</div>
        <div><strong>Ret./sem.</strong> = quantidade líquida retornada ÷ semanas ISO do filtro.</div>
        <div><strong>Base semanal</strong> = projetos visíveis; cada semana ISO parcial conta como uma semana.</div>
        <div><strong>1º Ret.</strong> = dias corridos entre a primeira remessa e o primeiro retorno.</div>
        <div><strong>Conclusão</strong> = dias corridos entre a primeira remessa e o último retorno.</div>
        <i class="footer-brush" aria-hidden="true"></i>
      </div>
    </div>
    """
    st.markdown(content, unsafe_allow_html=True)


@st.fragment(run_every="60s")
def dashboard_fragment() -> None:
    try:
        raw_rows = load_rows(database_url())
        all_projects, all_timeline = build_projects(raw_rows)
        if not all_projects:
            st.markdown(
                '<div class="empty"><h3>Nenhum lançamento de pintura encontrado</h3>'
                '<p>A conexão funcionou, mas não há movimentos de envio ou retorno para o filtro atual.</p></div>',
                unsafe_allow_html=True,
            )
            return

        project_names = [project.name for project in all_projects]
        default_period = (
            max(all_timeline[0], all_timeline[-1] - timedelta(days=44)),
            all_timeline[-1],
        )
        filter_column, download_column = st.columns([2.7, 1])
        with filter_column:
            st.markdown('<div class="toolbar-help">CONTROLES DO RELATÓRIO</div>', unsafe_allow_html=True)
            with st.popover("⚙ Filtros de projetos e período", use_container_width=True):
                st.caption("A seleção recalcula os indicadores, a tabela, os alertas e a imagem para download.")
                selected_projects = st.multiselect(
                    "Projetos lançados",
                    options=project_names,
                    default=project_names,
                    key="painting_project_filter",
                    placeholder="Selecione um ou mais projetos",
                )
                selected_period = st.slider(
                    "Período analisado",
                    min_value=all_timeline[0],
                    max_value=all_timeline[-1],
                    value=default_period,
                    format="DD/MM/YYYY",
                    key="painting_period_slider",
                )
                start_date, end_date = selected_period

                exact_day_enabled = st.toggle(
                    "Selecionar um dia exato",
                    key="painting_exact_day_enabled",
                    help="Quando ativado, o dia escolhido substitui temporariamente o intervalo linear.",
                )
                effective_start, effective_end = start_date, end_date
                if exact_day_enabled:
                    exact_day_key = "painting_exact_day_filter"
                    stored_day = st.session_state.get(exact_day_key)
                    if isinstance(stored_day, datetime):
                        stored_day = stored_day.date()
                    if not isinstance(stored_day, date) or not start_date <= stored_day <= end_date:
                        st.session_state[exact_day_key] = end_date
                    exact_day = st.date_input(
                        "Dia exato",
                        min_value=start_date,
                        max_value=end_date,
                        format="DD/MM/YYYY",
                        key=exact_day_key,
                    )
                    effective_start = effective_end = exact_day

        project_data, timeline_dates = build_projects(
            raw_rows,
            selected_names=set(selected_projects),
            start_date=effective_start,
            end_date=effective_end,
        )
        period_summary = (
            f'dia exato de {effective_start.strftime("%d/%m/%Y")}'
            if exact_day_enabled
            else f'período de {effective_start.strftime("%d/%m/%Y")} a {effective_end.strftime("%d/%m/%Y")}'
        )
        if not project_data:
            with download_column:
                st.markdown('<div class="toolbar-help">EXPORTAÇÃO</div>', unsafe_allow_html=True)
                st.button("📷 Baixar foto do painel", disabled=True, use_container_width=True)
            st.markdown(
                '<div class="empty"><h3>Nenhum movimento encontrado para os filtros selecionados</h3>'
                '<p>Escolha outro projeto ou amplie o período analisado.</p></div>',
                unsafe_allow_html=True,
            )
            return
        report_updated_at = max(project.updated_at for project in all_projects)
        with download_column:
            st.markdown('<div class="toolbar-help">EXPORTAÇÃO</div>', unsafe_allow_html=True)
            try:
                report_png = build_dashboard_png(
                    project_data,
                    timeline_dates,
                    smart_insights(project_data, timeline_dates),
                    report_year=all_timeline[-1].year,
                    updated_at=report_updated_at,
                    width=1920,
                )
                st.download_button(
                    "📷 Baixar foto do painel",
                    data=report_png,
                    file_name=(
                        f"relatorio_pintura_{effective_start.strftime('%Y%m%d')}_"
                        f"{effective_end.strftime('%Y%m%d')}.png"
                    ),
                    mime="image/png",
                    use_container_width=True,
                )
            except Exception:
                st.button("📷 Imagem indisponível", disabled=True, use_container_width=True)
        st.markdown(
            f'<div class="selection-note">Recorte atual: {len(project_data)} de {len(all_projects)} projetos · '
            f'{period_summary} · atualização automática</div>',
            unsafe_allow_html=True,
        )
        render_dashboard(
            project_data,
            timeline_dates,
            all_timeline[-1].year,
            report_updated_at,
        )
    except Exception as exc:
        st.error(f"Não foi possível sincronizar o painel com o Formulário MTECH: {exc}")


def main() -> None:
    st.markdown(CSS, unsafe_allow_html=True)
    dashboard_fragment()


if __name__ == "__main__":
    main()
