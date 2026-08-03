"""Renderizador independente do relatório gerencial de pintura em PNG.

O módulo não depende de Streamlit nem dos modelos internos do painel. A função
``generate_dashboard_png`` aceita dicionários, tuplas ou objetos simples e
devolve os bytes de uma imagem PNG pronta para download.

Exemplo mínimo::

    png = generate_dashboard_png(
        metrics=[
            {"value": 8, "label": "projetos analisados"},
            {"value": 6, "label": "projetos com retorno registrado"},
        ],
        projects=[
            {
                "name": "JDE ARAMADO G PILÃO VERMELHO 406+70",
                "sent_dates": [date(2026, 7, 13)],
                "return_dates": [date(2026, 7, 20)],
                "sent_day_count": 1,
                "first_return_days": 7,
                "conclusion_days": 7,
                "status": "Concluído",
            }
        ],
        timeline_dates=[date(2026, 7, 13), date(2026, 7, 20)],
        insights=[
            {
                "title": "Cobertura do período",
                "text": "1 de 1 projeto possui retorno registrado",
                "kind": "info",
            }
        ],
    )

Pillow é a única dependência de execução deste arquivo.
"""

from __future__ import annotations

import io
import math
import os
import re
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from pathlib import Path
from statistics import mean
from typing import Any, Iterable, Mapping, Sequence

from PIL import Image, ImageDraw, ImageFont


DateLike = date | datetime | str


@dataclass(frozen=True)
class Metric:
    """Indicador exibido na faixa superior."""

    value: Any
    label: str
    icon: str = ""
    tone: str = "blue"


@dataclass(frozen=True)
class ProjectRow:
    """Dados necessários para uma linha da linha do tempo e da tabela."""

    name: str
    sent_dates: tuple[date, ...] = ()
    return_dates: tuple[date, ...] = ()
    sent_day_count: int = 0
    first_return_days: int | None = None
    conclusion_days: int | None = None
    status: str = "Sem retorno"
    sent_per_week: float | None = None
    return_per_week: float | None = None
    sent_quantity: float | None = None
    returned_quantity: float | None = None


@dataclass(frozen=True)
class Insight:
    """Uma mensagem do quadro de insights/alertas."""

    title: str
    text: str
    kind: str = "info"


@dataclass(frozen=True)
class _Palette:
    navy: str = "#062D68"
    blue: str = "#0B82D2"
    teal: str = "#008B99"
    green: str = "#50BB32"
    orange: str = "#F29A24"
    red: str = "#E23C4A"
    ink: str = "#17375F"
    muted: str = "#5E7089"
    line: str = "#D7E3ED"
    grid: str = "#E7EEF4"
    canvas: str = "#F7F9FB"
    pale_blue: str = "#EAF4FC"
    pale_teal: str = "#E1F4F4"
    pale_green: str = "#EEF8E9"
    pale_orange: str = "#FFF5E4"
    pale_red: str = "#FFF0F2"


P = _Palette()


def _field(item: Any, *names: str, default: Any = None) -> Any:
    """Lê o primeiro campo existente de mapping, dataclass ou objeto comum."""

    for name in names:
        if isinstance(item, Mapping) and name in item:
            return item[name]
        if hasattr(item, name):
            return getattr(item, name)
    return default


