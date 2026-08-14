# Conjuntos completos de pintura — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Exibir no resumo do painel e na exportação PNG os conjuntos completos enviados e retornados, calculados pelas referências `QNT` das planilhas de pintura detectadas automaticamente.

**Architecture:** Um módulo Python puro descobrirá e indexará os arquivos `.xlsx` por display, processo e movimento, enquanto o Streamlit manterá o catálogo em cache usando a assinatura nome+tamanho+data de modificação. `build_projects` aplicará `floor(total/QNT)` por processo e consolidará o menor valor na linha do display; o HTML e o renderizador PNG apenas apresentarão os valores e os avisos produzidos por essa camada.

**Tech Stack:** Python 3.11+, Streamlit, openpyxl 3.1, Pillow, unittest, PostgreSQL/psycopg.

## Global Constraints

- A fonte padrão é `S:\PROJETOS EM ANDAMENTO\PAINEL DE CONTROLE MTECH\PROGRAMAS\PROJETOS - PAINEL PRODUÇÃO IA\planilhas_pintura` e pode ser substituída por `MTECH_PAINTING_LISTS_DIR`.
- Localizar a referência pelo cabeçalho normalizado `QNT`, esteja ele na coluna D ou E.
- Ignorar arquivos temporários cujo nome comece por `~$`.
- Detectar automaticamente arquivos `.xlsx` criados, removidos ou alterados.
- Calcular somente conjuntos completos com `floor(total histórico do processo / QNT)`.
- Consolidar a linha do display pelo menor resultado entre seus processos relacionados.
- Quando faltar referência válida, mostrar `—` e um alerta; nunca interromper os demais dados do painel.
- Manter os cálculos atuais de peças, semanas, prazos e status sem alteração.
- Manter o painel Streamlit e a exportação PNG coerentes; a página Next.js de demonstração está fora do escopo.
- Não modificar nenhum arquivo da pasta de planilhas.

---

### Task 1: Catálogo automático de referências `QNT`

**Files:**
- Create: `painting_references.py`
- Create: `tests/test_painting_references.py`
- Modify: `requirements.txt`
- Modify: `.env.example`

**Interfaces:**
- Produces: `ReferenceFile(name: str, size: int, modified_ns: int)`, `ReferenceSnapshot(directory: str, files: tuple[ReferenceFile, ...], warnings: tuple[str, ...])`, `ReferenceCatalog(quantities: dict[tuple[str, str, str], float], warnings: tuple[str, ...])`.
- Produces: `scan_reference_directory(directory: str | Path) -> ReferenceSnapshot`.
- Produces: `load_reference_catalog(snapshot: ReferenceSnapshot) -> ReferenceCatalog`.
- Produces: `reference_key(display: object, process: object, movement: str) -> tuple[str, str, str]` and `complete_sets(total: float, qnt: float | None) -> int | None`.
- Consumes: `painting_colors.COLOR_BY_ABBREVIATION` para retirar cores conhecidas do fim do nome do processo.

- [ ] **Step 1: Write the failing catalog tests**

Create `tests/test_painting_references.py` with temporary workbooks covering both observed layouts, cache signatures, invalid files, duplicate conflicts and floor division:

