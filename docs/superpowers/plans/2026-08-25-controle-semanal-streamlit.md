# Controle semanal no Streamlit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. The user explicitly prohibited subagents.

**Goal:** Adicionar ao painel Streamlit oficial um controle semanal editável, fiel à referência executiva, que estuda qualquer projeto de `painting_entries` usando metas acumuladas e requisitos configurados manualmente no Supabase.

**Architecture:** `painting_entries` permanece a única origem dos movimentos. Dois módulos novos separam domínio e acesso ao Supabase, um terceiro renderiza a visualização semanal, e `streamlit_app.py` apenas integra as abas e os formulários. Duas tabelas com RLS armazenam metas acumuladas e requisitos por projeto; a lista de projetos continua sendo derivada dinamicamente de `painting_entries`.

**Tech Stack:** Python 3, Streamlit 1.39+, psycopg 3, PostgreSQL/Supabase, `unittest`, HTML/CSS responsivo.

**Spec:** `docs/superpowers/specs/2026-08-25-controle-semanal-streamlit-design.md`

## Global Constraints

- Painel oficial: `https://painel-pintura-mtech.streamlit.app/`.
- Implementar somente no Streamlit; não modificar Next.js, Sites, Cloudflare, `production_entries`, `process_forecasts` ou `/lancamentos`.
- `painting_entries` é a única fonte de movimentos de remessa e retorno.
- Não fixar metas, datas correntes, lista de projetos ou componentes detectados no código de produção.
- Os valores 334 e 501 aparecem somente em testes e explicações, nunca na carga inicial.
- A meta digitada representa o acumulado até a sexta-feira da semana escolhida.
- O editor de metas e requisitos não terá senha, conforme decisão explícita do usuário; toda gravação exige confirmação visível.
- `CHAVE = 1` e `SUPORTE FIXAÇÃO DISPLAY = 2` serão cadastrados somente para `FEMSA / PG + ECONOMIA HIBRIDO / 26081000 / VM - 1000`.
- Não criar subagentes.
- Não expor `DATABASE_URL`, chaves ou tokens em logs, HTML, testes ou respostas.
- Não publicar antes de concluir testes automatizados, inspeção visual e revisão de código.

## File Structure

- Create `weekly_control.py`: modelos imutáveis, chave de projeto, calendário, normalização, agregação e fórmulas.
- Create `weekly_control_data.py`: consultas parametrizadas e upserts transacionais no Supabase.
- Create `weekly_control_view.py`: HTML/CSS semanal, formatação pt-BR, legendas e estados visuais.
- Create `supabase/migrations/20260825_create_painting_weekly_control.sql`: tabelas, constraints, índices e RLS, sem metas demonstrativas.
- Create `tests/test_weekly_control.py`: calendário, normalização, cálculo, ausências e TINTA.
- Create `tests/test_weekly_control_data.py`: consultas, isolamento do projeto e gravações idempotentes.
- Create `tests/test_weekly_control_view.py`: contrato visual, semântica, acessibilidade e estados.
- Create `tests/test_weekly_control_migration.py`: contrato estático da migration e proibição de fixtures.
- Modify `streamlit_app.py`: abas, seleção de projeto, formulários e composição da nova visualização.
- Modify `tests/test_project_sets.py`: preservar o comportamento da visão gerencial e testar a navegação integrada.

---

### Task 1: Domínio de projeto, calendário e normalização

**Files:**
- Create: `weekly_control.py`
- Create: `tests/test_weekly_control.py`

**Interfaces:**
- Produces: `ProjectIdentity`, `WeekPeriod`, `MovementEntry`, `ComponentRequirement`, `project_key()`, `weekly_periods()`, `normalize_text()`, `component_key()` e `movement_from_fields()`.
- Consumes: somente biblioteca padrão.

- [ ] **Step 1: Write the failing tests for exact project identity and deterministic keys**

```python
class WeeklyIdentityTest(unittest.TestCase):
    def test_project_key_is_stable_and_keeps_projects_isolated(self):
        pg = ProjectIdentity("FEMSA", "PG + ECONOMIA HIBRIDO", "26081000", "VM - 1000")
        other_color = ProjectIdentity("FEMSA", "PG + ECONOMIA HIBRIDO", "26081000", "PT - 1000")

        self.assertEqual(project_key(pg), project_key(pg))
        self.assertNotEqual(project_key(pg), project_key(other_color))
        self.assertEqual(len(project_key(pg)), 64)
```