def _date_value(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value or "").strip()
    if not text:
        return None
    for pattern in ("%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(text[:10], pattern).date()
        except ValueError:
            continue
    return None


def _dates(values: Any) -> tuple[date, ...]:
    if values is None:
        return ()
    if isinstance(values, (str, date, datetime)):
        values = [values]
    parsed = {_date_value(value) for value in values}
    return tuple(sorted(value for value in parsed if value is not None))


def _number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        result = float(value)
        return result if math.isfinite(result) else None
    try:
        text = str(value).strip()
        # Vírgula indica formato brasileiro; sem vírgula, o ponto é decimal.
        if "," in text:
            text = text.replace(".", "").replace(",", ".")
        result = float(text)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def _normalize_metrics(metrics: Mapping[str, Any] | Sequence[Any]) -> list[Metric]:
    if isinstance(metrics, Mapping):
        source: Iterable[Any] = [
            {"label": label, "value": value} for label, value in metrics.items()
        ]
    else:
        source = metrics

    result: list[Metric] = []
    tones = ("blue", "teal", "green", "blue", "blue", "teal", "green")
    for index, item in enumerate(source):
        if isinstance(item, Metric):
            result.append(item)
            continue
        if isinstance(item, (tuple, list)):
            value = item[0] if item else "—"
            label = item[1] if len(item) > 1 else "Indicador"
            icon = item[2] if len(item) > 2 else ""
            tone = item[3] if len(item) > 3 else tones[index % len(tones)]
        else:
            value = _field(item, "value", "valor", default="—")
            label = _field(item, "label", "rotulo", "title", default="Indicador")
            icon = _field(item, "icon", "icone", default="")
            tone = _field(item, "tone", "tom", default=tones[index % len(tones)])
        result.append(Metric(value=value, label=str(label), icon=str(icon), tone=str(tone)))
    return result


def _normalize_projects(projects: Sequence[Any]) -> list[ProjectRow]:
    result: list[ProjectRow] = []
    for item in projects:
        if isinstance(item, ProjectRow):
            result.append(item)
            continue
        sent = _dates(
            _field(item, "sent_dates", "remessa_dates", "remessas", "datas_remessa", default=())
        )
        returned = _dates(
            _field(item, "return_dates", "retorno_dates", "retornos", "datas_retorno", default=())
        )
        sent_days = _field(item, "sent_day_count", "dias_remessa", default=len(sent))
        first_return = _field(item, "first_return_days", "primeiro_retorno_dias")
        conclusion = _field(item, "conclusion_days", "conclusao_dias")
        result.append(
            ProjectRow(
                name=str(_field(item, "name", "projeto", "project", default="Projeto sem nome")),
                sent_dates=sent,
                return_dates=returned,
                sent_day_count=int(sent_days or 0),
                first_return_days=int(first_return) if first_return is not None else None,
                conclusion_days=int(conclusion) if conclusion is not None else None,
                status=str(_field(item, "status", default="Sem retorno")),
                sent_per_week=_number(
                    _field(
                        item,
                        "sent_per_week",
                        "envio_semana",
                        "env_sem",
                        "sent_weekly",
                        "weekly_sent_quantity",
                    )
                ),
                return_per_week=_number(
                    _field(
                        item,
                        "return_per_week",
                        "retorno_semana",
                        "ret_sem",
                        "return_weekly",
                        "weekly_return_quantity",
                    )
                ),
                sent_quantity=_number(
                    _field(item, "sent_quantity", "quantidade_enviada", "total_enviado")
                ),
                returned_quantity=_number(
                    _field(item, "returned_quantity", "quantidade_retornada", "total_retornado")
                ),
            )
        )
    return result


def _normalize_insights(insights: Sequence[Any]) -> list[Insight]:
    result: list[Insight] = []
    for item in insights:
        if isinstance(item, Insight):
            result.append(item)
            continue
        if isinstance(item, str):
            result.append(Insight("Análise", item, "info"))
            continue
        if isinstance(item, (tuple, list)):
            if len(item) >= 3:
                # Compatível com smart_insights: (ícone, título, texto).
                result.append(Insight(str(item[1]), str(item[2]), _kind_from_icon(str(item[0]))))
            elif len(item) == 2:
                result.append(Insight(str(item[0]), str(item[1]), "info"))
            elif item:
                result.append(Insight("Análise", str(item[0]), "info"))
            continue
        result.append(
            Insight(
                title=str(_field(item, "title", "titulo", default="Análise")),
                text=str(_field(item, "text", "texto", "message", default="")),
                kind=str(_field(item, "kind", "tipo", default="info")),
            )
        )
    return result


def _kind_from_icon(icon: str) -> str:
    if icon in {"⚠", "!", "alert", "warning"}:
        return "warning"
    if icon in {"✓", "check", "ok"}:
        return "success"
    if icon in {"◷", "clock", "partial"}:
        return "clock"
    if icon in {"▥", "chart"}:
        return "chart"
    return "info"


class _Fonts:
    def __init__(self) -> None:
        self.regular_path = self._find_font(False)
        self.bold_path = self._find_font(True)
        self._cache: dict[tuple[int, bool], ImageFont.ImageFont] = {}

    @staticmethod
    def _find_font(bold: bool) -> str | None:
        env_name = "DASHBOARD_FONT_BOLD" if bold else "DASHBOARD_FONT_REGULAR"
        candidates = [os.getenv(env_name, "")]
        if bold:
            candidates.extend(
                [
                    "C:/Windows/Fonts/arialbd.ttf",
                    "C:/Windows/Fonts/segoeuib.ttf",
                    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                    "DejaVuSans-Bold.ttf",
                ]
            )
        else:
            candidates.extend(
                [
                    "C:/Windows/Fonts/arial.ttf",
                    "C:/Windows/Fonts/segoeui.ttf",
                    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                    "DejaVuSans.ttf",
                ]
            )
        for candidate in candidates:
            if not candidate:
                continue
            try:
                ImageFont.truetype(candidate, 12)
                return candidate
            except OSError:
                continue
        return None

    def get(self, size: int, bold: bool = False) -> ImageFont.ImageFont:
        key = (max(7, int(size)), bold)
        if key not in self._cache:
            path = self.bold_path if bold else self.regular_path
            if path:
                self._cache[key] = ImageFont.truetype(path, key[0])
            else:
                self._cache[key] = ImageFont.load_default()
        return self._cache[key]


FONTS = _Fonts()


def _text_width(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> float:
    return draw.textlength(text, font=font)


def _ellipsize(
    draw: ImageDraw.ImageDraw,
    text: Any,
    font: ImageFont.ImageFont,
    max_width: float,
) -> str:
    value = re.sub(r"\s+", " ", str(text or "")).strip()
    if _text_width(draw, value, font) <= max_width:
        return value
    suffix = "…"
    while value and _text_width(draw, value + suffix, font) > max_width:
        value = value[:-1]
    return value.rstrip() + suffix


def _wrap(
    draw: ImageDraw.ImageDraw,
    text: Any,
    font: ImageFont.ImageFont,
    max_width: float,
    max_lines: int | None = None,
) -> list[str]:
    paragraphs = str(text or "").splitlines() or [""]
    lines: list[str] = []
    for paragraph in paragraphs:
        words = re.sub(r"\s+", " ", paragraph).strip().split(" ") if paragraph.strip() else [""]
        current = ""
        for word in words:
            candidate = word if not current else f"{current} {word}"
            if _text_width(draw, candidate, font) <= max_width:
                current = candidate
                continue
            if current:
                lines.append(current)
                current = ""
            if _text_width(draw, word, font) <= max_width:
                current = word
            else:
                fragment = ""
                for char in word:
                    if _text_width(draw, fragment + char, font) <= max_width:
                        fragment += char
                    else:
                        if fragment:
                            lines.append(fragment)
                        fragment = char
                current = fragment
        lines.append(current)
    if max_lines and len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = _ellipsize(draw, lines[-1] + "…", font, max_width)
    return lines


def _draw_centered(
    draw: ImageDraw.ImageDraw,
    box: tuple[float, float, float, float],
    text: Any,
    font: ImageFont.ImageFont,
    fill: str,
) -> None:
    left, top, right, bottom = box
    value = str(text)
    bbox = draw.textbbox((0, 0), value, font=font)
    width = bbox[2] - bbox[0]
    height = bbox[3] - bbox[1]
    draw.text(
        ((left + right - width) / 2, (top + bottom - height) / 2 - bbox[1]),
        value,
        font=font,
        fill=fill,
    )


def _panel(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    *,
    radius: int = 14,
    fill: str = "white",
    outline: str = P.line,
    shadow: bool = True,
) -> None:
    left, top, right, bottom = box
    if shadow:
        draw.rounded_rectangle(
            (left + 2, top + 4, right + 2, bottom + 5),
            radius=radius,
            fill="#E9EEF3",
        )
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=1)


def _draw_brand(draw: ImageDraw.ImageDraw, x: int, y: int, size: int) -> None:
    """Ícone vetorial simples de pistola de pintura, sem arquivo externo."""

    color = P.navy
    draw.rounded_rectangle((x + size * .24, y, x + size * .68, y + size * .18), radius=3, fill=color)
    draw.polygon(
        [
            (x + size * .18, y + size * .20),
            (x + size * .67, y + size * .23),
            (x + size * .75, y + size * .54),
            (x + size * .33, y + size * .60),
            (x + size * .12, y + size * .47),
        ],
        fill=color,
    )
    draw.polygon(
        [
            (x + size * .33, y + size * .52),
            (x + size * .54, y + size * .55),
            (x + size * .43, y + size * .95),
            (x + size * .18, y + size * .91),
        ],
        fill=color,
    )
    draw.rectangle((x + size * .65, y + size * .31, x + size * .92, y + size * .40), fill=color)
    for dx, dy, radius in ((.98, .28, .035), (1.06, .19, .025), (1.08, .39, .02), (1.16, .30, .018)):
        cx, cy, r = x + size * dx, y + size * dy, size * radius
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=color)