```python
import tempfile
import time
import unittest
from pathlib import Path

from openpyxl import Workbook

from painting_references import (
    complete_sets,
    load_reference_catalog,
    reference_key,
    scan_reference_directory,
)


def write_book(path: Path, rows: list[list[object]]) -> None:
    workbook = Workbook()
    sheet = workbook.active
    for row in rows:
        sheet.append(row)
    workbook.save(path)


class PaintingReferencesTest(unittest.TestCase):
    def test_reads_qnt_by_header_in_columns_d_and_e(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_book(root / "ilha.xlsx", [
                ["ACABADO", "FERRAMENTAL", "PROCESSO", "QNT", "QNT TOTAL"],
                ["ILHA", "Envio à Pintura", "CORPO - PRETO - ENVIO", 4, 36],
            ])
            write_book(root / "slim.xlsx", [
                ["CLIENTE", "ACABADO", "FERRAMENTAL", "PROCESSO", "QNT"],
                ["SOLAR", "RACK SLIM", "Retorno da Pintura", "Corpo - Preto", 1],
            ])

            catalog = load_reference_catalog(scan_reference_directory(root))

            self.assertEqual(catalog.quantities[reference_key("ILHA", "CORPO", "remessa")], 4)
            self.assertEqual(catalog.quantities[reference_key("RACK SLIM", "CORPO", "retorno")], 1)

    def test_ignores_excel_temporary_files_and_signature_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_book(root / "display.xlsx", [
                ["ACABADO", "FERRAMENTAL", "PROCESSO", "QNT"],
                ["DISPLAY", "Envio", "CORPO", 1],
            ])
            (root / "~$display.xlsx").write_bytes(b"locked")
            first = scan_reference_directory(root)
            time.sleep(0.01)
            write_book(root / "novo.xlsx", [
                ["ACABADO", "FERRAMENTAL", "PROCESSO", "QNT"],
                ["NOVO", "Retorno", "BASE", 2],
            ])
            second = scan_reference_directory(root)

            self.assertEqual([item.name for item in first.files], ["display.xlsx"])
            self.assertNotEqual(first.files, second.files)

    def test_keeps_valid_files_when_another_file_is_invalid(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_book(root / "valido.xlsx", [
                ["ACABADO", "FERRAMENTAL", "PROCESSO", "QNT"],
                ["DISPLAY", "Envio", "BASE", 2],
            ])
            (root / "quebrado.xlsx").write_bytes(b"not an xlsx")

            catalog = load_reference_catalog(scan_reference_directory(root))

            self.assertEqual(catalog.quantities[reference_key("DISPLAY", "BASE", "remessa")], 2)
            self.assertTrue(any("quebrado.xlsx" in warning for warning in catalog.warnings))

    def test_rejects_invalid_and_conflicting_qnt(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_book(root / "conflito.xlsx", [
                ["ACABADO", "FERRAMENTAL", "PROCESSO", "QNT"],
                ["DISPLAY", "Envio", "BASE", 2],
                ["DISPLAY", "Envio", "BASE", 3],
                ["DISPLAY", "Retorno", "CORPO", 0],
            ])

            catalog = load_reference_catalog(scan_reference_directory(root))

            self.assertNotIn(reference_key("DISPLAY", "BASE", "remessa"), catalog.quantities)
            self.assertNotIn(reference_key("DISPLAY", "CORPO", "retorno"), catalog.quantities)
            self.assertGreaterEqual(len(catalog.warnings), 2)

    def test_normalizes_accents_movements_colors_and_floors_sets(self):
        self.assertEqual(
            reference_key("PG + ECONOMIA HÍBRIDO", "Corpo - Preto - Retorno", "retorno"),
            reference_key("PG + ECONOMIA HIBRIDO", "CORPO", "retorno"),
        )
        self.assertEqual(complete_sets(9, 4), 2)
        self.assertEqual(complete_sets(0, 4), 0)
        self.assertIsNone(complete_sets(9, None))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the catalog test to verify it fails**

Run: `python -m unittest tests.test_painting_references -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'painting_references'`.

- [ ] **Step 3: Implement the reference catalog**

Create `painting_references.py` with these exact rules:

```python
from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from openpyxl import load_workbook

from painting_colors import COLOR_BY_ABBREVIATION

ReferenceKey = tuple[str, str, str]


@dataclass(frozen=True)
class ReferenceFile:
    name: str
    size: int
    modified_ns: int


@dataclass(frozen=True)
class ReferenceSnapshot:
    directory: str
    files: tuple[ReferenceFile, ...]
    warnings: tuple[str, ...] = ()


@dataclass
class ReferenceCatalog:
    quantities: dict[ReferenceKey, float]
    warnings: tuple[str, ...] = ()


def normalize_reference_text(value: object) -> str:
    text = unicodedata.normalize("NFD", str(value or ""))
    return " ".join(
        "".join(char for char in text if unicodedata.category(char) != "Mn")
        .strip()
        .upper()
        .split()
    )