- [ ] **Step 2: Run the identity test and verify RED**

Run: `python -m unittest tests.test_weekly_control.WeeklyIdentityTest -v`  
Expected: FAIL because `weekly_control` does not exist.

- [ ] **Step 3: Implement immutable identity and SHA-256 key generation**

```python
@dataclass(frozen=True)
class ProjectIdentity:
    cliente: str
    display: str
    numero_display: str
    codigo_pintura: str


@dataclass(frozen=True)
class WeekPeriod:
    start: date
    end: date


@dataclass(frozen=True)
class MovementEntry:
    component_key: str
    movement: Literal["remessa", "retorno"]
    quantity: Decimal
    occurred_at: datetime


@dataclass(frozen=True)
class ComponentRequirement:
    source_component_key: str
    display_name: str
    quantity_per_set: Decimal | None
    display_order: int
    active: bool


def project_key(identity: ProjectIdentity) -> str:
    canonical = "\x1f".join(normalize_text(value) for value in (
        identity.cliente,
        identity.display,
        identity.numero_display,
        identity.codigo_pintura,
    ))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
```

- [ ] **Step 4: Add failing tests for São Paulo weeks and normalization**

```python
class WeeklyCalendarTest(unittest.TestCase):
    def test_periods_are_monday_to_friday_in_sao_paulo(self):
        previous, current = weekly_periods(datetime(2026, 8, 25, 12, tzinfo=ZoneInfo("America/Sao_Paulo")))
        self.assertEqual((previous.start, previous.end), (date(2026, 8, 17), date(2026, 8, 21)))
        self.assertEqual((current.start, current.end), (date(2026, 8, 24), date(2026, 8, 28)))


class WeeklyNormalizationTest(unittest.TestCase):
    def test_normalizes_movements_components_and_tinta(self):
        self.assertEqual(movement_from_fields("BDJ CORPO RETORNO", ""), "retorno")
        self.assertEqual(movement_from_fields("BDJ CORPO", "Envio à Pintura"), "remessa")
        self.assertEqual(component_key("ENVIO — Fechamento Móvel"), "FECHAMENTO MOVEL")
        self.assertEqual(component_key("TINTA VM - ENVIO"), "TINTA VM")
```

- [ ] **Step 5: Run the new tests and verify RED**

Run: `python -m unittest tests.test_weekly_control.WeeklyCalendarTest tests.test_weekly_control.WeeklyNormalizationTest -v`  
Expected: FAIL because the calendar and normalization functions are missing.

- [ ] **Step 6: Implement the calendar and shared normalization rules**

Use `ZoneInfo("America/Sao_Paulo")`, strip accents with `unicodedata.normalize`, remove only the movement tokens `ENVIO`, `REMESSA` and `RETORNO`, preserve meaningful component text, and return `None` for unrecognized movement.

- [ ] **Step 7: Run Task 1 tests and verify GREEN**

Run: `python -m unittest tests.test_weekly_control.WeeklyIdentityTest tests.test_weekly_control.WeeklyCalendarTest tests.test_weekly_control.WeeklyNormalizationTest -v`  
Expected: all tests PASS.

- [ ] **Step 8: Commit Task 1**

```bash
git add weekly_control.py tests/test_weekly_control.py
git commit -m "feat: adicionar dominio do controle semanal"
```

---

### Task 2: Agregações, fórmulas, ausências e TINTA

**Files:**
- Modify: `weekly_control.py`
- Modify: `tests/test_weekly_control.py`

**Interfaces:**
- Consumes: types and normalization from Task 1.
- Produces: `WeeklyComponent`, `WeeklySummary`, `WeeklyControl`, `build_weekly_control()`.

- [ ] **Step 1: Write failing reference-fixture formula tests**

