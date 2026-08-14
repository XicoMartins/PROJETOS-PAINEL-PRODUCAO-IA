import unittest
from datetime import datetime
from unittest.mock import patch

from painting_references import ReferenceCatalog, reference_key
from streamlit_app import build_projects, render_dashboard


def row(process: str, movement: str, quantity: int) -> dict:
    return {
        "timestamp": "2026-08-01T08:00:00",
        "cliente": "CLIENTE",
        "display": "DISPLAY TESTE",
        "numero_display": "1",
        "codigo_pintura": "PR - 0001",
        "maquinario": movement,
        "processo": process,
        "data_producao": "01/08/2026",
        "quantidade": quantity,
        "quantidade_total": quantity,
        "created_at": "2026-08-01T08:00:00",
    }


class ProjectSetsTest(unittest.TestCase):
    def test_calculates_process_sets_and_uses_display_bottleneck(self):
        rows = [
            row("ENVIO - BASE - PRETO", "Envio à Pintura", 9),
            row("RETORNO - BASE - PRETO", "Retorno da Pintura", 8),
            row("ENVIO - CORPO - PRETO", "Envio à Pintura", 11),
            row("RETORNO - CORPO - PRETO", "Retorno da Pintura", 6),
        ]
        references = ReferenceCatalog({
            reference_key("DISPLAY TESTE", "BASE", "remessa"): 4,
            reference_key("DISPLAY TESTE", "BASE", "retorno"): 4,
            reference_key("DISPLAY TESTE", "CORPO", "remessa"): 5,
            reference_key("DISPLAY TESTE", "CORPO", "retorno"): 5,
        })

        projects, _ = build_projects(rows, references=references)

        self.assertEqual([(item.name, item.sent_sets, item.returned_sets) for item in projects[0].processes], [
            ("BASE", 2, 2),
            ("CORPO", 2, 1),
        ])
        self.assertEqual(projects[0].sent_sets, 2)
        self.assertEqual(projects[0].returned_sets, 1)

    def test_missing_reference_returns_none_and_warning(self):
        projects, _ = build_projects(
            [row("ENVIO - BASE - PRETO", "Envio à Pintura", 9)],
            references=ReferenceCatalog({}),
        )

        self.assertIsNone(projects[0].processes[0].sent_sets)
        self.assertIsNone(projects[0].sent_sets)
        self.assertTrue(any("BASE" in warning for warning in projects[0].reference_warnings))

    def test_rendered_summary_contains_set_columns_values_and_escaped_warning(self):
        references = ReferenceCatalog({
            reference_key("DISPLAY TESTE", "BASE", "remessa"): 4,
            reference_key("DISPLAY TESTE", "BASE", "retorno"): 4,
        })
        projects, timeline = build_projects([
            row("ENVIO - BASE - PRETO", "Envio à Pintura", 9),
            row("RETORNO - BASE - PRETO", "Retorno da Pintura", 8),
        ], references=references)
        with patch("streamlit_app.st.markdown") as markdown:
            render_dashboard(
                projects,
                timeline,
                2026,
                datetime(2026, 8, 1, 8),
                ("arquivo <sem QNT>",),
            )
        html = markdown.call_args.args[0]
        self.assertIn("Conj. enviados", html)
        self.assertIn("Conj. retornados", html)
        self.assertIn("arquivo &lt;sem QNT&gt;", html)
        self.assertNotIn("arquivo <sem QNT>", html)


if __name__ == "__main__":
    unittest.main()