def normalized_process(value: object) -> str:
    label = re.sub(r"\b(?:ENVIO|REMESSA|RETORNO)\b", " ", normalize_reference_text(value))
    label = re.sub(r"[-–—]+", " ", label)
    label = " ".join(label.split())
    for color in sorted(set(COLOR_BY_ABBREVIATION.values()), key=len, reverse=True):
        normalized_color = normalize_reference_text(color)
        if label == normalized_color:
            return "PROCESSO NAO INFORMADO"
        if label.endswith(f" {normalized_color}"):
            return label[: -len(normalized_color)].strip()
    return label or "PROCESSO NAO INFORMADO"


def reference_key(display: object, process: object, movement: str) -> ReferenceKey:
    return normalize_reference_text(display), normalized_process(process), movement


def complete_sets(total: float, qnt: float | None) -> int | None:
    if qnt is None or not math.isfinite(qnt) or qnt <= 0:
        return None
    return math.floor(max(0.0, float(total)) / qnt)
```

Complete the module by:

- having `scan_reference_directory` return a warning snapshot instead of raising when the directory is missing or unreadable;
- sorting files case-insensitively and including only non-temporary `.xlsx` files;
- using each file's `st_size` and `st_mtime_ns` in `ReferenceFile`;
- opening each file independently with `load_workbook(path, read_only=True, data_only=True)` and always closing it;
- finding the header row within the first 20 rows and mapping normalized headers `ACABADO`, `FERRAMENTAL`, `PROCESSO`, `QNT`;
- deriving movement from `FERRAMENTAL`, falling back to `PROCESSO`, with `RETORNO` checked before `ENVIO`/`REMESSA`;
- collecting positive finite numeric `QNT` values by `ReferenceKey`;
- accepting duplicate values when they agree and omitting the key with a warning when values conflict;
- prefixing file-level warnings with the file name and carrying `snapshot.warnings` into the catalog.

Use these concrete implementations for discovery and loading:

```python
def movement_from_reference(tooling: object, process: object) -> str | None:
    for value in (tooling, process):
        text = normalize_reference_text(value)
        if "RETORNO" in text:
            return "retorno"
        if "ENVIO" in text or "REMESSA" in text:
            return "remessa"
    return None


def scan_reference_directory(directory: str | Path) -> ReferenceSnapshot:
    root = Path(directory)
    try:
        files = tuple(
            ReferenceFile(path.name, path.stat().st_size, path.stat().st_mtime_ns)
            for path in sorted(root.iterdir(), key=lambda item: item.name.casefold())
            if path.is_file()
            and path.suffix.casefold() == ".xlsx"
            and not path.name.startswith("~$")
        )
        return ReferenceSnapshot(str(root), files)
    except OSError as exc:
        return ReferenceSnapshot(str(root), (), (f"Pasta de referências indisponível: {exc}",))


def load_reference_catalog(snapshot: ReferenceSnapshot) -> ReferenceCatalog:
    collected: dict[ReferenceKey, set[float]] = {}
    warnings = list(snapshot.warnings)
    root = Path(snapshot.directory)
    for source in snapshot.files:
        workbook = None
        try:
            workbook = load_workbook(root / source.name, read_only=True, data_only=True)
            sheet = workbook.active
            header_row = None
            indexes: dict[str, int] = {}
            for row_number, row in enumerate(
                sheet.iter_rows(min_row=1, max_row=20, values_only=True), start=1
            ):
                candidate = {
                    normalize_reference_text(value): index
                    for index, value in enumerate(row)
                    if normalize_reference_text(value)
                }
                if {"ACABADO", "FERRAMENTAL", "PROCESSO", "QNT"} <= candidate.keys():
                    header_row, indexes = row_number, candidate
                    break
            if header_row is None:
                warnings.append(f"{source.name}: cabeçalhos ACABADO/FERRAMENTAL/PROCESSO/QNT ausentes")
                continue
            for row_number, row in enumerate(
                sheet.iter_rows(min_row=header_row + 1, values_only=True), start=header_row + 1
            ):
                display = row[indexes["ACABADO"]] if indexes["ACABADO"] < len(row) else None
                tooling = row[indexes["FERRAMENTAL"]] if indexes["FERRAMENTAL"] < len(row) else None
                process = row[indexes["PROCESSO"]] if indexes["PROCESSO"] < len(row) else None
                raw_qnt = row[indexes["QNT"]] if indexes["QNT"] < len(row) else None
                if not any((display, tooling, process, raw_qnt)):
                    continue
                movement = movement_from_reference(tooling, process)
                try:
                    qnt = float(str(raw_qnt).replace(",", "."))
                except (TypeError, ValueError):
                    qnt = 0
                if not display or not process or movement is None or not math.isfinite(qnt) or qnt <= 0:
                    warnings.append(f"{source.name}: linha {row_number} sem referência QNT válida")
                    continue
                collected.setdefault(reference_key(display, process, movement), set()).add(qnt)
        except Exception as exc:
            warnings.append(f"{source.name}: não foi possível ler a planilha ({exc})")
        finally:
            if workbook is not None:
                workbook.close()
    quantities: dict[ReferenceKey, float] = {}
    for key, values in sorted(collected.items()):
        if len(values) == 1:
            quantities[key] = next(iter(values))
        else:
            warnings.append(f"Referência ambígua para {' / '.join(key)}: {sorted(values)}")
    return ReferenceCatalog(quantities, tuple(dict.fromkeys(warnings)))
