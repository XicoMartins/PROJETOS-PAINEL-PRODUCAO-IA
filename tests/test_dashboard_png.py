from __future__ import annotations

import io
import unittest
from datetime import date, timedelta

from PIL import Image

from dashboard_png import _automatic_metrics, _normalize_projects, _weekly_projects
from dashboard_png import build_dashboard_png, generate_dashboard_png


class DashboardPngTests(unittest.TestCase):
    def test_generates_a_valid_png_from_simple_structures(self) -> None:
        start = date(2026, 7, 13)
        dates = [start + timedelta(days=offset) for offset in range(18)]
        metrics = [
            {"value": 3, "label": "projetos analisados"},
            {"value": 2, "label": "projetos com retorno registrado", "tone": "teal"},
            {"value": "2,7", "label": "média de dias de remessa", "tone": "green"},
            {"value": "5,5", "label": "dias até o 1º retorno"},
            {"value": "9,0", "label": "dias até a conclusão"},
        ]
        projects = [
            {
                "name": "JDE ARAMADO G PILÃO VERMELHO 406+70",
                "sent_dates": [dates[0], dates[1], dates[3]],
                "return_dates": [dates[7], dates[10], dates[14]],
                "sent_day_count": 3,
                "first_return_days": 7,
                "conclusion_days": 14,
                "status": "Concluído",
            },
            {
                "name": "JDE ARAMADO P PILÃO 211",
                "sent_dates": [dates[5], dates[8]],
                "return_dates": [dates[12]],
                "sent_day_count": 2,
                "first_return_days": 7,
                "conclusion_days": 7,
                "status": "Parcial",
            },
            {
                "name": "JDE ARAMADO G PRETO 322",
                "sent_dates": [dates[9]],
                "return_dates": [],
                "sent_day_count": 1,
                "status": "Sem retorno",
            },
        ]
        insights = [
            ("⚠", "Projetos sem retorno", "JDE ARAMADO G PRETO 322"),
            ("◷", "Projeto com retorno parcial", "JDE ARAMADO P PILÃO 211"),
            ("▥", "Maior ciclo", "JDE ARAMADO G PILÃO VERMELHO, com 14 dias"),
        ]

        content = generate_dashboard_png(metrics, projects, dates, insights, width=1280)

        self.assertTrue(content.startswith(b"\x89PNG\r\n\x1a\n"))
        with Image.open(io.BytesIO(content)) as image:
            self.assertEqual(image.format, "PNG")
            self.assertEqual(image.mode, "RGB")
            self.assertGreaterEqual(image.width, 1280)
            self.assertGreater(image.height, 650)

    def test_handles_long_text_weekly_columns_and_missing_dates(self) -> None:
        projects = [
            {
                "name": "PROJETO COM UM NOME EXCEPCIONALMENTE LONGO PARA VALIDAR QUEBRA E CORTE SEM ESTOURAR O QUADRO",
                "remessas": ["31/07/2026"],
                "retornos": ["03/08/2026"],
                "dias_remessa": 1,
                "envio_semana": "141,3",
                "retorno_semana": "51,3",
                "primeiro_retorno_dias": 3,
                "conclusao_dias": 3,
                "status": "Concluído",
            }
        ]
        content = generate_dashboard_png(
            {"projetos analisados": 1},
            projects,
            [],
            [
                {
                    "title": "Análise extensa",
                    "text": "Texto muito longo " * 35,
                    "kind": "warning",
                }
            ],
            width=1200,
        )

        with Image.open(io.BytesIO(content)) as image:
            self.assertEqual(image.width, 1200)
            self.assertGreater(image.height, 500)

        normalized = _normalize_projects(projects)
        self.assertEqual(normalized[0].sent_per_week, 141.3)
        self.assertEqual(normalized[0].return_per_week, 51.3)

    def test_handles_an_empty_filtered_result(self) -> None:
        content = generate_dashboard_png([], [], [], [], width=1200)
        with Image.open(io.BytesIO(content)) as image:
            self.assertEqual(image.format, "PNG")
            self.assertEqual(image.width, 1200)

    def test_build_wrapper_calculates_seven_metrics_and_weekly_rates(self) -> None:
        timeline = [date(2026, 7, 1) + timedelta(days=offset) for offset in range(14)]
        projects = _normalize_projects(
            [
                {
                    "name": "Projeto A",
                    "sent_dates": [timeline[0], timeline[1]],
                    "return_dates": [timeline[7]],
                    "sent_day_count": 2,
                    "first_return_days": 7,
                    "conclusion_days": 7,
                    "status": "Concluído",
                    "sent_quantity": 200,
                    "returned_quantity": 100,
                }
            ]
        )
        weekly = _weekly_projects(projects, timeline)
        metrics = _automatic_metrics(weekly)

        self.assertEqual(len(metrics), 7)
        # O intervalo toca três semanas ISO: 29/06, 06/07 e 13/07.
        self.assertAlmostEqual(weekly[0].sent_per_week, 200 / 3)
        self.assertAlmostEqual(weekly[0].return_per_week, 100 / 3)
        content = build_dashboard_png(projects, timeline, [], width=1200)
        self.assertTrue(content.startswith(b"\x89PNG"))


if __name__ == "__main__":
    unittest.main()

