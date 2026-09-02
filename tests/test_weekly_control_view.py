import re
import tempfile
import unittest
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from PIL import Image

from weekly_control import (
    ComponentRequirement,
    MovementEntry,
    ProjectIdentity,
    WeekPeriod,
    build_weekly_control,
)


def accessible_text(markup: str) -> str:
    with_brand_names = re.sub(
        r'<span[^>]*aria-label="([^"]+)"[^>]*></span>',
        r"\1",
        markup,
    )
    return re.sub(r"<[^>]+>", "", with_brand_names).strip()


class WeeklyControlViewTest(unittest.TestCase):
    def setUp(self):
        instant = datetime(2026, 8, 25, 12, tzinfo=ZoneInfo("America/Sao_Paulo"))
        self.identity = ProjectIdentity(
            "FEMSA",
            "PG + ECONOMIA HIBRIDO",
            "26081000",
            "VM - 1000",
        )
        self.previous = WeekPeriod(date(2026, 8, 17), date(2026, 8, 21))
        self.current = WeekPeriod(date(2026, 8, 24), date(2026, 8, 28))
        self.following = WeekPeriod(date(2026, 8, 31), date(2026, 9, 4))
        self.control = build_weekly_control(
            334,
            501,
            (
                ComponentRequirement("CORPO", "CORPO", Decimal("1"), 1, True),
                ComponentRequirement("CHAVE", "CHAVE", Decimal("1"), 2, True),
            ),
            (
                MovementEntry("CORPO", "remessa", Decimal("463"), instant),
                MovementEntry("CORPO", "retorno", Decimal("317"), instant),
                MovementEntry("TINTA VM", "remessa", Decimal("25"), instant),
            ),
        )
        self.updated_at = instant

    def test_renders_the_approved_operational_panel_titles(self):
        try:
            from weekly_control_view import render_weekly_control_html
        except ModuleNotFoundError:
            self.fail("weekly_control_view ainda não foi implementado")

        rendered = render_weekly_control_html(
            self.identity,
            self.previous,
            self.current,
            self.control,
            self.updated_at,
        )

        self.assertNotIn("MODELO 1 · EXECUTIVO INDUSTRIAL", rendered)
        self.assertIn("Controle semanal de remessas e retornos", rendered)
        self.assertIn('aria-label="Multipint"', rendered)
        self.assertIn('aria-label="MTech"', rendered)
        self.assertNotIn("Semana passada", rendered)
        self.assertNotIn("Semana atual", rendered)
        self.assertEqual(rendered.count("<thead>"), 2)
        self.assertGreaterEqual(rendered.count('scope="col"'), 12)
        self.assertIn("Próxima ação: priorizar linhas em vermelho", rendered)
        self.assertIn("</style>\n<section", rendered)
        self.assertNotIn("</style>\n\n    <section", rendered)
        html_body = rendered.split("</style>", 1)[1]
        self.assertIsNone(re.search(r"(?m)^\s{4,}<", html_body))

    def test_replaces_all_weekly_brand_names_with_large_proportional_logos(self):
        from weekly_control_view import render_weekly_control_html

        rendered = render_weekly_control_html(
            self.identity,
            self.previous,
            self.current,
            self.control,
            self.updated_at,
        )

        body_without_css = re.sub(r"<style>.*?</style>", "", rendered, flags=re.S)
        visible_text = re.sub(r"<[^>]+>", "", body_without_css)

        self.assertNotRegex(visible_text, r"(?i)\bmtech\b|\bmultipint\b")
        self.assertEqual(
            rendered.count(
                '<span class="weekly-brand-logo weekly-brand-logo-mtech"'
            ),
            5,
        )
        self.assertEqual(
            rendered.count(
                '<span class="weekly-brand-logo weekly-brand-logo-multipint"'
            ),
            3,
        )
        self.assertEqual(rendered.count("data:image/png;base64,"), 2)
        self.assertIn("background-size: contain", rendered)
        self.assertRegex(
            rendered,
            r"\.weekly-panel-head \.weekly-brand-logo\s*\{[^}]*height:\s*34px;",
        )
        self.assertIn("max-height: 34px", rendered)
        self.assertIn("max-width: 170px", rendered)
        self.assertRegex(
            rendered,
            r"\.weekly-table th \.weekly-brand-logo\s*\{[^}]*height:\s*20px;",
        )
        self.assertIn("max-height: 20px", rendered)
        self.assertIn("max-width: 78px", rendered)
        self.assertRegex(
            rendered,
            r"\.weekly-explanation \.weekly-brand-logo\s*\{[^}]*height:\s*18px;",
        )
        self.assertIn("max-height: 18px", rendered)
        self.assertIn("max-width: 68px", rendered)
        self.assertIn(
            ".weekly-panel-head .weekly-brand-logo { height: 28px; }",
            rendered,
        )
        self.assertIn(
            ".weekly-explanation .weekly-brand-logo { height: 16px; }",
            rendered,
        )
        for proportional_rule in (
            ".weekly-panel-head .weekly-brand-logo-mtech { width: 117px; }",
            ".weekly-panel-head .weekly-brand-logo-multipint { width: 85px; }",
            ".weekly-table th .weekly-brand-logo-mtech { width: 69px; }",
            ".weekly-table th .weekly-brand-logo-multipint { width: 50px; }",
            ".weekly-explanation .weekly-brand-logo-mtech { width: 62px; }",
            ".weekly-explanation .weekly-brand-logo-multipint { width: 45px; }",
            ".weekly-panel-head .weekly-brand-logo-mtech { width: 96px; }",
            ".weekly-panel-head .weekly-brand-logo-multipint { width: 70px; }",
            ".weekly-table th .weekly-brand-logo { height: 18px; }",
            ".weekly-table th .weekly-brand-logo-mtech { width: 62px; }",
            ".weekly-table th .weekly-brand-logo-multipint { width: 45px; }",
            ".weekly-explanation .weekly-brand-logo-mtech { width: 55px; }",
            ".weekly-explanation .weekly-brand-logo-multipint { width: 40px; }",
        ):
            self.assertIn(proportional_rule, rendered)

    def test_logo_assets_are_valid_proportional_and_web_sized(self):
        logo_dir = Path(__file__).resolve().parents[1] / "assets" / "logos"
        expected_ratios = {"mtech.png": 3.43, "multipint.png": 2.51}

        for filename, expected_ratio in expected_ratios.items():
            with self.subTest(filename=filename):
                payload = (logo_dir / filename).read_bytes()
                self.assertEqual(payload[:8], b"\x89PNG\r\n\x1a\n")
                with Image.open(logo_dir / filename) as logo:
                    self.assertEqual(logo.format, "PNG")
                    logo.load()
                    width, height = logo.size
                self.assertLessEqual(width, 480)
                self.assertLessEqual(height, 200)
                self.assertLessEqual(width * height, 100_000)
                self.assertLessEqual(len(payload), 150_000)
                self.assertAlmostEqual(width / height, expected_ratio, delta=0.05)

    def test_empty_state_does_not_depend_on_brand_assets(self):
        import weekly_control_view as view

        original_logo_dir = view.LOGO_DIR
        with tempfile.TemporaryDirectory() as empty_dir:
            view.LOGO_DIR = Path(empty_dir)
            view._logo_data_uri.cache_clear()
            try:
                try:
                    rendered = view.render_weekly_empty_html(
                        "Painel indisponível",
                        "Tente novamente.",
                    )
                except OSError as exc:
                    self.fail(f"O estado vazio depende dos arquivos de logo: {exc}")
            finally:
                view.LOGO_DIR = original_logo_dir
                view._logo_data_uri.cache_clear()

        self.assertIn("Painel indisponível", rendered)
        self.assertNotIn("data:image/png;base64,", rendered)

    def test_weekly_control_uses_brand_names_if_logo_files_are_missing(self):
        import weekly_control_view as view

        original_logo_dir = view.LOGO_DIR
        with tempfile.TemporaryDirectory() as empty_dir:
            view.LOGO_DIR = Path(empty_dir)
            view._logo_data_uri.cache_clear()
            try:
                try:
                    rendered = view.render_weekly_control_html(
                        self.identity,
                        self.previous,
                        self.current,
                        self.control,
                        self.updated_at,
                    )
                except OSError as exc:
                    self.fail(f"A recuperação sem logos falhou: {exc}")
            finally:
                view.LOGO_DIR = original_logo_dir
                view._logo_data_uri.cache_clear()

        self.assertIn("Retorno Multipint", rendered)
        self.assertIn("Remessa MTech", rendered)
        self.assertNotIn("data:image/png;base64,", rendered)

    def test_renders_week_periods_in_bold(self):
        from weekly_control_view import render_weekly_control_html

        rendered = render_weekly_control_html(
            self.identity,
            self.current,
            self.following,
            self.control,
            self.updated_at,
        )

        self.assertEqual(
            rendered.count(
                '<p class="weekly-period"><strong>24/08–28/08/2026</strong></p>'
            ),
            2,
        )

    def test_both_panels_show_current_week_while_remittance_uses_following_target(self):
        from weekly_control_view import render_weekly_control_html

        rendered = render_weekly_control_html(
            self.identity,
            self.current,
            self.following,
            self.control,
            self.updated_at,
        )

        self.assertEqual(rendered.count("24/08–28/08/2026"), 2)
        self.assertNotIn("31/08–04/09/2026", rendered)
        self.assertIn("<strong>334</strong>", rendered)
        self.assertIn("<strong>501</strong>", rendered)

    def test_table_numbers_render_at_fourteen_pixels(self):
        from weekly_control_view import render_weekly_control_html

        rendered = render_weekly_control_html(
            self.identity,
            self.current,
            self.following,
            self.control,
            self.updated_at,
        )

        self.assertRegex(
            rendered,
            r"\.weekly-table td\s*\{[^}]*font-size:\s*14px;",
        )

    def test_renders_missing_values_tinta_and_textual_statuses(self):
        from weekly_control_view import render_weekly_control_html

        rendered = render_weekly_control_html(
            self.identity,
            self.previous,
            self.current,
            self.control,
            self.updated_at,
        )

        self.assertIn('class="weekly-status weekly-pending"', rendered)
        self.assertIn("Pendente", rendered)
        self.assertIn("TINTA VM", rendered)
        self.assertIn('class="weekly-paint-row"', rendered)
        self.assertIn("—", rendered)
        self.assertLess(rendered.index("CHAVE"), rendered.index("TINTA VM"))

    def test_return_panel_places_a_enviar_mtech_before_a_retornar_multipint(self):
        from weekly_control_view import render_weekly_control_html

        instant = datetime(2026, 9, 2, 12, tzinfo=ZoneInfo("America/Sao_Paulo"))
        control = build_weekly_control(
            334,
            501,
            (
                ComponentRequirement("NEGATIVO", "NEGATIVO", Decimal("1"), 1, True),
                ComponentRequirement("POSITIVO", "POSITIVO", Decimal("1"), 2, True),
                ComponentRequirement("ZERO", "ZERO", Decimal("1"), 3, True),
                ComponentRequirement("INCOMPLETO", "INCOMPLETO", Decimal("1"), 4, True),
            ),
            (
                MovementEntry("NEGATIVO", "remessa", Decimal("300"), instant),
                MovementEntry("NEGATIVO", "retorno", Decimal("350"), instant),
                MovementEntry("POSITIVO", "remessa", Decimal("400"), instant),
                MovementEntry("POSITIVO", "retorno", Decimal("300"), instant),
                MovementEntry("ZERO", "remessa", Decimal("334"), instant),
                MovementEntry("ZERO", "retorno", Decimal("334"), instant),
            ),
        )

        rendered = render_weekly_control_html(
            self.identity,
            self.current,
            self.following,
            control,
            instant,
        )
        tables = re.findall(r'<table class="weekly-table">(.*?)</table>', rendered)
        return_headers = [
            accessible_text(header)
            for header in re.findall(r'<th scope="col">(.*?)</th>', tables[0])
        ]
        remittance_headers = [
            accessible_text(header)
            for header in re.findall(r'<th scope="col">(.*?)</th>', tables[1])
        ]
        return_balances = re.findall(
            r'<td class="weekly-target-balance ([^"]*)">([^<]+)',
            tables[0],
        )
        remittance_balances = re.findall(
            r'<td class="weekly-target-balance ([^"]*)">([^<]+)',
            tables[1],
        )
        panels = re.findall(r'<article class="[^"]*">(.*?)</article>', rendered)

        self.assertEqual(
            return_headers,
            [
                "COMPONENTE",
                "QT/DY",
                "REMESSA",
                "RETORNO",
                "SALDO",
                "A ENVIAR MTech",
                "A RETORNAR Multipint",
            ],
        )
        self.assertEqual(
            remittance_headers,
            ["COMPONENTE", "QT/DY", "REMESSA", "RETORNO", "SALDO", "A ENVIAR MTech"],
        )
        self.assertIn("weekly-pending", return_balances[0][0])
        self.assertEqual(return_balances[0][1], "-34")
        self.assertIn("weekly-covered", return_balances[2][0])
        self.assertEqual(return_balances[2][1], "66")
        self.assertIn("weekly-covered", return_balances[4][0])
        self.assertEqual(return_balances[4][1], "0")
        self.assertIn("weekly-incomplete", return_balances[6][0])
        self.assertEqual(return_balances[6][1], "—")
        self.assertIn("Coberto", tables[0])
        self.assertIn("Dados incompletos", tables[0])

        self.assertIn("weekly-pending", remittance_balances[0][0])
        self.assertEqual(remittance_balances[0][1], "-201")
        self.assertIn("weekly-pending", remittance_balances[1][0])
        self.assertEqual(remittance_balances[1][1], "-101")
        self.assertIn("weekly-incomplete", remittance_balances[3][0])
        self.assertEqual(remittance_balances[3][1], "—")

        self.assertIn(
            "<span>Componentes da meta</span><strong>1.336</strong>",
            panels[0],
        )
        self.assertIn(
            "<span>Peças pendentes</span><strong>34</strong>",
            panels[0],
        )
        self.assertIn(
            "<span>Referências pendentes</span><strong>1</strong>",
            panels[0],
        )
        self.assertIn(
            "<span>Componentes da meta</span><strong>2.004</strong>",
            panels[1],
        )
        self.assertIn(
            "<span>Peças pendentes</span><strong>469</strong>",
            panels[1],
        )
        self.assertIn(
            "<span>Referências pendentes</span><strong>3</strong>",
            panels[1],
        )

    def test_escapes_project_values_and_formats_numbers_in_pt_br(self):
        from weekly_control_view import format_pt_br, render_weekly_control_html

        unsafe = ProjectIdentity("<FEMSA>", self.identity.display, "26081000", "VM - 1000")
        rendered = render_weekly_control_html(
            unsafe,
            self.previous,
            self.current,
            self.control,
            self.updated_at,
        )

        self.assertIn("&lt;FEMSA&gt;", rendered)
        self.assertNotIn("<FEMSA>", rendered)
        self.assertEqual(format_pt_br(Decimal("8517")), "8.517")
        self.assertEqual(format_pt_br(None), "—")

    def test_updated_time_is_shown_in_sao_paulo(self):
        from weekly_control_view import render_weekly_control_html

        rendered = render_weekly_control_html(
            self.identity,
            self.previous,
            self.current,
            self.control,
            datetime(2026, 8, 25, 15, tzinfo=UTC),
        )

        self.assertIn("Última atualização: 25/08/2026 12:00", rendered)
        self.assertLess(
            rendered.index("Última atualização: 25/08/2026 12:00"),
            rendered.index('class="weekly-panels"'),
        )


if __name__ == "__main__":
    unittest.main()