```

Modify `requirements.txt` by adding `openpyxl>=3.1,<4`. Modify `.env.example` by adding:

```dotenv
MTECH_PAINTING_LISTS_DIR=S:\PROJETOS EM ANDAMENTO\PAINEL DE CONTROLE MTECH\PROGRAMAS\PROJETOS - PAINEL PRODUÇÃO IA\planilhas_pintura
```

- [ ] **Step 4: Run the catalog tests to verify they pass**

Run: `python -m unittest tests.test_painting_references -v`

Expected: 5 tests run, all `OK`.

- [ ] **Step 5: Run existing Python tests for regression safety**

Run: `python -m unittest discover -s tests -p "test_*.py" -v`

Expected: all painting reference and painting color tests pass.

- [ ] **Step 6: Commit the catalog**

```powershell
git add painting_references.py tests/test_painting_references.py requirements.txt .env.example
git commit -m "feat: carregar referencias QNT das planilhas"
```

---

### Task 2: Calcular conjuntos e apresentá-los no painel Streamlit

**Files:**
- Create: `tests/test_project_sets.py`
- Modify: `streamlit_app.py`

**Interfaces:**
- Consumes: `ReferenceSnapshot`, `ReferenceCatalog`, `scan_reference_directory`, `load_reference_catalog`, `reference_key`, `complete_sets` from Task 1.
- Produces: `ProcessVolume.sent_sets: int | None`, `ProcessVolume.returned_sets: int | None`.
- Produces: `Project.sent_sets: int | None`, `Project.returned_sets: int | None`, `Project.reference_warnings: tuple[str, ...]`.
- Changes: `build_projects(..., references: ReferenceCatalog | None = None)`; existing callers remain valid because the new argument defaults to `None`.
- Changes: `render_dashboard(..., reference_warnings: tuple[str, ...] = ())`.

- [ ] **Step 1: Write failing project calculation tests**

Create `tests/test_project_sets.py`:

```python
import unittest

from painting_references import ReferenceCatalog, reference_key
from streamlit_app import build_projects


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


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the project tests to verify they fail**

Run: `python -m unittest tests.test_project_sets -v`

Expected: FAIL because `build_projects` does not accept `references` and the dataclasses do not expose set counts.

- [ ] **Step 3: Extend the project data model and calculation**

In `streamlit_app.py`:

1. Import the Task 1 interfaces and define `DEFAULT_PAINTING_LISTS_DIR` with the exact default path from Global Constraints.
2. Add optional set fields to `ProcessVolume` and `Project` as specified under Interfaces.
3. Change `build_projects` to accept `references: ReferenceCatalog | None = None`.
4. For each process total, look up separate remessa and retorno divisors with `reference_key(reference.display, process_name, movement)` and call `complete_sets` using the historical process totals.
5. Add a specific warning for every missing remessa/retorno key that is needed by a process; deduplicate and sort warnings before storing them.
6. Set the display's sent/returned sets to `min(...)` only when all process values for that movement are known; otherwise set the display value to `None`.
7. Preserve all existing quantity, period, status and date calculations byte-for-byte where practical.

