from __future__ import annotations

import html
from datetime import datetime
from decimal import Decimal

from weekly_control import (
    SAO_PAULO,
    ProjectIdentity,
    WeekPeriod,
    WeeklyComponent,
    WeeklyControl,
    WeeklySummary,
)


WEEKLY_CONTROL_CSS = """
<style>
  .weekly-control {
    --weekly-graphite: #202326;
    --weekly-graphite-soft: #34383d;
    --weekly-red: #bd1622;
    --weekly-wine: #7f1d2d;
    --weekly-teal: #0f716d;
    --weekly-yellow: #fff0a8;
    --weekly-blue: #dcecf8;
    --weekly-danger: #d9212d;
    --weekly-success: #dcefdc;
    --weekly-line: #d7dadd;
    --weekly-ink: #202326;
    background: #f5f6f6;
    border: 1px solid #cfd2d4;
    box-shadow: 0 12px 30px rgba(24, 28, 31, .12);
    color: var(--weekly-ink);
    font-family: Arial, Aptos, "Segoe UI", sans-serif;
    overflow: hidden;
  }
  .weekly-hero {
    background: var(--weekly-graphite);
    border-top: 6px solid var(--weekly-red);
    color: white;
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto;
    gap: 22px;
    padding: 19px 24px 17px;
  }
  .weekly-hero h1 {
    font-size: clamp(24px, 2.1vw, 35px);
    line-height: 1.05;
    margin: 0 0 6px;
    text-transform: uppercase;
  }
  .weekly-subtitle { color: #d8dcdf; font-size: 14px; font-weight: 700; }
  .weekly-project { align-self: center; max-width: 400px; text-align: right; }
  .weekly-project strong { display: block; font-size: 17px; }
  .weekly-project span { color: #cbd0d3; display: block; font-size: 12px; margin-top: 4px; }
  .weekly-project .weekly-updated { color: #f0f2f3; font-size: 11px; font-weight: 800; margin-top: 10px; }
  .weekly-panels {
    display: grid;
    gap: 14px;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    padding: 15px;
  }
  .weekly-panel { background: white; border: 1px solid var(--weekly-line); min-width: 0; }
  .weekly-panel-head {
    align-items: center;
    border-top: 7px solid var(--weekly-wine);
    display: flex;
    justify-content: space-between;
    gap: 14px;
    padding: 13px 14px 11px;
  }
  .weekly-panel-current .weekly-panel-head { border-color: var(--weekly-teal); }
  .weekly-panel-head h2 { font-size: 21px; margin: 0; text-transform: uppercase; }
  .weekly-panel-head .weekly-period { color: #51565a; font-size: 14px; margin: 5px 0 0; }
  .weekly-target {
    background: #f3e8ea;
    color: var(--weekly-wine);
    min-width: 104px;
    padding: 7px 10px;
    text-align: center;
  }
  .weekly-panel-current .weekly-target { background: #e1efed; color: var(--weekly-teal); }
  .weekly-target span { display: block; font-size: 9px; font-weight: 900; letter-spacing: .8px; }
  .weekly-target strong { display: block; font-size: 25px; line-height: 1; margin-top: 3px; }
  .weekly-table-wrap { overflow-x: auto; }
  .weekly-table { border-collapse: collapse; font-size: 11px; min-width: 610px; width: 100%; }
  .weekly-table th {
    background: var(--weekly-graphite-soft);
    border-right: 1px solid #50555a;
    color: white;
    font-size: 10px;
    letter-spacing: .35px;
    padding: 9px 7px;
    text-align: center;
  }
  .weekly-table th:first-child, .weekly-table td:first-child { text-align: left; }
  .weekly-table th[scope="row"] { font-size: 12px; font-weight: 900; }
  .weekly-table td {
    border-bottom: 1px solid #e4e6e7;
    border-right: 1px solid #e5e7e8;
    font-size: 14px;
    padding: 7px;
    text-align: center;
    vertical-align: middle;
  }
  .weekly-table tbody tr:nth-child(even):not(.weekly-paint-row) { background: #f7f8f8; }
  .weekly-table .weekly-remittance { background: var(--weekly-yellow); font-weight: 800; }
  .weekly-table .weekly-balance { background: var(--weekly-blue); font-weight: 800; }
  .weekly-table .weekly-target-balance { font-weight: 900; }
  .weekly-status { display: block; font-size: 8px; margin-top: 2px; text-transform: uppercase; }
  .weekly-pending { background: var(--weekly-danger); color: white; }
  .weekly-covered { background: var(--weekly-success); color: #165626; }
  .weekly-incomplete { background: #eef0f1; color: #60666a; }
  .weekly-paint-row { background: #741923; color: white; font-weight: 900; }
  .weekly-paint-row .weekly-remittance,
  .weekly-paint-row .weekly-balance { background: #8e2630; color: white; }
  .weekly-explanation {
    background: #f4f5f5;
    border-top: 1px solid var(--weekly-line);
    color: #575d61;
    font-size: 11px;
    font-weight: 700;
    padding: 9px 12px;
  }
  .weekly-summary {
    display: grid;
    gap: 7px;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    padding: 10px 12px 12px;
  }
  .weekly-summary div { background: #f4f5f5; padding: 8px; text-align: center; }
  .weekly-summary span { color: #666; display: block; font-size: 8px; font-weight: 900; text-transform: uppercase; }
  .weekly-summary strong { display: block; font-size: 17px; margin-top: 3px; }
  .weekly-footer {
    align-items: stretch;
    display: grid;
    gap: 12px;
    grid-template-columns: minmax(0, 1fr) auto;
    padding: 0 15px 15px;
  }
  .weekly-legends { background: white; border: 1px solid var(--weekly-line); padding: 11px 13px; }
  .weekly-legends span { display: inline-block; font-size: 11px; font-weight: 800; margin-right: 18px; }
  .weekly-dot { border-radius: 50%; display: inline-block; height: 9px; margin-right: 5px; width: 9px; }
  .weekly-dot-danger { background: var(--weekly-danger); }
  .weekly-dot-success { background: #62a469; }
  .weekly-next-action {
    background: var(--weekly-graphite);
    color: white;
    display: grid;
    font-size: 13px;
    font-weight: 900;
    min-width: 320px;
    padding: 11px 17px;
    place-items: center;
  }
  .weekly-warning { background: #fff4d6; border-top: 1px solid #e8cf80; color: #6b5010; font-size: 11px; padding: 9px 15px; }
  @media (max-width: 1366px) {
    .weekly-panels { gap: 10px; padding: 10px; }
    .weekly-panel-head h2 { font-size: 19px; }
    .weekly-table { font-size: 10px; min-width: 560px; }
    .weekly-table th[scope="row"] { font-size: 11px; }
  }
  @media (max-width: 700px) {
    .weekly-hero { grid-template-columns: 1fr; padding: 16px; }
    .weekly-project { max-width: none; text-align: left; }
    .weekly-panels { grid-template-columns: 1fr; }
    .weekly-footer { grid-template-columns: 1fr; }
    .weekly-next-action { min-width: 0; }
  }
</style>
"""


