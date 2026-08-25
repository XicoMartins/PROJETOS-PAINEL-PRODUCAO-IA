import unittest
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import patch
from zoneinfo import ZoneInfo


class FakeCursor:
    def __init__(self, rows):
        self.rows = rows
        self.executions = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, sql, params=()):
        self.executions.append((sql, params))

    def fetchall(self):
        return list(self.rows)


class SequencedFakeCursor(FakeCursor):
    def __init__(self, responses):
        super().__init__([])
        self.responses = list(responses)

    def fetchall(self):
        return list(self.responses.pop(0))


class FakeConnection:
    def __init__(self, rows):
        self.cursor_instance = FakeCursor(rows)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def cursor(self, **kwargs):
        return self.cursor_instance


class SequencedFakeConnection(FakeConnection):
    def __init__(self, responses):
        self.cursor_instance = SequencedFakeCursor(responses)


class WriteFakeCursor(FakeCursor):
    def __init__(self, fail_on_execution=None):
        super().__init__([])
        self.fail_on_execution = fail_on_execution

    def execute(self, sql, params=()):
        super().execute(sql, params)
        if self.fail_on_execution == len(self.executions):
            raise RuntimeError("falha simulada")


class WriteFakeConnection(FakeConnection):
    def __init__(self, fail_on_execution=None):
        self.cursor_instance = WriteFakeCursor(fail_on_execution)
        self.committed = False
        self.rolled_back = False

    def __exit__(self, exc_type, exc, traceback):
        self.rolled_back = exc_type is not None
        return False

    def commit(self):
        self.committed = True


class WeeklyProjectRepositoryTest(unittest.TestCase):
    def test_lists_each_exact_painting_identity_in_recency_order(self):
        try:
            from weekly_control_data import list_painting_projects
        except ModuleNotFoundError:
            self.fail("weekly_control_data ainda não foi implementado")

        instant = datetime(2026, 8, 25, 12, tzinfo=ZoneInfo("America/Sao_Paulo"))
        connection = FakeConnection(
            [
                {
                    "cliente": "FEMSA",
                    "display": "PG + ECONOMIA HIBRIDO",
                    "numero_display": "26081000",
                    "codigo_pintura": "VM - 1000",
                    "last_movement_at": instant,
                },
                {
                    "cliente": "FEMSA",
                    "display": "PG + ECONOMIA HIBRIDO",
                    "numero_display": "26081000",
                    "codigo_pintura": "PT - 1000",
                    "last_movement_at": instant,
                },
            ]
        )

        with patch("weekly_control_data.psycopg.connect", return_value=connection):
            projects = list_painting_projects("postgresql://database")

        self.assertEqual(len(projects), 2)
        self.assertNotEqual(projects[0].key, projects[1].key)
        self.assertEqual(projects[0].identity.codigo_pintura, "VM - 1000")
        self.assertIn("PG + ECONOMIA HIBRIDO", projects[0].label)
        sql, params = connection.cursor_instance.executions[0]
        self.assertIn("FROM public.painting_entries", sql)
        self.assertIn("GROUP BY cliente, display, numero_display, codigo_pintura", sql)
        self.assertEqual(params, ())


class WeeklySourceRepositoryTest(unittest.TestCase):
    def test_loads_targets_requirements_and_only_the_selected_project_movements(self):
        from weekly_control import ProjectIdentity, WeekPeriod
        from weekly_control_data import load_weekly_source

        instant = datetime(2026, 8, 25, 12, tzinfo=ZoneInfo("America/Sao_Paulo"))
        identity = ProjectIdentity(
            "FEMSA",
            "PG + ECONOMIA HIBRIDO",
            "26081000",
            "VM - 1000",
        )
        previous = WeekPeriod(date(2026, 8, 17), date(2026, 8, 21))
        current = WeekPeriod(date(2026, 8, 24), date(2026, 8, 28))
        connection = SequencedFakeConnection(
            [
                [
                    {"week_start": previous.start, "target_sets": 334},
                    {"week_start": current.start, "target_sets": 501},
                ],
                [
                    {
                        "source_component_key": "CORPO",
                        "display_name": "CORPO",
                        "quantity_per_set": Decimal("1"),
                        "display_order": 1,
                        "active": True,
                    }
                ],
                [
                    {
                        "processo": "CORPO ENVIO",
                        "maquinario": "Envio à Pintura",
                        "quantidade": 463,
                        "timestamp": instant,
                        "created_at": instant,
                    },
                    {
                        "processo": "CORPO RETORNO",
                        "maquinario": "Retorno da Pintura",
                        "quantidade": 317,
                        "timestamp": instant,
                        "created_at": instant,
                    },
                ],
            ]
        )

        with patch("weekly_control_data.psycopg.connect", return_value=connection):
            source = load_weekly_source(
                "postgresql://database",
                identity,
                previous,
                current,
            )

        self.assertEqual(source.previous_target, 334)
        self.assertEqual(source.current_target, 501)
        self.assertEqual(source.requirements[0].quantity_per_set, Decimal("1"))
        self.assertEqual(
            [(entry.component_key, entry.movement, entry.quantity) for entry in source.entries],
            [
                ("CORPO", "remessa", Decimal("463")),
                ("CORPO", "retorno", Decimal("317")),
            ],
        )
        movement_sql, movement_params = connection.cursor_instance.executions[2]
        self.assertIn("cliente = %s", movement_sql)
        self.assertEqual(
            movement_params,
            (
                "FEMSA",
                "PG + ECONOMIA HIBRIDO",
                "26081000",
                "VM - 1000",
            ),
        )


class WeeklyWriteRepositoryTest(unittest.TestCase):
    def setUp(self):
        from weekly_control import ProjectIdentity, WeekPeriod

        self.identity = ProjectIdentity(
            "FEMSA",
            "PG + ECONOMIA HIBRIDO",
            "26081000",
            "VM - 1000",
        )
        self.period = WeekPeriod(date(2026, 8, 24), date(2026, 8, 28))

    def test_target_upsert_uses_project_and_week_as_the_identity(self):
        from weekly_control_data import save_weekly_target

        connection = WriteFakeConnection()
        with patch("weekly_control_data.psycopg.connect", return_value=connection):
            save_weekly_target(
                "postgresql://database",
                self.identity,
                self.period,
                501,
            )

        sql, params = connection.cursor_instance.executions[0]
        self.assertIn("ON CONFLICT (project_key, week_start)", sql)
        self.assertEqual(params[1:5], (
            "FEMSA",
            "PG + ECONOMIA HIBRIDO",
            "26081000",
            "VM - 1000",
        ))
        self.assertEqual(params[-1], 501)
        self.assertTrue(connection.committed)

    def test_requirement_batch_rolls_back_when_one_write_fails(self):
        from weekly_control import ComponentRequirement
        from weekly_control_data import save_component_requirements

        connection = WriteFakeConnection(fail_on_execution=2)
        requirements = (
            ComponentRequirement("CHAVE", "CHAVE", Decimal("1"), 1, True),
            ComponentRequirement(
                "SUPORTE FIXACAO DISPLAY",
                "SUPORTE FIXAÇÃO DISPLAY",
                Decimal("2"),
                2,
                True,
            ),
        )

        with (
            patch("weekly_control_data.psycopg.connect", return_value=connection),
            self.assertRaisesRegex(RuntimeError, "falha simulada"),
        ):
            save_component_requirements(
                "postgresql://database",
                self.identity,
                requirements,
            )

        self.assertFalse(connection.committed)
        self.assertTrue(connection.rolled_back)


if __name__ == "__main__":
    unittest.main()