Use this calculation shape when converting `process_totals` into `ProcessVolume` values:

```python
        project_reference_warnings: list[str] = []
        processes: list[ProcessVolume] = []
        for values in sorted(process_totals.values(), key=lambda item: normalize(item["name"])):
            process_label = str(values["name"])
            sent_qnt = (
                references.quantities.get(reference_key(reference.display, process_label, "remessa"))
                if references is not None else None
            )
            returned_qnt = (
                references.quantities.get(reference_key(reference.display, process_label, "retorno"))
                if references is not None else None
            )
            sent_sets = complete_sets(float(values["sent"]), sent_qnt)
            returned_sets = complete_sets(float(values["returned"]), returned_qnt)
            if references is not None and sent_sets is None:
                project_reference_warnings.append(f"{name} / {process_label}: QNT de envio ausente")
            if references is not None and returned_sets is None:
                project_reference_warnings.append(f"{name} / {process_label}: QNT de retorno ausente")
            processes.append(ProcessVolume(
                name=process_label,
                sent_quantity=float(values["sent"]),
                returned_quantity=float(values["returned"]),
                sent_sets=sent_sets,
                returned_sets=returned_sets,
            ))

        sent_set_values = [process.sent_sets for process in processes]
        returned_set_values = [process.returned_sets for process in processes]
        project_sent_sets = (
            min(value for value in sent_set_values if value is not None)
            if sent_set_values and all(value is not None for value in sent_set_values) else None
        )
        project_returned_sets = (
            min(value for value in returned_set_values if value is not None)
            if returned_set_values and all(value is not None for value in returned_set_values) else None
        )
```

Pass `project_sent_sets`, `project_returned_sets` and
`tuple(sorted(set(project_reference_warnings)))` into the new `Project` fields.

Add a cached wrapper whose cache key includes the immutable snapshot:

```python
@st.cache_data(show_spinner=False)
def load_reference_catalog_cached(snapshot: ReferenceSnapshot) -> ReferenceCatalog:
    return load_reference_catalog(snapshot)
```

In `dashboard_fragment`, scan and load references once before the first `build_projects`, then pass the same catalog to both calls. Aggregate `catalog.warnings` and the selected projects' `reference_warnings` into a sorted tuple.

- [ ] **Step 4: Add the HTML columns and compact warning**

In `render_dashboard`:

- insert `Conj. enviados` immediately after `Enviado total` and `Conj. retornados` immediately after `Retornado total`;
- render integer set counts with a helper returning `—` for `None`;
- add values to both display and process rows;
- update all `nth-child` widths for 11 columns, keeping the first column the widest and avoiding horizontal scrolling at the existing desktop width;
- add a `.reference-alert` block inside the summary panel after the table when warnings exist;
- escape every warning with the existing `safe` helper;
- add the footer definition `Conjuntos = total histórico ÷ QNT; a linha do Display usa o menor resultado completo entre os processos.`

Use this exact column order and desktop width allocation:

```css
.summary-table th:nth-child(1) { width: 31%; }
.summary-table th:nth-child(2) { width: 5%; }
.summary-table th:nth-child(3), .summary-table th:nth-child(5) { width: 8%; }
.summary-table th:nth-child(4), .summary-table th:nth-child(6) { width: 7%; }
.summary-table th:nth-child(7), .summary-table th:nth-child(8), .summary-table th:nth-child(10), .summary-table th:nth-child(11) { width: 7%; }
.summary-table th:nth-child(9) { width: 6%; }
```

```html
<th>Display / Processo</th><th>Dias Rem.</th>
<th class="total-col">Enviado total</th><th>Conj. enviados</th>
<th class="total-col">Retornado total</th><th>Conj. retornados</th>
<th>Env./sem.</th><th>Ret./sem.</th><th>1º Ret.</th><th>Conclusão</th><th>Status</th>
```

Pass the aggregated warning tuple to `render_dashboard`.

