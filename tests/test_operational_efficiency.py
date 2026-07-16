from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.operational_efficiency import (
    build_best_operator_standard_catalog,
    calculate_efficiency_period_change,
    calculate_operational_efficiency,
    combine_standard_catalogs,
)
from services.planilha_service import resolve_standard_rate


def entry(
    *,
    good=100,
    scrap=5,
    hours=2.5,
    display="Display X",
    machine="Maquina A",
    process="Processo A",
) -> dict:
    return {
        "quantidade_produzida": good,
        "pecas_mortas": scrap,
        "duracao_horas": hours,
        "display": display,
        "maquinario": machine,
        "processo": process,
    }


def standard(
    *,
    rate=50,
    display="Display X",
    machine="Maquina A",
    process="Processo A",
    duplicate=False,
) -> dict:
    return {
        "display": display,
        "maquinario": machine,
        "processo": process,
        "standard_rate_pph": rate,
        "standard_duplicate": duplicate,
        "has_standard_value": rate is not None,
    }


class OperationalEfficiencyTests(unittest.TestCase):
    def test_best_operator_weighted_rate_becomes_historical_standard(self) -> None:
        entries = pd.DataFrame(
            [
                {**entry(good=100, scrap=0, hours=2), "operador": "Operador A"},
                {**entry(good=50, scrap=0, hours=1), "operador": "Operador A"},
                {**entry(good=80, scrap=0, hours=1), "operador": "Operador B"},
            ]
        )

        catalog = build_best_operator_standard_catalog(entries)

        self.assertEqual(len(catalog), 1)
        self.assertEqual(catalog.loc[0, "reference_operator"], "Operador B")
        self.assertAlmostEqual(catalog.loc[0, "standard_rate_pph"], 80.0)
        self.assertEqual(catalog.loc[0, "standard_source"], "melhor_operador_historico")

    def test_historical_operator_rate_includes_scrap(self) -> None:
        entries = pd.DataFrame(
            [{**entry(good=100, scrap=5, hours=2.5), "operador": "Operador A"}]
        )

        catalog = build_best_operator_standard_catalog(entries)

        self.assertAlmostEqual(catalog.loc[0, "standard_rate_pph"], 42.0)

    def test_explicit_spreadsheet_standard_has_priority_over_history(self) -> None:
        explicit = pd.DataFrame([standard(rate=50)])
        historical = pd.DataFrame(
            [
                {
                    **standard(rate=80),
                    "standard_source": "melhor_operador_historico",
                }
            ]
        )

        combined = combine_standard_catalogs(explicit, historical)

        self.assertEqual(len(combined), 1)
        self.assertEqual(combined.loc[0, "standard_rate_pph"], 50.0)

    def test_history_fills_combination_without_explicit_standard(self) -> None:
        explicit = pd.DataFrame([standard(rate=None)])
        historical = pd.DataFrame([standard(rate=80)])

        combined = combine_standard_catalogs(explicit, historical)

        self.assertEqual(len(combined), 1)
        self.assertEqual(combined.loc[0, "standard_rate_pph"], 80.0)

    def test_duplicate_explicit_standard_blocks_historical_fallback(self) -> None:
        explicit = pd.DataFrame([standard(rate=None, duplicate=True)])
        explicit.loc[0, "has_standard_value"] = True
        historical = pd.DataFrame([standard(rate=80)])

        combined = combine_standard_catalogs(explicit, historical)

        self.assertEqual(len(combined), 1)
        self.assertTrue(bool(combined.loc[0, "standard_duplicate"]))

    def test_single_entry_efficiency_is_84_percent(self) -> None:
        result = calculate_operational_efficiency(
            pd.DataFrame([entry()]), pd.DataFrame([standard()])
        )

        self.assertAlmostEqual(result.standard_hours, 2.1)
        self.assertAlmostEqual(result.raw_efficiency, 0.84)

    def test_multiple_entries_use_weighted_hours_not_simple_average(self) -> None:
        entries = pd.DataFrame(
            [
                entry(good=100, scrap=5, hours=2.5),
                entry(good=200, scrap=0, hours=5.0),
            ]
        )

        result = calculate_operational_efficiency(
            entries, pd.DataFrame([standard()])
        )

        self.assertAlmostEqual(result.standard_hours, 6.1)
        self.assertAlmostEqual(result.covered_real_hours, 7.5)
        self.assertAlmostEqual(result.raw_efficiency, 6.1 / 7.5)

    def test_processed_quantity_includes_good_production_and_scrap(self) -> None:
        result = calculate_operational_efficiency(
            pd.DataFrame([entry(good=100, scrap=5)]),
            pd.DataFrame([standard(rate=50)]),
        )

        self.assertAlmostEqual(result.standard_hours, (100 + 5) / 50)

    def test_minutes_per_piece_are_converted_to_pieces_per_hour(self) -> None:
        rate, source = resolve_standard_rate(None, "1,5")

        self.assertAlmostEqual(rate, 40.0)
        self.assertEqual(source, "tempo_padrao_min_por_peca")

    def test_pieces_per_hour_has_priority_over_minutes_per_piece(self) -> None:
        rate, source = resolve_standard_rate("50", 2)

        self.assertEqual(rate, 50.0)
        self.assertEqual(source, "pecas_por_hora_padrao")

    def test_entry_without_standard_is_uncovered(self) -> None:
        result = calculate_operational_efficiency(
            pd.DataFrame([entry()]), pd.DataFrame()
        )

        self.assertIsNone(result.raw_efficiency)
        self.assertEqual(result.covered_records, 0)
        self.assertEqual(len(result.missing_report), 1)

    def test_hour_coverage_uses_real_hours(self) -> None:
        entries = pd.DataFrame(
            [
                entry(good=80, scrap=0, hours=8, process="Coberto"),
                entry(good=20, scrap=0, hours=2, process="Sem padrao"),
            ]
        )
        standards = pd.DataFrame([standard(rate=10, process="Coberto")])

        result = calculate_operational_efficiency(entries, standards)

        self.assertAlmostEqual(result.coverage_hours, 0.8)

    def test_record_coverage_counts_valid_entries(self) -> None:
        entries = pd.DataFrame(
            [entry(process="Coberto"), entry(process="Sem padrao")]
        )
        standards = pd.DataFrame([standard(process="Coberto")])

        result = calculate_operational_efficiency(entries, standards)

        self.assertAlmostEqual(result.coverage_records, 0.5)

    def test_efficiency_is_unavailable_below_80_percent_hour_coverage(self) -> None:
        entries = pd.DataFrame(
            [
                entry(good=70, scrap=0, hours=7, process="Coberto"),
                entry(good=30, scrap=0, hours=3, process="Sem padrao"),
            ]
        )
        standards = pd.DataFrame([standard(rate=10, process="Coberto")])

        result = calculate_operational_efficiency(entries, standards)

        self.assertAlmostEqual(result.coverage_hours, 0.7)
        self.assertIsNone(result.raw_efficiency)

    def test_efficiency_is_available_at_80_percent_hour_coverage(self) -> None:
        entries = pd.DataFrame(
            [
                entry(good=80, scrap=0, hours=8, process="Coberto"),
                entry(good=20, scrap=0, hours=2, process="Sem padrao"),
            ]
        )
        standards = pd.DataFrame([standard(rate=10, process="Coberto")])

        result = calculate_operational_efficiency(entries, standards)

        self.assertAlmostEqual(result.raw_efficiency, 1.0)

    def test_raw_efficiency_can_exceed_100_percent(self) -> None:
        result = calculate_operational_efficiency(
            pd.DataFrame([entry(good=100, scrap=0, hours=1)]),
            pd.DataFrame([standard(rate=50)]),
        )

        self.assertAlmostEqual(result.raw_efficiency, 2.0)
        self.assertAlmostEqual(result.oee_efficiency, 1.0)

    def test_duplicate_standard_is_not_selected_silently(self) -> None:
        result = calculate_operational_efficiency(
            pd.DataFrame([entry()]),
            pd.DataFrame([standard(duplicate=True)]),
        )

        self.assertIsNone(result.raw_efficiency)
        self.assertEqual(result.duplicate_standard_count, 1)
        self.assertEqual(result.missing_report.iloc[0]["motivo"], "Padrao duplicado")

    def test_zero_standard_rate_is_invalid(self) -> None:
        result = calculate_operational_efficiency(
            pd.DataFrame([entry()]), pd.DataFrame([standard(rate=0)])
        )

        self.assertIsNone(result.raw_efficiency)
        self.assertEqual(result.covered_records, 0)

    def test_zero_and_negative_durations_are_invalid(self) -> None:
        entries = pd.DataFrame([entry(hours=0), entry(hours=-1)])

        result = calculate_operational_efficiency(
            entries, pd.DataFrame([standard()])
        )

        self.assertEqual(result.total_valid_records, 0)
        self.assertEqual(result.invalid_records, 2)
        self.assertIsNone(result.raw_efficiency)

    def test_negative_production_or_scrap_is_invalid(self) -> None:
        entries = pd.DataFrame([entry(good=-1), entry(scrap=-1)])

        result = calculate_operational_efficiency(
            entries, pd.DataFrame([standard()])
        )

        self.assertEqual(result.total_valid_records, 0)

    def test_monthly_change_uses_reliable_operational_efficiencies(self) -> None:
        standards = pd.DataFrame([standard(rate=10)])
        previous = calculate_operational_efficiency(
            pd.DataFrame([entry(good=80, scrap=0, hours=8)]), standards
        )
        current = calculate_operational_efficiency(
            pd.DataFrame([entry(good=96, scrap=0, hours=8)]), standards
        )

        change = calculate_efficiency_period_change(current, previous)

        self.assertAlmostEqual(change, 0.2)

    def test_monthly_change_is_unavailable_when_coverage_is_insufficient(self) -> None:
        standards = pd.DataFrame([standard(rate=10, process="Coberto")])
        previous = calculate_operational_efficiency(
            pd.DataFrame([entry(good=80, scrap=0, hours=8, process="Coberto")]),
            standards,
        )
        current = calculate_operational_efficiency(
            pd.DataFrame(
                [
                    entry(good=70, scrap=0, hours=7, process="Coberto"),
                    entry(good=30, scrap=0, hours=3, process="Sem padrao"),
                ]
            ),
            standards,
        )

        self.assertIsNone(calculate_efficiency_period_change(current, previous))

    def test_matching_normalizes_case_accents_spaces_and_special_characters(self) -> None:
        entries = pd.DataFrame(
            [
                entry(
                    display="  Dísplay X ",
                    machine="MÁQUINA-Á",
                    process="Córte / 01",
                )
            ]
        )
        standards = pd.DataFrame(
            [standard(display="display x", machine="maquina a", process="corte 01")]
        )

        result = calculate_operational_efficiency(entries, standards)

        self.assertEqual(result.covered_records, 1)

    def test_missing_machine_uses_unique_display_process_match(self) -> None:
        result = calculate_operational_efficiency(
            pd.DataFrame([entry(machine=None)]),
            pd.DataFrame([standard()]),
        )

        self.assertEqual(result.covered_records, 1)

    def test_missing_process_uses_unique_display_machine_match(self) -> None:
        result = calculate_operational_efficiency(
            pd.DataFrame([entry(process=None)]),
            pd.DataFrame([standard()]),
        )

        self.assertEqual(result.covered_records, 1)

    def test_ambiguous_fallback_match_is_not_used(self) -> None:
        standards = pd.DataFrame(
            [standard(machine="M1"), standard(machine="M2")]
        )

        result = calculate_operational_efficiency(
            pd.DataFrame([entry(machine=None)]), standards
        )

        self.assertEqual(result.covered_records, 0)
        self.assertEqual(result.missing_report.iloc[0]["motivo"], "Associacao ambigua")

    def test_entry_without_display_is_uncovered(self) -> None:
        result = calculate_operational_efficiency(
            pd.DataFrame([entry(display=None)]), pd.DataFrame([standard()])
        )

        self.assertEqual(result.covered_records, 0)
        self.assertEqual(result.missing_report.iloc[0]["motivo"], "Display nao informado")

    @patch(
        "services.operational_efficiency.load_standard_catalog_for_entries",
        return_value=pd.DataFrame(),
    )
    def test_complete_absence_of_plan_or_standard_keeps_panel_available(
        self, _mock_catalog
    ) -> None:
        result = calculate_operational_efficiency(pd.DataFrame([entry()]))

        self.assertFalse(result.has_registered_standards)
        self.assertIsNone(result.raw_efficiency)
        self.assertIsNone(result.oee_efficiency)


if __name__ == "__main__":
    unittest.main()
