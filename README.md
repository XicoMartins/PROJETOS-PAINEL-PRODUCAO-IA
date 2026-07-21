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

Perfis podem ser definidos no mesmo Secret. A aba **PREVISÃO DE PROCESSO** é
exclusiva do perfil `admin`:

```toml
[auth.roles]
admin = "admin"
pcp = "user"
producao = "user"
```

Por compatibilidade com instalações anteriores, o usuário literalmente chamado
`admin` recebe esse perfil mesmo sem `[auth.roles]`. Para outros nomes, configure
o perfil explicitamente ou use `AUTH_ADMIN_USERS=usuario1,usuario2`.

## Previsão de processo

A previsão usa somente apontamentos com lote, quantidade positiva e duração
positiva, sempre segmentados por display, processo e maquinário. Duplicidades por
`id` são removidas e, com quatro ou mais lotes, taxas fora dos limites de Tukey
(1,5 IQR) são excluídas.

- **Provável:** `soma(quantidade) / soma(horas × operadores)` e ajuste pela
  quantidade prevista de operadores.
- **Otimista:** mediana dos 20% melhores lotes válidos.
- **Conservador:** mediana dos 20% piores lotes válidos.

Um único lote já gera previsão, com os três cenários iguais e confiança baixa.
A confiança é alta com 10 ou mais lotes, média com 5 a 9 e baixa com 1 a 4,
podendo ser reduzida quando o coeficiente de
variação ultrapassa 50% ou 80%. O término considera turno, horas produtivas,
dias da semana e feriados informados; não soma horas corridas.

O botão **Salvar previsão** cria, se necessário, a tabela PostgreSQL
`process_forecasts` e registra usuário, escopo, entradas, parâmetros e resultados.
O usuário do `DATABASE_URL` precisa de permissão para `CREATE TABLE` no primeiro
uso e de `SELECT`/`INSERT` nos usos seguintes.

Limitações da fonte atual: `production_entries` não possui cadastro de displays
ativos/cancelados, status formal de conclusão, paradas, feriados, turno ou
eficiência consolidada por lote. Por isso, conclusão é inferida por duração
positiva; feriados/turno são parâmetros da simulação; e a tela não inventa nem
exibe uma eficiência de lote inexistente.

### Máquinas, dependências e paralelismo

A tela possui dois modos:

- **Processo individual:** produtividade estimada × operadores por máquina ×
  máquinas disponíveis.
- **Roteiro: paralelos e dependentes:** carrega os processos e quantidades por
  produto da planilha do display e permite informar máquinas disponíveis por
  maquinário, máquinas alocadas, predecessores e processos paralelos.

A ordem da planilha é apenas uma sugestão inicial sequencial e deve ser revisada
pelo administrador. Processos `Iniciais` começam sem predecessor; processos
`Dependentes` aceitam um ou mais códigos separados por ponto e vírgula; processos
`Paralelos` herdam os predecessores do processo usado como referência. O
agendador rejeita ciclos e impede que a soma das máquinas alocadas em atividades
simultâneas ultrapasse a capacidade cadastrada. O cenário provável é apresentado
também em gráfico temporal.

Quando um ou mais processos não possuem nenhum lote válido, o sistema calcula um
**roteiro parcial** com os processos que têm dados. Processos ausentes são
omitidos e as dependências seguintes são reconectadas aos ancestrais disponíveis
mais próximos. A tela e o histórico registram explicitamente que o prazo não
representa 100% do roteiro e identificam os processos desconsiderados.

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