- [ ] **Step 5: Run project and regression tests**

Run: `python -m unittest tests.test_project_sets tests.test_painting_references tests.test_painting_colors -v`

Expected: all tests pass.

- [ ] **Step 6: Add and run an HTML rendering assertion**

Extend `tests/test_project_sets.py` with a mocked Streamlit markdown call:

```python
from datetime import date, datetime
from unittest.mock import patch

from streamlit_app import render_dashboard


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
```

Place this method inside `ProjectSetsTest` and keep the imports at module scope.

Run: `python -m unittest tests.test_project_sets -v`

Expected: 3 tests run, all `OK`.

- [ ] **Step 7: Commit the Streamlit integration**

```powershell
git add streamlit_app.py tests/test_project_sets.py
git commit -m "feat: mostrar conjuntos completos no painel"
```

---

### Task 3: Manter a exportação PNG consistente e verificar o layout

**Files:**
- Create: `tests/test_dashboard_png.py`
- Modify: `dashboard_png.py`
- Modify: `streamlit_app.py`

**Interfaces:**
- Consumes: `Project.sent_sets`, `Project.returned_sets`, `ProcessVolume.sent_sets`, `ProcessVolume.returned_sets`, and aggregated reference warnings from Task 2.
- Produces: `ProcessRow.sent_sets: int | None`, `ProcessRow.returned_sets: int | None`, `ProjectRow.sent_sets: int | None`, `ProjectRow.returned_sets: int | None`.
- Produces: `_summary_columns(weekly: bool) -> list[tuple[str, float]]` and `_summary_values(row_kind: str, item: ProjectRow | ProcessRow, weekly: bool) -> list[Any]` for deterministic table testing.

- [ ] **Step 1: Write failing PNG summary tests**

Create `tests/test_dashboard_png.py`:

```python
import unittest
from datetime import date

from dashboard_png import (
    _normalize_projects,
    _summary_columns,
    _summary_values,
    generate_dashboard_png,
)


class DashboardPngSetsTest(unittest.TestCase):
    def test_normalizes_and_places_set_counts_in_summary(self):
        projects = _normalize_projects([{
            "name": "DISPLAY",
            "sent_sets": 2,
            "returned_sets": 1,
            "total_sent_quantity": 9,
            "total_returned_quantity": 8,
            "processes": [{
                "name": "BASE",
                "sent_quantity": 9,
                "returned_quantity": 8,
                "sent_sets": 2,
                "returned_sets": 2,
            }],
        }])

        labels = [label for label, _ in _summary_columns(True)]
        values = _summary_values("display", projects[0], True)

        self.assertEqual(labels[2:6], ["Env. total", "Conj. env.", "Ret. total", "Conj. ret."])
        self.assertEqual(values[2:6], ["9,0", "2", "8,0", "1"])
        self.assertEqual(projects[0].processes[0].sent_sets, 2)

    def test_generates_png_with_set_columns(self):
        png = generate_dashboard_png(
            metrics=[],
            projects=[{
                "name": "DISPLAY",
                "sent_dates": [date(2026, 8, 1)],
                "return_dates": [date(2026, 8, 2)],
                "sent_sets": 2,
                "returned_sets": 1,
                "sent_quantity": 9,
                "returned_quantity": 8,
                "total_sent_quantity": 9,
                "total_returned_quantity": 8,
                "processes": [{
                    "name": "BASE",
                    "sent_quantity": 9,
                    "returned_quantity": 8,
                    "sent_sets": 2,
                    "returned_sets": 2,
                }],
            }],
            timeline_dates=[date(2026, 8, 1), date(2026, 8, 2)],
            insights=[{"title": "Referências", "text": "arquivo sem QNT", "kind": "warning"}],
            width=1280,
        )

        self.assertTrue(png.startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertGreater(len(png), 10_000)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the PNG tests to verify they fail**

Run: `python -m unittest tests.test_dashboard_png -v`

Expected: FAIL because the set fields and summary helpers do not exist.

- [ ] **Step 3: Extend PNG models, normalization and table helpers**

In `dashboard_png.py`:

1. Add optional `sent_sets` and `returned_sets` fields to `ProcessRow` and `ProjectRow`.
2. Read those fields in `_normalize_projects` without converting `None` to zero.
3. Add `_format_sets(value)` that returns `—` for `None` and `str(int(value))` otherwise.
4. Extract the current inline column definition into `_summary_columns(weekly)` and insert `Conj. env.` after `Env. total` plus `Conj. ret.` after `Ret. total`.
5. Extract display/process value construction into `_summary_values`; preserve status calculation for process rows.
6. Allocate ratios so `Display / Processo` remains at least 30% of the table and each set column receives at least 7% before normalization.
7. Use the helpers inside `generate_dashboard_png` so tests and rendering share exactly the same ordering.
8. Add a footer item: `Conjuntos = total ÷ QNT; Display usa o menor processo.`

Use these exact helpers as the single source for header/value order:

```python
def _format_sets(value: int | None) -> str:
    return "—" if value is None else str(int(value))


