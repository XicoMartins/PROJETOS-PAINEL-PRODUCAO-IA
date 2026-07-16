# Painel de Producao IA

Painel Streamlit para analise dos lancamentos do FORMS-MTECH.

## Fonte principal

Em producao, o painel le a tabela `production_entries` usando a mesma `DATABASE_URL`
configurada no app de lancamentos.

## Padrao produtivo para eficiencia operacional

As planilhas da pasta `planilhas` podem receber uma das colunas opcionais abaixo
na mesma linha de cada combinacao de `FERRAMENTAL` e `PROCESSO`:

- `pecas_por_hora_padrao`: taxa padrao em pecas por hora (prioritaria).
- `tempo_padrao_min_por_peca`: alternativa em minutos por peca, convertida por
  `60 / minutos`.

Nao preencha as duas colunas em linhas duplicadas para a mesma combinacao. Quando
mais de um padrao e encontrado para o mesmo maquinario e processo, o painel marca
a combinacao como duplicada e nao a utiliza. Planilhas sem essas colunas continuam
compativeis. Quando nao existe um padrao explicito, o painel usa como referencia
a taxa media ponderada do melhor operador no historico completo da fonte para a
mesma combinacao de display, maquinario e processo. Essa taxa e calculada como
`soma(producao + refugo) / soma(horas validas)` para cada operador; o maior
resultado positivo se torna o padrao historico. O padrao da planilha sempre tem
prioridade, e combinacoes duplicadas na planilha nao usam fallback silencioso.

Configure nos Secrets do Streamlit Cloud:

```toml
DATABASE_URL = "postgresql://usuario:senha@host:5432/banco?sslmode=require"
```

## Login de acesso

O painel exige usuario e senha antes de mostrar dados, filtros, graficos e tabelas.
Use o mesmo formato de Secrets do app FORMS-MTECH.

Para gerar o hash da senha:

```powershell
python scripts/gerar_hash_senha.py
```

Para um unico usuario:

```toml
[auth]
username = "seu_usuario"
password_hash = "pbkdf2_sha256$260000$..."
```

Para varios usuarios:

```toml
[auth.users]
admin = "pbkdf2_sha256$260000$..."
pcp = "pbkdf2_sha256$260000$..."
producao = "pbkdf2_sha256$260000$..."
```

## Deploy no Streamlit Cloud

1. Suba esta pasta em um repositorio GitHub.
2. No Streamlit Cloud, selecione o repositorio.
3. Main file: `streamlit_app.py`.
4. Configure o mesmo `DATABASE_URL` do FORMS-MTECH nos Secrets.

## Execucao local

```powershell
pip install -r requirements.txt
streamlit run streamlit_app.py
```

## Migrar SQLite legado para PostgreSQL

A base antiga fica em `PROJETOS -BACKEND/db.sqlite3`, tabela `core_productionentry`.
Para validar a leitura sem gravar:

```powershell
python scripts/migrate_sqlite_to_postgres.py --dry-run
```

Para migrar para o PostgreSQL:

```powershell
$env:DATABASE_URL="postgresql://usuario:senha@host:5432/banco?sslmode=require"
python scripts/migrate_sqlite_to_postgres.py
```

O script usa `ON CONFLICT DO NOTHING`, entao pode ser reexecutado sem duplicar
registros que ja existam por `source_hash` ou `import_key`.