```python
class WeeklyCalculationTest(unittest.TestCase):
    def test_reference_formulas_and_pending_totals(self):
        control = build_weekly_control(
            previous_target=334,
            current_target=501,
            requirements=(
                ComponentRequirement("CORPO", "CORPO", Decimal("1"), 1, True),
                ComponentRequirement("TOLDO", "TOLDO", Decimal("1"), 2, True),
                ComponentRequirement("BANDEJA DIREITA P", "BANDEJA DIREITA – P", Decimal("4"), 3, True),
                ComponentRequirement("SUPORTE FIXACAO DISPLAY", "SUPORTE FIXAÇÃO DISPLAY", Decimal("2"), 4, True),
            ),
            entries=(
                MovementEntry("CORPO", "remessa", Decimal("463"), FIXED_INSTANT),
                MovementEntry("CORPO", "retorno", Decimal("317"), FIXED_INSTANT),
                MovementEntry("TOLDO", "remessa", Decimal("550"), FIXED_INSTANT),
                MovementEntry("TOLDO", "retorno", Decimal("390"), FIXED_INSTANT),
                MovementEntry("BANDEJA DIREITA P", "remessa", Decimal("1600"), FIXED_INSTANT),
                MovementEntry("BANDEJA DIREITA P", "retorno", Decimal("778"), FIXED_INSTANT),
                MovementEntry("SUPORTE FIXACAO DISPLAY", "remessa", Decimal("1010"), FIXED_INSTANT),
                MovementEntry("SUPORTE FIXACAO DISPLAY", "retorno", Decimal("287"), FIXED_INSTANT),
            ),
        )

        by_key = {row.component_key: row for row in control.components}
        self.assertEqual(by_key["CORPO"].previous_balance, Decimal("-17"))
        self.assertEqual(by_key["CORPO"].current_balance, Decimal("-38"))
        self.assertEqual(by_key["TOLDO"].previous_balance, Decimal("56"))
        self.assertEqual(by_key["TOLDO"].current_balance, Decimal("49"))
        self.assertEqual(by_key["BANDEJA DIREITA P"].previous_balance, Decimal("-558"))
        self.assertEqual(by_key["BANDEJA DIREITA P"].current_balance, Decimal("-404"))
        self.assertEqual(by_key["SUPORTE FIXACAO DISPLAY"].previous_balance, Decimal("-381"))
        self.assertEqual(by_key["SUPORTE FIXACAO DISPLAY"].current_balance, Decimal("8"))
```

- [ ] **Step 2: Run the calculation test and verify RED**

Run: `python -m unittest tests.test_weekly_control.WeeklyCalculationTest.test_reference_formulas_and_pending_totals -v`  
Expected: FAIL because `build_weekly_control` is missing.

- [ ] **Step 3: Implement Decimal-based calculations**

Implement the exact formulas from the spec with these immutable return types:

```python
@dataclass(frozen=True)
class WeeklyComponent:
    component_key: str
    display_name: str
    quantity_per_set: Decimal | None
    total_remessa: Decimal | None
    total_retorno: Decimal | None
    painting_balance: Decimal | None
    previous_balance: Decimal | None
    current_balance: Decimal | None


@dataclass(frozen=True)
class WeeklySummary:
    target_sets: int | None
    total_components: Decimal | None
    pending_pieces: Decimal
    pending_references: int


@dataclass(frozen=True)
class WeeklyControl:
    components: tuple[WeeklyComponent, ...]
    paint_rows: tuple[WeeklyComponent, ...]
    previous_summary: WeeklySummary
    current_summary: WeeklySummary
    warnings: tuple[str, ...]
```

A computed balance is `None` when any required operand is absent. Count pending references only when the computed balance is negative; sum the absolute value of those negative balances.

- [ ] **Step 4: Add failing tests for missing movement, explicit zero, ordering and TINTA**

```python
    def test_missing_is_not_zero_and_tinta_is_separate(self):
        control = build_weekly_control(
            previous_target=10,
            current_target=12,
            requirements=(ComponentRequirement("CHAVE", "CHAVE", Decimal("1"), 2, True),),
            entries=(
                MovementEntry("CHAVE", "remessa", Decimal("0"), FIXED_INSTANT),
                MovementEntry("TINTA VM", "remessa", Decimal("25"), FIXED_INSTANT),
            ),
        )

        self.assertEqual(control.components[0].total_remessa, Decimal("0"))
        self.assertIsNone(control.components[0].total_retorno)
        self.assertIsNone(control.components[0].painting_balance)
        self.assertEqual(control.paint_rows[0].total_remessa, Decimal("25"))
        self.assertEqual(control.paint_rows[0].display_name, "TINTA VM")
```

- [ ] **Step 5: Implement presence-aware aggregation and TINTA extraction**

Aggregate `quantidade` only after movement and component normalization. Track presence separately from numeric totals so a stored zero differs from no row. Sort configured components by `display_order`; append sorted TINTA rows after all configured components and exclude them from summaries.

