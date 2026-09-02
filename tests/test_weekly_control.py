import unittest
from dataclasses import asdict
from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo


class WeeklyIdentityTest(unittest.TestCase):
    def test_project_key_changes_when_the_painting_identity_changes(self):
        try:
            from weekly_control import ProjectIdentity, project_key
        except ModuleNotFoundError:
            self.fail("weekly_control ainda não foi implementado")

        pg = ProjectIdentity(
            "FEMSA",
            "PG + ECONOMIA HIBRIDO",
            "26081000",
            "VM - 1000",
        )
        other_color = ProjectIdentity(
            "FEMSA",
            "PG + ECONOMIA HIBRIDO",
            "26081000",
            "PT - 1000",
        )

        self.assertEqual(
            project_key(pg),
            "3d787dcee76cb067ccb301246958353a34b5e29bf9726ffa40306b0b303672ae",
        )
        self.assertNotEqual(project_key(pg), project_key(other_color))


class WeeklyCalendarTest(unittest.TestCase):
    def test_periods_are_current_and_next_monday_to_friday_in_sao_paulo(self):
        from weekly_control import weekly_periods

        current, following = weekly_periods(
            datetime(2026, 8, 25, 12, tzinfo=ZoneInfo("America/Sao_Paulo"))
        )

        self.assertEqual(
            (current.start, current.end),
            (date(2026, 8, 24), date(2026, 8, 28)),
        )
        self.assertEqual(
            (following.start, following.end),
            (date(2026, 8, 31), date(2026, 9, 4)),
        )

    def test_normalizes_any_selected_day_to_its_monday_and_friday(self):
        from weekly_control import week_period_for_date

        period = week_period_for_date(date(2026, 8, 27))

        self.assertEqual(period.start, date(2026, 8, 24))
        self.assertEqual(period.end, date(2026, 8, 28))


class WeeklyNormalizationTest(unittest.TestCase):
    def test_process_takes_precedence_when_it_identifies_the_movement(self):
        from weekly_control import movement_from_fields

        self.assertEqual(
            movement_from_fields("BDJ CORPO RETORNO", "Envio à Pintura"),
            "retorno",
        )

    def test_machinery_identifies_movement_when_process_does_not(self):
        from weekly_control import movement_from_fields

        self.assertEqual(
            movement_from_fields("BDJ CORPO", "Envio à Pintura"),
            "remessa",
        )

    def test_component_key_removes_movement_accents_and_separators(self):
        from weekly_control import component_key

        self.assertEqual(
            component_key("ENVIO — Fechamento Móvel"),
            "FECHAMENTO MOVEL",
        )
        self.assertEqual(component_key("TINTA VM - ENVIO"), "TINTA VM")