def _tone(metric: Metric) -> tuple[str, str]:
    name = metric.tone.casefold()
    if "green" in name or "verde" in name:
        return P.pale_green, "#568F2D"
    if "teal" in name or "turques" in name:
        return P.pale_teal, P.teal
    if "orange" in name or "laranja" in name:
        return P.pale_orange, P.orange
    if "red" in name or "vermel" in name:
        return P.pale_red, P.red
    return P.pale_blue, P.navy


def _draw_metric_icon(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    index: int,
    color: str,
    explicit: str = "",
) -> None:
    left, top, right, bottom = box
    cx, cy = (left + right) // 2, (top + bottom) // 2
    size = min(right - left, bottom - top)
    line = max(2, size // 18)
    if explicit:
        _draw_centered(draw, box, explicit, FONTS.get(int(size * .43), True), color)
        return
    kind = index % 7
    if kind == 0:  # prancheta
        draw.rounded_rectangle((cx - size*.22, cy - size*.30, cx + size*.22, cy + size*.30), radius=3, outline=color, width=line)
        draw.rectangle((cx - size*.09, cy - size*.36, cx + size*.09, cy - size*.26), fill=color)
        draw.rectangle((cx - size*.11, cy - size*.08, cx + size*.11, cy + size*.10), outline=color, width=line)
    elif kind == 1:  # retorno
        draw.arc((cx-size*.28, cy-size*.28, cx+size*.28, cy+size*.28), 25, 315, fill=color, width=line)
        draw.polygon([(cx-size*.31, cy-size*.05), (cx-size*.12, cy-size*.16), (cx-size*.12, cy+size*.05)], fill=color)
    elif kind == 2:  # calendário
        draw.rounded_rectangle((cx-size*.28, cy-size*.24, cx+size*.28, cy+size*.27), radius=3, outline=color, width=line)
        draw.line((cx-size*.28, cy-size*.10, cx+size*.28, cy-size*.10), fill=color, width=line)
        for dx in (-.13, .03, .18):
            draw.line((cx+size*dx, cy-size*.05, cx+size*dx, cy+size*.20), fill=color, width=1)
        draw.line((cx-size*.22, cy+size*.07, cx+size*.22, cy+size*.07), fill=color, width=1)
    elif kind in (3, 4):  # setas de volume
        direction = 1 if kind == 3 else -1
        draw.line((cx, cy-size*.25*direction, cx, cy+size*.25*direction), fill=color, width=line)
        tip_y = cy-size*.27*direction
        draw.polygon([(cx, tip_y), (cx-size*.14, tip_y+size*.15*direction), (cx+size*.14, tip_y+size*.15*direction)], fill=color)
    else:  # relógio
        draw.ellipse((cx-size*.29, cy-size*.29, cx+size*.29, cy+size*.29), outline=color, width=line)
        draw.line((cx, cy, cx, cy-size*.18), fill=color, width=line)
        draw.line((cx, cy, cx+size*.15, cy+size*.08), fill=color, width=line)


def _draw_status(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    status: str,
    *,
    compact: bool = False,
) -> None:
    normalized = status.casefold()
    if "concl" in normalized:
        label, fg, bg, border, symbol = "Concluído", "#3E842A", P.pale_green, "#C6E5B9", "check"
    elif "parcial" in normalized:
        label, fg, bg, border, symbol = "Parcial", "#B96C0E", P.pale_orange, "#F0CE90", "clock"
    else:
        label, fg, bg, border, symbol = "Sem retorno", "#C52F3D", P.pale_red, "#F0B8C0", "cross"
    font = FONTS.get(10 if compact else 11, True)
    max_w = box[2] - box[0] - 6
    label = _ellipsize(draw, label, font, max_w - 34)
    width = min(max_w, int(_text_width(draw, label, font) + 35))
    height = 24 if compact else 28
    cx, cy = (box[0] + box[2]) // 2, (box[1] + box[3]) // 2
    pill = (cx - width // 2, cy - height // 2, cx + width // 2, cy + height // 2)
    draw.rounded_rectangle(pill, radius=height // 2, fill=bg, outline=border, width=1)
    icon_x, icon_y = pill[0] + 11, cy
    icon_r = 6
    draw.ellipse((icon_x-icon_r, icon_y-icon_r, icon_x+icon_r, icon_y+icon_r), outline=fg, width=1)
    if symbol == "check":
        draw.line((icon_x-3, icon_y, icon_x-1, icon_y+3, icon_x+4, icon_y-3), fill=fg, width=2)
    elif symbol == "clock":
        draw.line((icon_x, icon_y, icon_x, icon_y-4), fill=fg, width=1)
        draw.line((icon_x, icon_y, icon_x+3, icon_y+2), fill=fg, width=1)
    else:
        draw.line((icon_x-3, icon_y-3, icon_x+3, icon_y+3), fill=fg, width=1)
        draw.line((icon_x+3, icon_y-3, icon_x-3, icon_y+3), fill=fg, width=1)
    bbox = draw.textbbox((0, 0), label, font=font)
    label_y = cy - (bbox[3] - bbox[1]) / 2 - bbox[1]
    draw.text((pill[0] + 22, label_y), label, font=font, fill=fg)


def _format_number(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:.1f}".replace(".", ",")


def _weekly_projects(
    projects: Sequence[ProjectRow],
    timeline: Sequence[date],
) -> list[ProjectRow]:
    """Garante valores semanais, usando os totais quando necessário."""

    if timeline:
        first_monday = timeline[0] - timedelta(days=timeline[0].weekday())
        last_monday = timeline[-1] - timedelta(days=timeline[-1].weekday())
        period_weeks = max(1, ((last_monday - first_monday).days // 7) + 1)
    else:
        period_weeks = 1.0
    result: list[ProjectRow] = []
    for project in projects:
        sent_per_week = project.sent_per_week
        return_per_week = project.return_per_week
        if sent_per_week is None and project.sent_quantity is not None:
            sent_per_week = project.sent_quantity / period_weeks
        if return_per_week is None and project.returned_quantity is not None:
            return_per_week = project.returned_quantity / period_weeks
        # O relatório atual sempre possui as duas colunas, inclusive com zero.
        result.append(
            replace(
                project,
                sent_per_week=sent_per_week if sent_per_week is not None else 0.0,
                return_per_week=return_per_week if return_per_week is not None else 0.0,
            )
        )
    return result


def _automatic_metrics(projects: Sequence[ProjectRow]) -> list[Metric]:
    returned = [project for project in projects if project.return_dates]
    first_returns = [
        project.first_return_days
        for project in projects
        if project.first_return_days is not None
    ]
    conclusions = [
        project.conclusion_days
        for project in projects
        if project.conclusion_days is not None
    ]
    return [
        Metric(len(projects), "projetos analisados", tone="blue"),
        Metric(len(returned), "projetos com retorno registrado", tone="teal"),
        Metric(
            _format_number(mean(project.sent_day_count for project in projects) if projects else 0),
            "média de dias de remessa",
            tone="green",
        ),
        Metric(
            _format_number(mean(project.sent_per_week or 0 for project in projects) if projects else 0),
            "envio médio por projeto/sem.",
            tone="blue",
        ),
        Metric(
            _format_number(mean(project.return_per_week or 0 for project in projects) if projects else 0),
            "retorno médio por projeto/sem.",
            tone="blue",
        ),
        Metric(
            _format_number(mean(first_returns) if first_returns else 0),
            "dias até o 1º retorno",
            tone="blue",
        ),
        Metric(
            _format_number(mean(conclusions) if conclusions else 0),
            "dias até a conclusão",
            tone="blue",
        ),
    ]


def _day_text(value: int | None, *, incomplete: bool = False) -> str:
    if value is None:
        return "não concluído" if incomplete else "—"
    return f"{value} dia" if value == 1 else f"{value} dias"


def _timeline_values(projects: Sequence[ProjectRow], supplied: Sequence[DateLike]) -> list[date]:
    values = {_date_value(item) for item in supplied}
    timeline = sorted(value for value in values if value is not None)
    if timeline:
        return timeline
    events = {
        event
        for project in projects
        for event in (*project.sent_dates, *project.return_dates)
    }
    return sorted(events)


def _fit_title_font(draw: ImageDraw.ImageDraw, text: str, max_width: int) -> ImageFont.ImageFont:
    for size in range(39, 23, -1):
        font = FONTS.get(size, True)
        if _text_width(draw, text, font) <= max_width:
            return font
    return FONTS.get(23, True)


def _insight_icon(draw: ImageDraw.ImageDraw, x: int, y: int, kind: str) -> None:
    key = kind.casefold()
    if key in {"warning", "alert", "risco"}:
        color = P.red
        draw.polygon([(x+11, y), (x+22, y+21), (x, y+21)], fill=color)
        _draw_centered(draw, (x+5, y+4, x+17, y+18), "!", FONTS.get(13, True), "white")
    elif key in {"success", "ok", "check"}:
        draw.ellipse((x, y, x+22, y+22), outline=P.green, width=2)
        draw.line((x+5, y+12, x+10, y+17, x+18, y+6), fill=P.green, width=2)
    elif key in {"clock", "partial", "tempo"}:
        draw.ellipse((x, y, x+22, y+22), outline=P.orange, width=2)
        draw.line((x+11, y+11, x+11, y+4), fill=P.orange, width=2)
        draw.line((x+11, y+11, x+17, y+14), fill=P.orange, width=2)
    elif key in {"chart", "grafico", "trend"}:
        for offset, height in ((0, 8), (6, 13), (12, 18), (18, 22)):
            draw.rectangle((x+offset, y+22-height, x+offset+4, y+22), fill="#5A9B2E")
        draw.line((x, y+15, x+8, y+10, x+14, y+12, x+22, y+2), fill="#5A9B2E", width=2)
    else:
        draw.ellipse((x, y, x+22, y+22), fill=P.teal)
        _draw_centered(draw, (x, y, x+22, y+22), "i", FONTS.get(14, True), "white")


def _draw_bulb_mark(draw: ImageDraw.ImageDraw, x: int, y: int) -> None:
    """Desenha a marca de lâmpada do quadro de insights."""

    draw.ellipse((x, y, x + 42, y + 42), fill=P.teal)
    draw.ellipse((x + 12, y + 8, x + 30, y + 27), outline="white", width=2)
    draw.line((x + 16, y + 24, x + 18, y + 30, x + 24, y + 30, x + 27, y + 24), fill="white", width=2)
    draw.line((x + 18, y + 33, x + 24, y + 33), fill="white", width=2)
    draw.line((x + 21, y + 3, x + 21, y + 7), fill="white", width=2)
    draw.line((x + 7, y + 12, x + 11, y + 15), fill="white", width=2)
    draw.line((x + 31, y + 15, x + 35, y + 12), fill="white", width=2)


def generate_dashboard_png(
    metrics: Mapping[str, Any] | Sequence[Any],
    projects: Sequence[Any],
    timeline_dates: Sequence[DateLike],
    insights: Sequence[Any],
    *,
    title: str = "RELATÓRIO GERENCIAL CONSOLIDADO — PINTURA MTECH",
    subtitle: str = "Controle de Remessas e Retornos por Projeto",
    base_label: str = "Base: Formulário MTECH",
    report_year: int | str | None = None,
    updated_at: datetime | str | None = None,
    width: int = 1600,
) -> bytes:
    """Gera o relatório completo e devolve bytes PNG.

    ``metrics`` aceita mapping ``{rótulo: valor}``, tuplas ``(valor, rótulo)``
    ou dicionários com ``value``, ``label``, ``icon`` e ``tone``.

    Cada projeto pode ser um dicionário ou objeto com ``name``, ``sent_dates``,
    ``return_dates``, ``sent_day_count``, ``first_return_days``,
    ``conclusion_days`` e ``status``. Os campos opcionais ``sent_per_week`` e
    ``return_per_week`` acrescentam as duas colunas semanais à tabela.

    Datas aceitam ``date``, ``datetime``, ``YYYY-MM-DD`` ou ``DD/MM/YYYY``.
    A imagem cresce horizontalmente quando o período é muito longo e
    verticalmente conforme a quantidade de projetos.
    """

    normalized_metrics = _normalize_metrics(metrics)
    normalized_projects = _normalize_projects(projects)
    normalized_insights = _normalize_insights(insights)
    timeline = _timeline_values(normalized_projects, timeline_dates)

    width = max(1200, int(width))
    day_count = max(1, len(timeline))
    # Conserva cada dia legível; filtros extensos produzem uma imagem mais larga.
    width = max(width, 570 + day_count * 27)
    margin = 22
    project_col = min(340, max(275, int(width * .185)))
    status_col = 130

    header_h = 88
    kpi_h = 94
    timeline_title_h = 45
    timeline_header_h = 31
    timeline_row_h = 32
    timeline_h = timeline_title_h + timeline_header_h + max(1, len(normalized_projects)) * timeline_row_h + 13
    table_header_h = 34
    table_row_h = 27
    table_h = table_header_h + max(1, len(normalized_projects)) * table_row_h + 4
    insight_row_h = 51
    insight_h = 54 + max(1, min(5, len(normalized_insights))) * insight_row_h + 8
    bottom_h = max(205, table_h, insight_h)
    foot_h = 78
    total_h = margin + header_h + kpi_h + 12 + timeline_h + 13 + bottom_h + 13 + foot_h + margin

    image = Image.new("RGB", (width, total_h), P.canvas)
    draw = ImageDraw.Draw(image)
    outer = (5, 5, width - 6, total_h - 6)
    draw.rounded_rectangle(outer, radius=6, fill="white", outline="#D9E3EC", width=1)

    # Cabeçalho.
    _draw_brand(draw, margin + 4, margin + 2, 64)
    note_w = 250
    title_x = margin + 91
    title_max = width - title_x - note_w - margin
    title_font = _fit_title_font(draw, title, title_max)
    draw.text((title_x, margin - 1), title, font=title_font, fill=P.navy)
    year = report_year if report_year is not None else (timeline[-1].year if timeline else datetime.now().year)
    subtitle_line = f"{subtitle}  |  {base_label} {year}".strip()
    subtitle_font = FONTS.get(19, True)
    draw.text((title_x, margin + 46), _ellipsize(draw, subtitle_line, subtitle_font, title_max), font=subtitle_font, fill=P.teal)
    note_x = width - note_w + 5
    note_font = FONTS.get(10, False)
    notes = [
        "* Da 1ª remessa até o 1º retorno registrado",
        "** Da 1ª remessa até o último retorno registrado",
        "Médias calculadas para projetos com retorno",
    ]
    note_y = margin + 2
    for note in notes:
        for line in _wrap(draw, note, note_font, note_w - margin, 2):
            draw.text((note_x, note_y), line, font=note_font, fill=P.ink)
            note_y += 13
        note_y += 2
    if updated_at:
        stamp = updated_at.strftime("%d/%m/%Y %H:%M") if isinstance(updated_at, datetime) else str(updated_at)
        draw.text((note_x, margin + 69), f"Atualizado: {stamp}", font=FONTS.get(9, False), fill=P.muted)

    # Indicadores.
    y = margin + header_h
    card_count = max(1, len(normalized_metrics))
    gap = 12
    cards_left = margin + 46
    cards_right = width - margin
    card_w = (cards_right - cards_left - gap * (card_count - 1)) / card_count
    if not normalized_metrics:
        normalized_metrics = [Metric("—", "Nenhum indicador disponível")]
    for index, metric in enumerate(normalized_metrics):
        left = int(cards_left + index * (card_w + gap))
        right = int(left + card_w)
        top, bottom = y + 2, y + kpi_h - 8
        _panel(draw, (left, top, right, bottom), radius=13)
        icon_bg, icon_fg = _tone(metric)
        icon_size = min(54, int(card_w * .25))
        icon_box = (left + 13, top + 16, left + 13 + icon_size, top + 16 + icon_size)
        draw.rounded_rectangle(icon_box, radius=12, fill=icon_bg)
        _draw_metric_icon(draw, icon_box, index, icon_fg, metric.icon)
        text_x = icon_box[2] + 13
        text_w = max(25, right - text_x - 9)
        value_font = FONTS.get(29 if card_count <= 7 else 25, True)
        draw.text((text_x, top + 12), _ellipsize(draw, metric.value, value_font, text_w), font=value_font, fill=P.navy)
        label_font = FONTS.get(10 if card_count <= 7 else 9, True)
        for line_no, line in enumerate(_wrap(draw, metric.label, label_font, text_w, 3)):
            draw.text((text_x, top + 51 + line_no * 11), line, font=label_font, fill=P.ink)

    # Linha do tempo.
    timeline_top = y + kpi_h + 4
    timeline_box = (margin, timeline_top, width - margin, timeline_top + timeline_h)
    _panel(draw, timeline_box, radius=14, shadow=False)
    title_font_small = FONTS.get(16, True)
    timeline_title = "LINHA DO TEMPO — REMESSAS E RETORNOS POR PROJETO"
    legend = "■ REMESSA   ● RETORNO"
    title_width = _text_width(draw, timeline_title, title_font_small)
    legend_font = FONTS.get(10, True)
    legend_width = _text_width(draw, legend, legend_font)
    group_width = title_width + 20 + legend_width
    group_x = max(margin + 8, (width - group_width) / 2)
    draw.text((group_x, timeline_top + 14), timeline_title, font=title_font_small, fill=P.navy)
    legend_x = group_x + title_width + 20
    draw.text((legend_x, timeline_top + 19), "■ REMESSA", font=legend_font, fill=P.blue)
    draw.text((legend_x + _text_width(draw, "■ REMESSA   ", legend_font), timeline_top + 19), "● RETORNO", font=legend_font, fill=P.green)
    draw.line((margin, timeline_top + timeline_title_h, width-margin, timeline_top + timeline_title_h), fill=P.line)

    grid_left = margin + 10
    grid_right = width - margin - 10
    header_top = timeline_top + timeline_title_h
    date_left = grid_left + project_col
    date_right = grid_right - status_col
    date_w = (date_right - date_left) / day_count
    header_font = FONTS.get(10, True)
    draw.text((grid_left + 12, header_top + 11), "Projeto", font=header_font, fill=P.navy)
    for index, day in enumerate(timeline):
        cell_left = date_left + index * date_w
        label = day.strftime("%d/%m")
        _draw_centered(draw, (cell_left, header_top, cell_left + date_w, header_top + timeline_header_h), label, FONTS.get(9, True), P.navy)
        draw.line((cell_left, header_top, cell_left, timeline_box[3]-8), fill=P.grid, width=1)
    _draw_centered(draw, (date_right, header_top, grid_right, header_top+timeline_header_h), "Status", header_font, P.navy)
    draw.line((date_right, header_top, date_right, timeline_box[3]-8), fill=P.grid, width=1)
    draw.line((grid_left, header_top+timeline_header_h, grid_right, header_top+timeline_header_h), fill=P.grid, width=1)

    timeline_index = {day: index for index, day in enumerate(timeline)}
    row_start = header_top + timeline_header_h
    if not normalized_projects:
        _draw_centered(
            draw,
            (grid_left, row_start, grid_right, row_start + timeline_row_h),
            "Nenhum projeto no recorte selecionado",
            FONTS.get(11, False),
            P.muted,
        )
    for row_index, project in enumerate(normalized_projects):
        top = row_start + row_index * timeline_row_h
        bottom = top + timeline_row_h
        if row_index % 2:
            draw.rectangle((grid_left, top, grid_right, bottom), fill="#FBFCFD")
        draw.line((grid_left, bottom, grid_right, bottom), fill=P.grid, width=1)
        circle = (grid_left + 9, top + 6, grid_left + 29, top + 26)
        draw.ellipse(circle, fill=P.navy)
        _draw_centered(draw, circle, row_index + 1, FONTS.get(9, True), "white")
        name_font = FONTS.get(10, True)
        name = _ellipsize(draw, project.name, name_font, project_col - 47)
        draw.text((grid_left + 36, top + 10), name, font=name_font, fill=P.ink)

        sent = [value for value in project.sent_dates if value in timeline_index]
        returned = [value for value in project.return_dates if value in timeline_index]
        center_y = (top + bottom) / 2
        if sent:
            first_x = date_left + (timeline_index[sent[0]] + .5) * date_w
            last_x = date_left + (timeline_index[sent[-1]] + .5) * date_w
            draw.line((first_x, center_y - 3, last_x, center_y - 3), fill="#55A9DB", width=2)
        if returned:
            first_x = date_left + (timeline_index[returned[0]] + .5) * date_w
            last_x = date_left + (timeline_index[returned[-1]] + .5) * date_w
            draw.line((first_x, center_y + 3, last_x, center_y + 3), fill="#73C75A", width=2)
        sent_set, return_set = set(sent), set(returned)
        for day in sent_set | return_set:
            cx = date_left + (timeline_index[day] + .5) * date_w
            both = day in sent_set and day in return_set
            if day in sent_set:
                sx = cx - 5 if both else cx
                draw.rectangle((sx-5, center_y-8, sx+5, center_y+2), fill="#D9EDFA")
                draw.rectangle((sx-4, center_y-7, sx+4, center_y+1), fill=P.blue)
            if day in return_set:
                rx = cx + 5 if both else cx
                draw.ellipse((rx-6, center_y-3, rx+6, center_y+9), fill="#E1F4DD")
                draw.ellipse((rx-5, center_y-2, rx+5, center_y+8), fill=P.green)
        _draw_status(draw, (int(date_right), top, grid_right, bottom), project.status, compact=True)

    # Tabela e insights.
    bottom_top = timeline_box[3] + 13
    gap = 14
    left_w = int((width - 2 * margin - gap) * .53)
    table_box = (margin, bottom_top, margin + left_w, bottom_top + bottom_h)
    insight_box = (table_box[2] + gap, bottom_top, width - margin, bottom_top + bottom_h)
    _panel(draw, table_box, radius=13, shadow=False)
    _panel(draw, insight_box, radius=13, shadow=False)

    weekly = any(
        project.sent_per_week is not None or project.return_per_week is not None
        for project in normalized_projects
    )
    if weekly:
        columns = [
            ("Projeto", .43), ("Dias Rem.", .09), ("Env./sem.", .10),
            ("Ret./sem.", .10), ("1º Ret.", .09), ("Conclusão", .10), ("Status", .13),
        ]
    else:
        columns = [
            ("Projeto", .48), ("Dias Rem.", .12), ("1º Ret.", .13),
            ("Conclusão", .14), ("Status", .18),
        ]
    total_ratio = sum(ratio for _, ratio in columns)
    widths = [(table_box[2] - table_box[0]) * ratio / total_ratio for _, ratio in columns]
    header_bottom = bottom_top + table_header_h
    draw.rounded_rectangle((table_box[0], bottom_top, table_box[2], header_bottom+3), radius=13, fill=P.navy)
    draw.rectangle((table_box[0], header_bottom-4, table_box[2], header_bottom+3), fill=P.navy)
    cursor = table_box[0]
    for col_index, ((label, _), col_w) in enumerate(zip(columns, widths)):
        if col_index:
            draw.line((cursor, bottom_top, cursor, header_bottom), fill="#2F5487", width=1)
        if col_index == 0:
            draw.text((cursor+10, bottom_top+11), label, font=FONTS.get(10, True), fill="white")
        else:
            _draw_centered(draw, (cursor, bottom_top, cursor+col_w, header_bottom), label, FONTS.get(9, True), "white")
        cursor += col_w
    for row_index, project in enumerate(normalized_projects):
        top = header_bottom + row_index * table_row_h
        bottom = top + table_row_h
        if row_index % 2:
            draw.rectangle((table_box[0]+1, top, table_box[2]-1, bottom), fill="#F7FAFC")
        draw.line((table_box[0], bottom, table_box[2], bottom), fill=P.line, width=1)
        values: list[Any] = [project.name, project.sent_day_count]
        if weekly:
            values.extend([_format_number(project.sent_per_week), _format_number(project.return_per_week)])
        values.extend([
            _day_text(project.first_return_days),
            _day_text(project.conclusion_days, incomplete=True),
            project.status,
        ])
        cursor = table_box[0]
        for col_index, (value, col_w) in enumerate(zip(values, widths)):
            if col_index == 0:
                circle = (cursor+9, top+5, cursor+26, top+22)
                draw.ellipse(circle, fill=P.navy)
                _draw_centered(draw, circle, row_index+1, FONTS.get(8, True), "white")
                font = FONTS.get(9, True)
                text = _ellipsize(draw, value, font, col_w-39)
                draw.text((cursor+32, top+9), text, font=font, fill=P.ink)
            elif col_index == len(values)-1:
                _draw_status(draw, (int(cursor), top, int(cursor+col_w), bottom), str(value), compact=True)
            else:
                _draw_centered(draw, (cursor, top, cursor+col_w, bottom), value, FONTS.get(9, False), P.ink)
            cursor += col_w
    if not normalized_projects:
        _draw_centered(draw, (table_box[0], header_bottom, table_box[2], header_bottom+table_row_h), "Nenhum dado no recorte", FONTS.get(10), P.muted)

    _draw_bulb_mark(draw, insight_box[0] + 15, bottom_top + 6)
    heading_x = insight_box[0] + 67
    draw.text((heading_x, bottom_top+18), "INSIGHTS / ALERTAS", font=FONTS.get(18, True), fill=P.teal)
    badge_x = heading_x + _text_width(draw, "INSIGHTS / ALERTAS", FONTS.get(18, True)) + 10
    badge = (int(badge_x), bottom_top+19, int(badge_x)+76, bottom_top+39)
    draw.rounded_rectangle(badge, radius=10, fill=P.pale_teal)
    _draw_centered(draw, badge, "IA ANALÍTICA", FONTS.get(8, True), P.teal)
    draw.line((insight_box[0]+16, bottom_top+51, insight_box[2]-16, bottom_top+51), fill=P.line)
    shown_insights = normalized_insights[:5]
    if not shown_insights:
        shown_insights = [Insight("Sem alertas", "Nenhuma análise disponível para o recorte atual", "success")]
    for index, insight in enumerate(shown_insights):
        top = bottom_top + 59 + index * insight_row_h
        if index:
            draw.line((insight_box[0]+16, top-6, insight_box[2]-16, top-6), fill=P.line)
        _insight_icon(draw, insight_box[0]+19, top+4, insight.kind)
        text_x = insight_box[0]+53
        text_w = insight_box[2]-text_x-18
        full = f"{insight.title}: {insight.text}".rstrip(": ")
        lines = _wrap(draw, full, FONTS.get(10, False), text_w, 3)
        for line_no, line in enumerate(lines):
            draw.text((text_x, top + line_no*13), line, font=FONTS.get(10, False), fill=P.ink)

    # Rodapé explicativo.
    foot_top = insight_box[3] + 13
    foot_box = (margin, foot_top, width-margin, foot_top+foot_h)
    draw.rounded_rectangle(foot_box, radius=12, fill=P.pale_blue)
    info_circle = (margin+13, foot_top+14, margin+39, foot_top+40)
    draw.ellipse(info_circle, fill=P.navy)
    _draw_centered(draw, info_circle, "i", FONTS.get(15, True), "white")
    footnotes = [
        ("Dias Rem.", "datas com remessa registrada."),
        ("Env./sem.", "volume enviado ÷ semanas ISO do filtro."),
        ("Ret./sem.", "volume retornado ÷ semanas ISO do filtro."),
        ("Base semanal", "cada semana ISO parcial conta como uma semana."),
        ("1º Ret.", "dias entre a primeira remessa e o primeiro retorno."),
        ("Conclusão", "dias entre a primeira remessa e o último retorno."),
    ]
    foot_start = margin + 54
    foot_gap = 18
    brush_space = 150
    foot_col = (width-margin-brush_space-foot_start-foot_gap*2) / 3
    for index, (label, text) in enumerate(footnotes):
        column = index % 3
        row = index // 3
        left = foot_start + column*(foot_col+foot_gap)
        y_text = foot_top + 10 + row * 29
        bold = FONTS.get(9, True)
        regular = FONTS.get(9, False)
        draw.text((left, y_text), f"{label} =", font=bold, fill=P.ink)
        x_text = left + _text_width(draw, f"{label} = ", bold)
        remaining = max(20, left+foot_col-x_text)
        first = True
        for line in _wrap(draw, text, regular, foot_col, 1):
            if first and _text_width(draw, line, regular) <= remaining:
                draw.text((x_text, y_text), line, font=regular, fill=P.ink)
            else:
                if first:
                    y_text += 14
                draw.text((left, y_text), line, font=regular, fill=P.ink)
                y_text += 14
            first = False

    # Pincel decorativo inspirado no rodapé do relatório de referência.
    brush_right = width - margin - 19
    brush_y = foot_top + 31
    draw.polygon(
        [
            (brush_right - 142, brush_y + 5),
            (brush_right - 91, brush_y - 6),
            (brush_right - 91, brush_y + 17),
            (brush_right - 142, brush_y + 12),
        ],
        fill=P.teal,
    )
    draw.rounded_rectangle(
        (brush_right - 94, brush_y - 7, brush_right - 54, brush_y + 18),
        radius=4,
        fill="#0B547F",
    )
    draw.rounded_rectangle(
        (brush_right - 57, brush_y - 5, brush_right, brush_y + 16),
        radius=10,
        fill=P.navy,
    )

    output = io.BytesIO()
    image.save(output, format="PNG", optimize=True, dpi=(144, 144))
    return output.getvalue()


def build_dashboard_png(
    projects: Sequence[Any],
    timeline: Sequence[DateLike],
    insights: Sequence[Any],
    *,
    report_year: int | str | None = None,
    updated_at: datetime | str | None = None,
    width: int = 1600,
    title: str = "RELATÓRIO GERENCIAL CONSOLIDADO — PINTURA MTECH",
    subtitle: str = "Controle de Remessas e Retornos por Projeto",
    base_label: str = "Base: Formulário MTECH",
) -> bytes:
    """Integração pronta para o painel atual, com os sete KPIs calculados.

    Esta é a função recomendada para o botão de download do Streamlit. Ela
    aceita diretamente os projetos filtrados e a linha do tempo usada na tela,
    calcula os indicadores do mesmo recorte e mantém as colunas ``Env./sem.`` e
    ``Ret./sem.``. Caso um projeto não tenha taxas semanais prontas, elas são
    derivadas de ``sent_quantity``/``returned_quantity`` e do período filtrado.
    """

    base_projects = _normalize_projects(projects)
    normalized_timeline = _timeline_values(base_projects, timeline)
    normalized_projects = _weekly_projects(base_projects, normalized_timeline)
    metrics = _automatic_metrics(normalized_projects)
    return generate_dashboard_png(
        metrics,
        normalized_projects,
        normalized_timeline,
        insights,
        title=title,
        subtitle=subtitle,
        base_label=base_label,
        report_year=report_year,
        updated_at=updated_at,
        width=width,
    )


def save_dashboard_png(
    path: str | os.PathLike[str],
    metrics: Mapping[str, Any] | Sequence[Any],
    projects: Sequence[Any],
    timeline_dates: Sequence[DateLike],
    insights: Sequence[Any],
    **options: Any,
) -> Path:
    """Atalho conveniente que grava o retorno de ``generate_dashboard_png``."""

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(
        generate_dashboard_png(metrics, projects, timeline_dates, insights, **options)
    )
    return destination


__all__ = [
    "build_dashboard_png",
    "Insight",
    "Metric",
    "ProjectRow",
    "generate_dashboard_png",
    "save_dashboard_png",
]
