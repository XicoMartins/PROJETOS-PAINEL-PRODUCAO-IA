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

    def test_renders_two_semantic_week_panels_and_reference_copy(self):
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

        self.assertIn("MODELO 1 · EXECUTIVO INDUSTRIAL", rendered)
        self.assertIn("Controle semanal de remessas e retornos", rendered)
        self.assertIn("Semana passada", rendered)
        self.assertIn("Semana atual", rendered)
        self.assertIn("P/ FECHAR", rendered)
        self.assertIn("P/ ENVIAR", rendered)
        self.assertEqual(rendered.count("<thead>"), 2)
        self.assertGreaterEqual(rendered.count('scope="col"'), 12)
        self.assertIn("Próxima ação: priorizar linhas em vermelho", rendered)
        self.assertIn("</style>\n<section", rendered)
        self.assertNotIn("</style>\n\n    <section", rendered)

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


if __name__ == "__main__":
    unittest.main()