- [ ] **Step 6: Add the complete fixture summary assertions**

Add fixtures from the reference that prove: 17 components per set, 5,678 previous components, 8,517 current components, 1,584 previous pending pieces across six references, and 937 current pending pieces across four references.

- [ ] **Step 7: Run Task 2 tests and verify GREEN**

Run: `python -m unittest tests.test_weekly_control -v`  
Expected: all tests PASS.

- [ ] **Step 8: Commit Task 2**

```bash
git add weekly_control.py tests/test_weekly_control.py
git commit -m "feat: calcular metas e pendencias semanais"
```

---

### Task 3: Migration das metas e requisitos

**Files:**
- Create: `supabase/migrations/20260825_create_painting_weekly_control.sql`
- Create: `tests/test_weekly_control_migration.py`

**Interfaces:**
- Produces: `public.painting_weekly_targets` and `public.painting_component_requirements`.
- Consumes: `project_key` values generated by the application; no foreign key to the append-only movement log.

- [ ] **Step 1: Write the failing migration contract test**

```python
class WeeklyMigrationTest(unittest.TestCase):
    def test_migration_has_constraints_rls_and_no_demo_targets(self):
        sql = MIGRATION.read_text(encoding="utf-8").upper()
        self.assertIn("CREATE TABLE PUBLIC.PAINTING_WEEKLY_TARGETS", sql)
        self.assertIn("CREATE TABLE PUBLIC.PAINTING_COMPONENT_REQUIREMENTS", sql)
        self.assertIn("UNIQUE (PROJECT_KEY, WEEK_START)", sql)
        self.assertIn("WEEK_END = WEEK_START + 4", sql)
        self.assertIn("ENABLE ROW LEVEL SECURITY", sql)
        self.assertNotIn("VALUES (334", sql)
        self.assertNotIn("VALUES (501", sql)
```

- [ ] **Step 2: Run the migration test and verify RED**

Run: `python -m unittest tests.test_weekly_control_migration -v`  
Expected: FAIL because the SQL file is missing.

- [ ] **Step 3: Write idempotent DDL**

Create both tables with identity primary keys, checks, unique constraints, lookup indexes, `created_at`, `updated_at`, and RLS enabled. Permit `quantity_per_set` to be null so detected but incomplete components can be represented. Do not insert metas or general component fixtures in the migration.

- [ ] **Step 4: Run the migration test and verify GREEN**

Run: `python -m unittest tests.test_weekly_control_migration -v`  
Expected: PASS.

- [ ] **Step 5: Commit Task 3**

```bash
git add supabase/migrations/20260825_create_painting_weekly_control.sql tests/test_weekly_control_migration.py
git commit -m "feat: adicionar migration do planejamento de pintura"
```

---

### Task 4: Repositório Supabase de leitura e escrita

**Files:**
- Create: `weekly_control_data.py`
- Create: `tests/test_weekly_control_data.py`

**Interfaces:**
- Consumes: `ProjectIdentity`, `WeekPeriod`, `ComponentRequirement`, `MovementEntry`, `project_key()`.
- Produces: `ProjectOption`, `WeeklySourceData`, `list_painting_projects()`, `load_weekly_source()`, `save_weekly_target()`, `save_component_requirements()`.

- [ ] **Step 1: Write failing tests for the distinct project query**

Patch `psycopg.connect` with a recording connection and assert that `list_painting_projects(db_url)` returns every distinct four-column identity ordered by the most recent movement. The test must include two colors for the same display and assert both remain separate.

- [ ] **Step 2: Run the project-query test and verify RED**

Run: `python -m unittest tests.test_weekly_control_data.WeeklyProjectRepositoryTest -v`  
Expected: FAIL because `weekly_control_data` does not exist.

- [ ] **Step 3: Implement `list_painting_projects()`**

Use a parameter-free aggregate query over `painting_entries` that groups by the exact four source columns, rejects blank identities, returns `MAX(COALESCE(timestamp, created_at))`, and builds the deterministic key in Python. Never concatenate values into SQL.

- [ ] **Step 4: Write failing tests for isolated source loading**

Assert that `load_weekly_source(db_url, identity, previous_period, current_period)` issues parameterized queries for:

```text
painting_weekly_targets: project_key + both week_start values
painting_component_requirements: project_key, ordered by display_order
painting_entries: exact cliente + display + numero_display + codigo_pintura
```