def _summary_columns(weekly: bool) -> list[tuple[str, float]]:
    if weekly:
        return [
            ("Display / Processo", .30), ("Dias", .05),
            ("Env. total", .075), ("Conj. env.", .07),
            ("Ret. total", .075), ("Conj. ret.", .07),
            ("Env./sem.", .06), ("Ret./sem.", .06),
            ("1º Ret.", .055), ("Conclusão", .065), ("Status", .12),
        ]
    return [
        ("Display / Processo", .34), ("Dias", .06),
        ("Env. total", .10), ("Conj. env.", .08),
        ("Ret. total", .10), ("Conj. ret.", .08),
        ("1º Ret.", .08), ("Conclusão", .08), ("Status", .08),
    ]


def _summary_values(row_kind: str, item: ProjectRow | ProcessRow, weekly: bool) -> list[Any]:
    if row_kind == "display":
        project = item
        values = [
            project.name,
            project.sent_day_count,
            _format_number(project.total_sent_quantity),
            _format_sets(project.sent_sets),
            _format_number(project.total_returned_quantity),
            _format_sets(project.returned_sets),
        ]
        if weekly:
            values.extend([_format_number(project.sent_per_week), _format_number(project.return_per_week)])
        values.extend([
            _day_text(project.first_return_days),
            _day_text(project.conclusion_days, incomplete=True),
            project.status,
        ])
        return values
    process = item
    status = (
        "Sem retorno" if process.returned_quantity <= 0
        else "Parcial" if process.sent_quantity > 0 and process.returned_quantity < process.sent_quantity
        else "Concluído"
    )
    values = [
        process.name,
        "—",
        _format_number(process.sent_quantity),
        _format_sets(process.sent_sets),
        _format_number(process.returned_quantity),
        _format_sets(process.returned_sets),
    ]
    if weekly:
        values.extend(["—", "—"])
    values.extend(["—", "—", status])
    return values
```

- [ ] **Step 4: Send reference warnings to the PNG insights panel**

In `streamlit_app.py`, create one warning insight when aggregated reference warnings exist:

```python
reference_insights = (
    [("⚠", "Referências de conjuntos", "; ".join(reference_warnings))]
    if reference_warnings
    else []
)
png_insights = (reference_insights + smart_insights(project_data, timeline_dates))[:5]
```

Pass `png_insights` to `build_dashboard_png`. Keep the HTML warning block from Task 2 unchanged.

- [ ] **Step 5: Run PNG and full Python tests**

Run: `python -m unittest tests.test_dashboard_png -v`

Expected: 2 tests run, all `OK`.

Run: `python -m unittest discover -s tests -p "test_*.py" -v`

Expected: all Python tests pass.

- [ ] **Step 6: Generate and visually inspect the representative PNG**

Run this focused fixture command from PowerShell:

```powershell
@'
from datetime import date
from pathlib import Path
from dashboard_png import generate_dashboard_png