def format_pt_br(value: Decimal | int | None) -> str:
    if value is None:
        return "—"
    number = Decimal(value)
    if number == number.to_integral_value():
        return f"{int(number):,}".replace(",", ".")
    rendered = f"{number:,.3f}".rstrip("0").rstrip(".")
    return rendered.replace(",", "#").replace(".", ",").replace("#", ".")


def _safe(value: object) -> str:
    return html.escape(str(value or ""), quote=True)


def _date(period: WeekPeriod) -> str:
    return f"{period.start.strftime('%d/%m')}–{period.end.strftime('%d/%m/%Y')}"


def _balance_cell(value: Decimal | None, extra_class: str = "") -> str:
    if value is None:
        return (
            f'<td class="weekly-target-balance weekly-incomplete {extra_class}">—'
            '<span class="weekly-status">Dados incompletos</span></td>'
        )
    if value < 0:
        return (
            f'<td class="weekly-target-balance weekly-pending {extra_class}">'
            f'{format_pt_br(value)}<span class="weekly-status weekly-pending">Pendente</span></td>'
        )
    return (
        f'<td class="weekly-target-balance weekly-covered {extra_class}">'
        f'{format_pt_br(value)}<span class="weekly-status weekly-covered">Coberto</span></td>'
    )


def _row(row: WeeklyComponent, target_side: str, paint: bool = False) -> str:
    target_balance = (
        row.previous_balance if target_side == "previous" else row.current_balance
    )
    row_class = ' class="weekly-paint-row"' if paint else ""
    return (
        f"<tr{row_class}>"
        f'<th scope="row">{_safe(row.display_name)}</th>'
        f"<td>{format_pt_br(row.quantity_per_set)}</td>"
        f'<td class="weekly-remittance">{format_pt_br(row.total_remessa)}</td>'
        f"<td>{format_pt_br(row.total_retorno)}</td>"
        f'<td class="weekly-balance">{format_pt_br(row.painting_balance)}</td>'
        f"{_balance_cell(target_balance)}"
        "</tr>"
    )