The test must prove that no row from another color reaches the returned `MovementEntry` collection.

- [ ] **Step 5: Implement `load_weekly_source()`**

Convert database numerics to `Decimal`, timestamps to aware datetimes, preserve absent targets as `None`, and derive detected component keys from the selected project's movements. Return warnings for detected components without saved requirements.

- [ ] **Step 6: Write failing upsert and rollback tests**

```python
class WeeklyWriteRepositoryTest(unittest.TestCase):
    def test_target_upsert_uses_project_and_week_conflict_key(self):
        save_weekly_target(DB_URL, IDENTITY, CURRENT_PERIOD, 501)
        sql, params = recording_cursor.executions[-1]
        self.assertIn("ON CONFLICT (project_key, week_start)", sql)
        self.assertEqual(params[-1], 501)

    def test_component_batch_rolls_back_when_one_row_fails(self):
        recording_cursor.fail_on_execution = 2
        with self.assertRaises(RuntimeError):
            save_component_requirements(DB_URL, IDENTITY, REQUIREMENTS)
        self.assertFalse(recording_connection.committed)
        self.assertTrue(recording_connection.rolled_back)
```

- [ ] **Step 7: Implement transactional target and requirement upserts**

Validate week boundaries and non-negative integer target before opening the connection. Validate unique component keys/orders and positive-or-null quantities. Use `INSERT INTO public.painting_weekly_targets (...) VALUES (...) ON CONFLICT (project_key, week_start) DO UPDATE` for metas and the equivalent explicit column list with `ON CONFLICT (project_key, source_component_key) DO UPDATE` for requirements. Set `updated_at = now()`, commit once after a complete batch, and let the context manager roll back any failed batch.

- [ ] **Step 8: Run Task 4 tests and verify GREEN**

Run: `python -m unittest tests.test_weekly_control_data -v`  
Expected: all tests PASS.

- [ ] **Step 9: Commit Task 4**

```bash
git add weekly_control_data.py tests/test_weekly_control_data.py
git commit -m "feat: conectar controle semanal ao supabase"
```

---

### Task 5: Visual executivo responsivo

**Files:**
- Create: `weekly_control_view.py`
- Create: `tests/test_weekly_control_view.py`

**Interfaces:**
- Consumes: `ProjectIdentity`, `WeekPeriod`, `WeeklyControl`.
- Produces: `WEEKLY_CONTROL_CSS`, `format_pt_br()`, `render_weekly_control_html()`, `render_weekly_empty_html()`.

- [ ] **Step 1: Write failing semantic and copy tests**

```python
class WeeklyControlViewTest(unittest.TestCase):
    def test_renders_reference_contract_with_semantic_tables(self):
        html = render_weekly_control_html(MODEL)
        self.assertIn("MODELO 1 · EXECUTIVO INDUSTRIAL", html)
        self.assertIn("Controle semanal de remessas e retornos", html)
        self.assertIn("Semana passada", html)
        self.assertIn("Semana atual", html)
        self.assertIn("P/ FECHAR", html)
        self.assertIn("P/ ENVIAR", html)
        self.assertEqual(html.count("<thead>"), 2)
        self.assertIn('scope="col"', html)
        self.assertIn("Próxima ação: priorizar linhas em vermelho", html)
```

- [ ] **Step 2: Run the view test and verify RED**

Run: `python -m unittest tests.test_weekly_control_view -v`  
Expected: FAIL because the renderer does not exist.

- [ ] **Step 3: Implement escaped HTML and pt-BR formatting**

Use `html.escape` for every database/user value. Render absent values as `—`, explicit zero as `0`, negatives with the minus sign, and thousands with periods. Add textual status labels alongside red/green classes.

- [ ] **Step 4: Add failing tests for row classes, TINTA and incomplete data**

Assert that negative balances have both a red class and the text `Pendente`, covered balances have both a green class and `Coberto`, TINTA is the last row and excluded from summary values, and an incomplete requirement renders `—` plus a visible data warning.

- [ ] **Step 5: Implement the complete reference layout**

Build the graphite header, wine and petroleum accents, two table panels, alternating rows, yellow remittance, blue balance, legends, summary cards and action card. Scope every selector below `.weekly-control` and add media queries for 1366 px and 700 px; below 700 px stack the panels and allow only the table wrappers to scroll.