class WeeklyCalculationTest(unittest.TestCase):
    def test_return_panel_p_to_send_uses_remittance_target_and_quantity_per_set(self):
        from weekly_control import (
            ComponentRequirement,
            MovementEntry,
            build_weekly_control,
        )

        instant = datetime(2026, 9, 2, 12, tzinfo=ZoneInfo("America/Sao_Paulo"))
        control = build_weekly_control(
            previous_target=668,
            current_target=835,
            requirements=(
                ComponentRequirement("CORPO", "CORPO", Decimal("1"), 1, True),
                ComponentRequirement("BANDEJA P", "BANDEJA P", Decimal("4"), 2, True),
                ComponentRequirement("SUPORTE", "SUPORTE", Decimal("2"), 3, True),
                ComponentRequirement("SEM REMESSA", "SEM REMESSA", Decimal("1"), 4, True),
            ),
            entries=(
                MovementEntry("CORPO", "remessa", Decimal("651"), instant),
                MovementEntry("BANDEJA P", "remessa", Decimal("2800"), instant),
                MovementEntry("SUPORTE", "remessa", Decimal("1010"), instant),
            ),
        )

        values = {
            row.component_key: asdict(row).get("return_remittance_balance")
            for row in control.components
        }
        self.assertEqual(values["CORPO"], Decimal("-17"))
        self.assertEqual(values["BANDEJA P"], Decimal("128"))
        self.assertEqual(values["SUPORTE"], Decimal("-326"))
        self.assertIsNone(values["SEM REMESSA"])

    def test_applies_previous_and_current_accumulated_target_formulas(self):
        from weekly_control import (
            ComponentRequirement,
            MovementEntry,
            build_weekly_control,
        )

        instant = datetime(2026, 8, 25, 12, tzinfo=ZoneInfo("America/Sao_Paulo"))
        control = build_weekly_control(
            previous_target=334,
            current_target=501,
            requirements=(
                ComponentRequirement("CORPO", "CORPO", Decimal("1"), 1, True),
                ComponentRequirement("TOLDO", "TOLDO", Decimal("1"), 2, True),
                ComponentRequirement(
                    "BANDEJA DIREITA P",
                    "BANDEJA DIREITA – P",
                    Decimal("4"),
                    3,
                    True,
                ),
                ComponentRequirement(
                    "SUPORTE FIXACAO DISPLAY",
                    "SUPORTE FIXAÇÃO DISPLAY",
                    Decimal("2"),
                    4,
                    True,
                ),
            ),
            entries=(
                MovementEntry("CORPO", "remessa", Decimal("463"), instant),
                MovementEntry("CORPO", "retorno", Decimal("317"), instant),
                MovementEntry("TOLDO", "remessa", Decimal("550"), instant),
                MovementEntry("TOLDO", "retorno", Decimal("390"), instant),
                MovementEntry("BANDEJA DIREITA P", "remessa", Decimal("1600"), instant),
                MovementEntry("BANDEJA DIREITA P", "retorno", Decimal("778"), instant),
                MovementEntry(
                    "SUPORTE FIXACAO DISPLAY", "remessa", Decimal("1010"), instant
                ),
                MovementEntry(
                    "SUPORTE FIXACAO DISPLAY", "retorno", Decimal("287"), instant
                ),
            ),
        )

        by_key = {row.component_key: row for row in control.components}
        self.assertEqual(by_key["CORPO"].previous_balance, Decimal("-17"))
        self.assertEqual(by_key["CORPO"].current_balance, Decimal("-38"))
        self.assertEqual(by_key["TOLDO"].previous_balance, Decimal("56"))
        self.assertEqual(by_key["TOLDO"].current_balance, Decimal("49"))
        self.assertEqual(
            by_key["BANDEJA DIREITA P"].previous_balance,
            Decimal("-558"),
        )
        self.assertEqual(
            by_key["BANDEJA DIREITA P"].current_balance,
            Decimal("-404"),
        )
        self.assertEqual(
            by_key["SUPORTE FIXACAO DISPLAY"].previous_balance,
            Decimal("-381"),
        )
        self.assertEqual(
            by_key["SUPORTE FIXACAO DISPLAY"].current_balance,
            Decimal("8"),
        )

    def test_distinguishes_missing_movement_from_zero_and_separates_tinta(self):
        from weekly_control import (
            ComponentRequirement,
            MovementEntry,
            build_weekly_control,
        )

        instant = datetime(2026, 8, 25, 12, tzinfo=ZoneInfo("America/Sao_Paulo"))
        control = build_weekly_control(
            previous_target=10,
            current_target=12,
            requirements=(
                ComponentRequirement("CHAVE", "CHAVE", Decimal("1"), 1, True),
            ),
            entries=(
                MovementEntry("CHAVE", "remessa", Decimal("0"), instant),
                MovementEntry("TINTA VM", "remessa", Decimal("25"), instant),
            ),
        )

        chave = control.components[0]
        self.assertEqual(chave.total_remessa, Decimal("0"))
        self.assertIsNone(chave.total_retorno)
        self.assertIsNone(chave.painting_balance)
        self.assertEqual(len(control.paint_rows), 1)
        self.assertEqual(control.paint_rows[0].display_name, "TINTA VM")
        self.assertEqual(control.paint_rows[0].total_remessa, Decimal("25"))
        self.assertIsNone(control.paint_rows[0].quantity_per_set)

    def test_summarizes_only_negative_component_balances(self):
        from weekly_control import (
            ComponentRequirement,
            MovementEntry,
            build_weekly_control,
        )

        instant = datetime(2026, 8, 25, 12, tzinfo=ZoneInfo("America/Sao_Paulo"))
        requirements = (
            ComponentRequirement("CORPO", "CORPO", Decimal("1"), 1, True),
            ComponentRequirement("TOLDO", "TOLDO", Decimal("1"), 2, True),
            ComponentRequirement("BDJ DIREITA P", "BDJ DIREITA P", Decimal("4"), 3, True),
            ComponentRequirement("BDJ ESQUERDA P", "BDJ ESQUERDA P", Decimal("4"), 4, True),
            ComponentRequirement("BDJ DIREITA G", "BDJ DIREITA G", Decimal("1"), 5, True),
            ComponentRequirement("BDJ ESQUERDA G", "BDJ ESQUERDA G", Decimal("1"), 6, True),
            ComponentRequirement("FECHAMENTO", "FECHAMENTO", Decimal("1"), 7, True),
            ComponentRequirement("PARACHOQUE", "PARACHOQUE", Decimal("1"), 8, True),
            ComponentRequirement("CHAVE", "CHAVE", Decimal("1"), 9, True),
            ComponentRequirement("SUPORTE", "SUPORTE", Decimal("2"), 10, True),
        )
        totals = {
            "CORPO": (463, 317),
            "TOLDO": (550, 390),
            "BDJ DIREITA P": (1600, 778),
            "BDJ ESQUERDA P": (1700, 865),
            "BDJ DIREITA G": (600, 400),
            "BDJ ESQUERDA G": (600, 400),
            "FECHAMENTO": (550, 281),
            "PARACHOQUE": (600, 350),
            "CHAVE": (310, 230),
            "SUPORTE": (1010, 287),
        }
        entries = tuple(
            movement
            for key, (sent, returned) in totals.items()
            for movement in (
                MovementEntry(key, "remessa", Decimal(sent), instant),
                MovementEntry(key, "retorno", Decimal(returned), instant),
            )
        )

        control = build_weekly_control(334, 501, requirements, entries)

        self.assertEqual(control.previous_summary.total_components, Decimal("5678"))
        self.assertEqual(control.current_summary.total_components, Decimal("8517"))
        self.assertEqual(control.previous_summary.pending_pieces, Decimal("1584"))
        self.assertEqual(control.previous_summary.pending_references, 6)
        self.assertEqual(control.current_summary.pending_pieces, Decimal("937"))
        self.assertEqual(control.current_summary.pending_references, 4)


class WeeklySubmissionTest(unittest.TestCase):
    def test_target_submission_requires_confirmation(self):
        from weekly_control import validate_target_submission

        with self.assertRaisesRegex(ValueError, "Confirme"):
            validate_target_submission(date(2026, 8, 27), 501, False)

    def test_target_submission_normalizes_the_week(self):
        from weekly_control import validate_target_submission

        period, target = validate_target_submission(date(2026, 8, 27), 501, True)

        self.assertEqual((period.start, period.end), (date(2026, 8, 24), date(2026, 8, 28)))
        self.assertEqual(target, 501)


if __name__ == "__main__":
    unittest.main()