output = Path('.codex-work/conjuntos-pintura-preview.png')
output.parent.mkdir(exist_ok=True)
output.write_bytes(generate_dashboard_png(
    metrics=[],
    projects=[{
        'name': 'DISPLAY TESTE PRETO 1',
        'sent_dates': [date(2026, 8, 1)],
        'return_dates': [date(2026, 8, 2)],
        'sent_quantity': 20,
        'returned_quantity': 13,
        'total_sent_quantity': 20,
        'total_returned_quantity': 13,
        'sent_sets': 4,
        'returned_sets': 2,
        'processes': [
            {'name': 'BASE', 'sent_quantity': 9, 'returned_quantity': 8, 'sent_sets': 2, 'returned_sets': 2},
            {'name': 'CORPO', 'sent_quantity': 11, 'returned_quantity': 5, 'sent_sets': 2, 'returned_sets': 1},
        ],
    }],
    timeline_dates=[date(2026, 8, 1), date(2026, 8, 2)],
    insights=[{'title': 'Referências de conjuntos', 'text': 'um processo sem QNT', 'kind': 'warning'}],
    width=1920,
))
print(output.resolve())
'@ | python -
```

Open `.codex-work/conjuntos-pintura-preview.png` with the local image viewer and verify: both set headers are fully legible; display/process names are not clipped beyond the existing ellipsis behavior; totals, set counts and statuses occupy the correct columns; warning insight is readable; no content crosses the panel boundary.

Expected: a valid 1920px-wide PNG with all 11 summary columns visible and aligned.

- [ ] **Step 7: Run syntax and diff checks**

Run: `python -m py_compile painting_references.py streamlit_app.py dashboard_png.py`

Expected: exit code 0 with no output.

Run: `git diff --check`

Expected: exit code 0 with no whitespace errors.

- [ ] **Step 8: Commit PNG parity**

```powershell
git add dashboard_png.py streamlit_app.py tests/test_dashboard_png.py
git commit -m "feat: incluir conjuntos na exportacao do painel"
```

---

### Task 4: Verificação integrada com as planilhas reais

**Files:**
- Modify only if verification exposes a defect: `painting_references.py`, `streamlit_app.py`, `dashboard_png.py`, and the test that reproduces the defect.

**Interfaces:**
- Consumes: all interfaces produced by Tasks 1–3.
- Produces: evidence that the real directory is detected, valid `QNT` references are indexed and failures remain non-fatal.

- [ ] **Step 1: Run the complete automated suite**

Run: `python -m unittest discover -s tests -p "test_*.py" -v`

Expected: all tests pass.

- [ ] **Step 2: Inspect the real directory without modifying it**

Run:

```powershell
@'
from painting_references import load_reference_catalog, scan_reference_directory

directory = r'S:\PROJETOS EM ANDAMENTO\PAINEL DE CONTROLE MTECH\PROGRAMAS\PROJETOS - PAINEL PRODUÇÃO IA\planilhas_pintura'
snapshot = scan_reference_directory(directory)
catalog = load_reference_catalog(snapshot)
print(f'files={len(snapshot.files)} references={len(catalog.quantities)} warnings={len(catalog.warnings)}')
for warning in catalog.warnings:
    print(f'WARNING: {warning}')
'@ | python -
```

Expected: the five non-temporary workbooks are detected, the temporary `~$` file is ignored, at least one reference is indexed from every valid workbook, and warnings—if a workbook is temporarily locked—are printed without a traceback.

- [ ] **Step 3: Verify automatic invalidation behavior against a temporary directory**

Run: `python -m unittest tests.test_painting_references.PaintingReferencesTest.test_ignores_excel_temporary_files_and_signature_changes -v`

Expected: test passes, proving a created workbook changes the immutable snapshot used as the Streamlit cache key.

- [ ] **Step 4: Run the final static checks**

Run: `python -m py_compile painting_references.py streamlit_app.py dashboard_png.py`

Expected: exit code 0.

Run: `git status --short`

Expected: no uncommitted implementation files; `.codex-work` remains ignored.

- [ ] **Step 5: Commit only if verification required a corrective change**

If Step 1–4 exposed a defect, first add a failing regression test, implement the smallest correction, rerun the covering test and full Python suite, then commit only the affected source and test files:

```powershell
git add painting_references.py streamlit_app.py dashboard_png.py tests
git commit -m "fix: validar referencias reais de pintura"
```

If no correction was required, do not create an empty commit.
