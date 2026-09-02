import re
import unittest
from datetime import UTC, date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from weekly_control import (
    ComponentRequirement,
    MovementEntry,
    ProjectIdentity,
    WeekPeriod,
    build_weekly_control,
)


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
        self.assertIn("Retorno MULTIPINT", rendered)
        self.assertIn("Remessa MTECH", rendered)
        self.assertNotIn("Semana passada", rendered)
        self.assertNotIn("Semana atual", rendered)
        self.assertIn("P/ FECHAR", rendered)
        self.assertIn("P/ ENVIAR", rendered)
        self.assertEqual(rendered.count("<thead>"), 2)
        self.assertGreaterEqual(rendered.count('scope="col"'), 12)
        self.assertIn("Próxima ação: priorizar linhas em vermelho", rendered)
        self.assertIn("</style>\n<section", rendered)
        self.assertNotIn("</style>\n\n    <section", rendered)
        html_body = rendered.split("</style>", 1)[1]
        self.assertIsNone(re.search(r"(?m)^\s{4,}<", html_body))

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

    def test_return_panel_places_p_to_send_before_p_to_close_with_status_colors(self):
        from weekly_control_view import render_weekly_control_html

        instant = datetime(2026, 9, 2, 12, tzinfo=ZoneInfo("America/Sao_Paulo"))
        control = build_weekly_control(
            334,
            501,
            (
                ComponentRequirement("NEGATIVO", "NEGATIVO", Decimal("1"), 1, True),
                ComponentRequirement("POSITIVO", "POSITIVO", Decimal("1"), 2, True),
            ),
            (
                MovementEntry("NEGATIVO", "remessa", Decimal("300"), instant),
                MovementEntry("NEGATIVO", "retorno", Decimal("350"), instant),
                MovementEntry("POSITIVO", "remessa", Decimal("400"), instant),
                MovementEntry("POSITIVO", "retorno", Decimal("300"), instant),
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
        return_headers = re.findall(r'<th scope="col">([^<]+)</th>', tables[0])
        remittance_headers = re.findall(r'<th scope="col">([^<]+)</th>', tables[1])
        return_balances = re.findall(
            r'<td class="weekly-target-balance ([^"]*)">([^<]+)',
            tables[0],
        )

        self.assertEqual(
            return_headers,
            ["COMPONENTE", "QT/DY", "REMESSA", "RETORNO", "SALDO", "P/ ENVIAR", "P/ FECHAR"],
        )
        self.assertEqual(
            remittance_headers,
            ["COMPONENTE", "QT/DY", "REMESSA", "RETORNO", "SALDO", "P/ ENVIAR"],
        )
        self.assertIn("weekly-pending", return_balances[0][0])
        self.assertEqual(return_balances[0][1], "-34")
        self.assertIn("weekly-covered", return_balances[2][0])
        self.assertEqual(return_balances[2][1], "66")

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