- [ ] **Step 6: Run Task 5 tests and verify GREEN**

Run: `python -m unittest tests.test_weekly_control_view -v`  
Expected: all tests PASS.

- [ ] **Step 7: Commit Task 5**

```bash
git add weekly_control_view.py tests/test_weekly_control_view.py
git commit -m "feat: renderizar controle semanal executivo"
```

---

### Task 6: Abas e formulários no Streamlit

**Files:**
- Modify: `streamlit_app.py`
- Modify: `tests/test_project_sets.py`
- Create: `tests/test_weekly_control_streamlit.py`

**Interfaces:**
- Consumes: all public functions from Tasks 1, 2, 4 and 5.
- Produces: `weekly_control_panel()`, `render_target_editor()`, `render_requirement_editor()` and an updated `main()`.

- [ ] **Step 1: Write a failing navigation test**

Patch `st.tabs`, `dashboard_fragment` and `weekly_control_panel`, call `main()`, and assert the exact labels `Visão gerencial` and `Controle semanal` plus one render call for each panel.

- [ ] **Step 2: Run the navigation test and verify RED**

Run: `python -m unittest tests.test_weekly_control_streamlit.WeeklyNavigationTest -v`  
Expected: FAIL because `main()` has no tabs.

- [ ] **Step 3: Integrate native Streamlit tabs without changing the current dashboard**

Keep `dashboard_fragment()` unchanged inside the first tab. Put the new loader, selector, editors and HTML renderer inside the second tab. Cache read queries for 55 seconds and clear only the weekly caches after a successful save.

- [ ] **Step 4: Write failing tests for project selection and editor validation**

Cover these scenarios with patched Streamlit widgets and repository calls:

- newest project is the default;
- changing the project reloads only its source data;
- target save is blocked without the confirmation checkbox;
- negative/non-integer target is rejected;
- requirement save is blocked for duplicate order or blank component key;
- successful save shows confirmation and reruns the app;
- database failure shows an error and never substitutes fixture data.

- [ ] **Step 5: Implement target editor**

Use a `st.form` inside an expander. Accept a date and normalize it to the containing Monday/Friday, show both dates before saving, use `st.number_input(step=1, min_value=0)`, and require `st.checkbox("Confirmo a gravação desta meta acumulada")`.

- [ ] **Step 6: Implement component editor**

Build editable rows from the union of detected keys and saved requirements. Use `st.data_editor` with columns for active, component source, display name, quantity per set and order. Permit added rows for components without movements. Require a separate confirmation checkbox before calling the batch upsert.

- [ ] **Step 7: Implement weekly state handling**

Display distinct messages for missing migration, no projects, missing target(s), no movements, incomplete requirements and connection/write failures. Render partial data only when its unavailable calculations remain `—` and the warning names the missing fields.

- [ ] **Step 8: Run integration and regression tests**

Run: `python -m unittest tests.test_weekly_control_streamlit tests.test_project_sets -v`  
Expected: all tests PASS and the existing managerial tests remain unchanged.

- [ ] **Step 9: Commit Task 6**

```bash
git add streamlit_app.py tests/test_project_sets.py tests/test_weekly_control_streamlit.py
git commit -m "feat: integrar controle semanal ao streamlit"
```

---

### Task 7: Aplicar schema e requisitos iniciais no Supabase

**Files:**
- Use: `supabase/migrations/20260825_create_painting_weekly_control.sql`
- Use: `weekly_control_data.py`

**Interfaces:**
- Consumes: verified migration and repository functions.
- Produces: remote schema plus two approved requirement records; produces no target records.

- [ ] **Step 1: Enable an authorized write path**

Replace the current Supabase MCP configuration that contains `read_only=true` with an authenticated write-enabled configuration for the same project `rhvftsqeqqvlqweedbzs`. Verify the target project URL before any mutation. If the current Codex session does not expose a migration tool after reauthentication, use an authenticated Supabase SQL editor session; never print a connection string.

- [ ] **Step 2: Reinspect the remote schema immediately before mutation**

Confirm that neither target table exists. If either exists, compare every column, constraint and policy with the migration and stop on incompatible drift instead of overwriting it.

- [ ] **Step 3: Apply the migration exactly once**

Apply `20260825_create_painting_weekly_control.sql` through the authorized Supabase migration path. Record the migration name and returned status.

- [ ] **Step 4: Verify schema and advisors**

