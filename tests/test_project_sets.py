import os
import unittest
from datetime import datetime
from unittest.mock import patch

from painting_references import ReferenceCatalog, ReferenceSnapshot, reference_key
import streamlit_app
from streamlit_app import (
    build_projects,
    dashboard_fragment,
    load_reference_catalog_cached,
    render_dashboard,
)


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

    def test_dashboard_without_reference_warnings_keeps_insights_in_html_block(self):
        projects, timeline = build_projects([
            row("ENVIO - BASE - PRETO", "Envio à Pintura", 9),
            row("RETORNO - BASE - PRETO", "Retorno da Pintura", 8),
        ])

        with patch("streamlit_app.st.markdown") as markdown:
            render_dashboard(
                projects,
                timeline,
                2026,
                datetime(2026, 8, 1, 8),
                (),
            )

        html = markdown.call_args.args[0]
        bottom_grid = html.split('<div class="bottom-grid">', 1)[1].split("</aside>", 1)[0]
        self.assertIn('<aside class="panel insights">', bottom_grid)
        self.assertNotRegex(bottom_grid, r"\n[ \t]*\n")

    def test_transient_reference_failure_is_not_cached_indefinitely(self):
        snapshot = ReferenceSnapshot(r"D:\referencias-pintura", ())
        transient = ReferenceCatalog({}, ("arquivo bloqueado",))
        recovered = ReferenceCatalog({("DISPLAY", "BASE", "remessa"): 4})
        ttl = streamlit_app.REFERENCE_CATALOG_CACHE_TTL_SECONDS

        load_reference_catalog_cached.clear()
        try:
            with patch(
                "streamlit_app.load_reference_catalog",
                side_effect=[transient, recovered],
            ) as loader:
                first = load_reference_catalog_cached(
                    snapshot, streamlit_app.reference_catalog_cache_epoch(0)
                )
                before_expiry = load_reference_catalog_cached(
                    snapshot, streamlit_app.reference_catalog_cache_epoch(ttl - 0.001)
                )
                after_expiry = load_reference_catalog_cached(
                    snapshot, streamlit_app.reference_catalog_cache_epoch(ttl)
                )
        finally:
            load_reference_catalog_cached.clear()

        self.assertEqual(first, before_expiry)
        self.assertEqual(after_expiry.quantities, recovered.quantities)
        self.assertEqual(after_expiry.warnings, ())
        self.assertEqual(loader.call_count, 2)

    def test_reference_alert_limits_many_warnings_and_keeps_panel_content(self):
        projects, timeline = build_projects([row("ENVIO - BASE - PRETO", "Envio à Pintura", 9)])
        warnings = tuple(
            f"aviso {index} <arquivo>" for index in range(12)
        )

        with patch("streamlit_app.st.markdown") as markdown:
            render_dashboard(
                projects,
                timeline,
                2026,
                datetime(2026, 8, 1, 8),
                warnings,
            )

        html = markdown.call_args.args[0]
        alert = html.split('<div class="reference-alert">', 1)[1].split("</div>", 1)[0]
        self.assertIn("CLIENTE TESTE PRETO 1", html)
        self.assertIn("aviso 0 &lt;arquivo&gt;", alert)
        self.assertNotIn("aviso 0 <arquivo>", alert)
        self.assertIn("mais 8 avisos", alert)
        self.assertNotIn("aviso 11", alert)
        self.assertEqual(alert.count("<br>"), 4)

    def test_reference_scan_uses_environment_directory_override(self):
        override = r"D:\referencias-pintura"
        with (
            patch.dict(os.environ, {"MTECH_PAINTING_LISTS_DIR": override}),
            patch("streamlit_app.load_rows", return_value=[]),
            patch("streamlit_app.scan_reference_directory") as scan_directory,
            patch("streamlit_app.load_reference_catalog_cached", return_value=ReferenceCatalog({})),
            patch(
                "streamlit_app.load_github_reference_catalog_cached",
                return_value=ReferenceCatalog({}),
            ),
            patch("streamlit_app.st.markdown"),
        ):
            dashboard_fragment.__wrapped__()

        scan_directory.assert_called_once_with(override)

    def test_online_fallback_divides_femsa_item_totals_by_synced_qnt(self):
        catalog_loader = getattr(streamlit_app, "load_dashboard_reference_catalog", None)
        self.assertTrue(callable(catalog_loader), "fallback online de referências ainda não implementado")

        remote_catalog = ReferenceCatalog({
            reference_key(
                "PG + ECONOMIA HIBRIDO", "BDJ DIREITA MAIOR CORPO", "remessa"
            ): 4,
            reference_key(
                "PG + ECONOMIA HIBRIDO", "BDJ DIREITA MAIOR CORPO", "retorno"
            ): 4,
        })
        with (
            patch(
                "streamlit_app.scan_reference_directory",
                return_value=ReferenceSnapshot("S:\\indisponivel", (), ("unidade indisponível",)),
            ),
            patch(
                "streamlit_app.load_reference_catalog_cached",
                return_value=ReferenceCatalog({}, ("unidade indisponível",)),
            ),
            patch(
                "streamlit_app.load_github_reference_catalog_cached",
                return_value=remote_catalog,
            ) as remote_loader,
        ):
            references = catalog_loader("S:\\indisponivel")

        sent = row("ENVIO - BDJ DIREITA MAIOR CORPO - VERMELHO", "Envio à Pintura", 400)
        returned = row("RETORNO - BDJ DIREITA MAIOR CORPO - VERMELHO", "Retorno da Pintura", 179)
        for item in (sent, returned):
            item["cliente"] = "FEMSA"
            item["display"] = "PG + ECONOMIA HIBRIDO"
            item["codigo_pintura"] = "VM - 1000"

        projects, _ = build_projects([sent, returned], references=references)

        self.assertEqual(projects[0].processes[0].sent_quantity, 400)
        self.assertEqual(projects[0].processes[0].sent_sets, 100)
        self.assertEqual(projects[0].processes[0].returned_quantity, 179)
        self.assertEqual(projects[0].processes[0].returned_sets, 44)
        remote_loader.assert_called_once()


if __name__ == "__main__":
    unittest.main()