def _summary(summary: WeeklySummary) -> str:
    return (
        '<div class="weekly-summary">'
        f'<div><span>Componentes da meta</span><strong>{format_pt_br(summary.total_components)}</strong></div>'
        f'<div><span>Peças pendentes</span><strong>{format_pt_br(summary.pending_pieces)}</strong></div>'
        f'<div><span>Referências pendentes</span><strong>{format_pt_br(summary.pending_references)}</strong></div>'
        "</div>"
    )


def _panel(
    title: str,
    period: WeekPeriod,
    target: int | None,
    target_header: str,
    explanation: str,
    target_side: str,
    control: WeeklyControl,
    current: bool,
) -> str:
    rows = "".join(_row(row, target_side) for row in control.components)
    rows += "".join(_row(row, target_side, paint=True) for row in control.paint_rows)
    summary = control.current_summary if current else control.previous_summary
    panel_class = "weekly-panel weekly-panel-current" if current else "weekly-panel"
    return f"""
    <article class="{panel_class}">
      <header class="weekly-panel-head">
        <div><h2>{_safe(title)}</h2><p class="weekly-period"><strong>{_safe(_date(period))}</strong></p></div>
        <div class="weekly-target"><span>META ACUMULADA</span><strong>{format_pt_br(target)}</strong></div>
      </header>
      <div class="weekly-table-wrap">
        <table class="weekly-table">
          <thead><tr>
            <th scope="col">COMPONENTE</th><th scope="col">QT/DY</th>
            <th scope="col">REMESSA</th><th scope="col">RETORNO</th>
            <th scope="col">SALDO</th><th scope="col">{_safe(target_header)}</th>
          </tr></thead>
          <tbody>{rows}</tbody>
        </table>
      </div>
      <div class="weekly-explanation">{_safe(explanation)}</div>
      {_summary(summary)}
    </article>
    """


def render_weekly_control_html(
    identity: ProjectIdentity,
    previous_period: WeekPeriod,
    current_period: WeekPeriod,
    control: WeeklyControl,
    updated_at: datetime | None,
) -> str:
    warnings = "".join(f"<div>{_safe(warning)}</div>" for warning in control.warnings)
    warning_html = (
        f'<div class="weekly-warning"><strong>Dados incompletos:</strong>{warnings}</div>'
        if warnings
        else ""
    )
    if updated_at is None:
        updated = "não disponível"
    else:
        localized = (
            updated_at.replace(tzinfo=SAO_PAULO)
            if updated_at.tzinfo is None
            else updated_at.astimezone(SAO_PAULO)
        )
        updated = localized.strftime("%d/%m/%Y %H:%M")
    project_title = f"{identity.display} · Pintura externa"
    identity_line = (
        f"{identity.cliente} · Nº {identity.numero_display} · {identity.codigo_pintura}"
    )
    body = f"""<section class="weekly-control" aria-labelledby="weekly-control-title">
      <header class="weekly-hero">
        <div>
          <h1 id="weekly-control-title">Controle semanal de remessas e retornos</h1>
          <div class="weekly-subtitle">Período operacional vigente</div>
        </div>
        <div class="weekly-project"><strong>{_safe(project_title)}</strong><span>{_safe(identity_line)}</span><span class="weekly-updated">Última atualização: {_safe(updated)}</span></div>
      </header>
      <div class="weekly-panels">
        {_panel('Retorno MULTIPINT', previous_period, control.previous_summary.target_sets, 'P/ FECHAR', 'Pendente de pintura / entrega na Mtech', 'previous', control, False)}
        {_panel('Remessa MTECH', previous_period, control.current_summary.target_sets, 'P/ ENVIAR', 'Pendente de envio da Mtech à Multipint', 'current', control, True)}
      </div>
      {warning_html}
      <footer class="weekly-footer">
        <div class="weekly-legends">
          <span><i class="weekly-dot weekly-dot-danger"></i>Pendência — saldo negativo</span>
          <span><i class="weekly-dot weekly-dot-success"></i>Quantidade coberta — saldo igual ou positivo</span>
        </div>
        <div class="weekly-next-action">Próxima ação: priorizar linhas em vermelho</div>
      </footer>
    </section>
    """
    return WEEKLY_CONTROL_CSS + "".join(line.strip() for line in body.splitlines())


def render_weekly_empty_html(title: str, message: str) -> str:
    return (
        WEEKLY_CONTROL_CSS
        + '<section class="weekly-control"><div class="weekly-warning">'
        + f"<strong>{_safe(title)}</strong><div>{_safe(message)}</div>"
        + "</div></section>"
    )