List both tables with verbose metadata, confirm RLS enabled, run security and performance advisors, and preserve the unrelated `process_forecasts` RLS warning without modifying that table.

- [ ] **Step 5: Insert only the two approved PG requirements**

Use the deterministic key for `ProjectIdentity("FEMSA", "PG + ECONOMIA HIBRIDO", "26081000", "VM - 1000")` and upsert:

```text
CHAVE | CHAVE | quantity_per_set 1 | next free display_order | active true
SUPORTE FIXACAO DISPLAY | SUPORTE FIXAÇÃO DISPLAY | quantity_per_set 2 | next free display_order | active true
```

Query the existing requirement orders first and allocate the next two unique integers. Do not insert 334, 501 or any weekly target.

- [ ] **Step 6: Read back and verify the exact records**

Assert that only the selected `project_key` received the two records, quantities are 1 and 2, and all target tables remain empty until a user enters a real meta in the panel.

---

### Task 8: Full automated and visual verification

**Files:**
- Verify all changed files.

**Interfaces:**
- Consumes: complete local implementation and remote schema.
- Produces: current evidence for completion review.

- [ ] **Step 1: Read and use the required verification skill**

Read `superpowers:verification-before-completion` completely and follow its evidence rules before making any success claim.

- [ ] **Step 2: Run the complete Python suite**

Run: `python -m unittest discover -s tests -p "test_*.py" -v`  
Expected: all tests PASS.

- [ ] **Step 3: Run repository checks**

Run: `pnpm lint`  
Run: `pnpm test`  
Run: `pnpm build`  
Run: `git diff --check`  
Expected: every command exits 0. If an unrelated pre-existing failure appears, document exact evidence and keep it separate from feature failures.

- [ ] **Step 4: Start the local Streamlit app with a real database connection**

Use an existing secure local secret or temporary process environment without printing it. Start the app hidden, open it in the in-app browser, and verify both tabs, project changes, target writes and requirement writes.

- [ ] **Step 5: Capture desktop and mobile evidence**

Inspect at 1600×900, 1366×768 and approximately 390×844. Compare with `Mtech_Modelo_1_Executivo.png`; confirm headers, six columns, two aligned panels, colors, negative signs, status text, TINTA position, summary cards, no clipped text and mobile stacking.

- [ ] **Step 6: Confirm real-data agreement**

For the selected project, compare every displayed remittance and return total against an independent read-only Supabase aggregation. Confirm project switching never combines identities.

- [ ] **Step 7: Commit final visual or test corrections**

```bash
git add weekly_control.py weekly_control_data.py weekly_control_view.py streamlit_app.py tests supabase/migrations
git commit -m "fix: concluir validacao do controle semanal"
```

Create this commit only when corrections exist; otherwise preserve the existing task commits.

---

### Task 9: Code review, publication and online verification

**Files:**
- Review the complete branch diff.

**Interfaces:**
- Consumes: verified branch and authorized GitHub access.
- Produces: published Streamlit version on the official URL.

- [ ] **Step 1: Read and use the required code-review skill**

Read `superpowers:requesting-code-review` completely. Because subagents are prohibited, perform the prescribed review inline against the spec, inspect the full diff, and resolve every blocking finding before publication.

- [ ] **Step 2: Verify branch and deployment target**

Confirm the official Streamlit app is deployed from `origin/codex/painel-pintura-mtech` by comparing a unique current UI marker with the online app. Do not merge or overwrite the unrelated-history `origin/main` branch.

- [ ] **Step 3: Push the verified branch**

Run: `git push origin codex/painel-pintura-mtech`  
Expected: push succeeds and Streamlit Cloud begins redeployment.

- [ ] **Step 4: Wait for and inspect the official deployment**

Open `https://painel-pintura-mtech.streamlit.app/`, wait for the new version, verify both tabs and repeat critical desktop/mobile checks using real Supabase data.

- [ ] **Step 5: Perform one real manual workflow online**

Select a project, enter a user-confirmed cumulative meta for a chosen week, confirm the save, reload the page and verify persistence. Do not invent the value; if the user has not supplied a production meta at that time, verify the editor with an existing approved record or leave the target table unchanged.

- [ ] **Step 6: Report delivery evidence**

Report files created/modified, Supabase tables/columns used, formulas, project identity rule, tests/build outputs, visual comparison, migration status, online URL and any remaining incomplete component metadata.
