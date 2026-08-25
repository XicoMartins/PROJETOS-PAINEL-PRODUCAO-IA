# Controle semanal no Streamlit — Especificação de desenho

**Data:** 2026-08-25  
**Classificação:** mudança arquitetural  
**Painel oficial:** `https://painel-pintura-mtech.streamlit.app/`

## 1. Objetivo

Adicionar ao painel Streamlit existente uma aba chamada **Controle semanal**, reproduzindo com alta fidelidade a página 1 do material executivo fornecido. A nova aba compara a semana anterior com a semana atual, usa dados reais do Supabase e preserva a visão gerencial atual.

Esta especificação substitui a proposta inicial de implementar uma rota Next.js/Sites. Por decisão explícita do usuário, a entrega será feita somente no painel Streamlit oficial. Sites, Next.js e `production_entries` ficam fora do escopo.

## 2. Decisões aprovadas

- `painting_entries` será a única fonte de movimentos de remessa e retorno.
- O painel continuará conectado ao Supabase no servidor; credenciais nunca serão enviadas ao navegador.
- Metas semanais, quantidade por conjunto e ordem dos componentes não serão fixadas no código.
- Duas tabelas auxiliares guardarão somente metadados de planejamento.
- Os valores do material visual serão usados apenas em testes automatizados.
- A aba será publicada no painel Streamlit ao final, depois da verificação local.
- Não serão usados subagentes.

## 3. Descoberta da base atual

O Supabase possui três tabelas públicas: `painting_entries`, `production_entries` e `process_forecasts`. Não existem tabelas, views, migrations ou colunas que armazenem metas semanais, quantidade por conjunto ou ordem visual dos componentes.

### 3.1 Colunas utilizadas de `painting_entries`

| Coluna | Uso |
| --- | --- |
| `id` | desempate determinístico e rastreabilidade |
| `timestamp` | última atualização dos movimentos |
| `cliente` | parte da identidade exata da origem |
| `display` | parte da identidade exata da origem |
| `numero_display` | identificador estável do display/lote operacional |
| `codigo_pintura` | separação de cor/código de pintura |
| `maquinario` | identificação auxiliar de remessa ou retorno |
| `processo` | componente, movimento e linha TINTA |
| `data_producao` | data operacional do movimento |
| `quantidade` | incremento a somar no acumulado |
| `quantidade_total` | conferência do acumulado registrado |
| `created_at` | atualização e desempate auxiliar |

O projeto ativo identificado na inspeção possui a identidade exata:

- `cliente = FEMSA`
- `display = PG + ECONOMIA HIBRIDO`
- `numero_display = 26081000`
- `codigo_pintura = VM - 1000`

Essa identidade foi usada somente para validar a modelagem. Ela não será fixada no código; será armazenada no lote semanal ativo.

Nos dados atuais desse projeto, `SUM(quantidade)` por componente e movimento coincide com o último `quantidade_total`. O cálculo usará a soma dos incrementos de `quantidade`, preservando o modelo operacional já utilizado pelo painel.

## 4. Migration mínima proposta

### 4.1 `painting_weekly_lots`

Armazena o planejamento semanal e a identidade exata da origem dos movimentos.

| Coluna | Tipo/Regra | Finalidade |
| --- | --- | --- |
| `id` | `bigint generated always as identity`, PK | identificador técnico |
| `project_key` | `text not null` | chave canônica compartilhada entre semanas e requisitos |
| `project_label` | `text not null` | título apresentado no painel |
| `source_cliente` | `text not null` | filtro exato em `painting_entries.cliente` |
| `source_display` | `text not null` | filtro exato em `painting_entries.display` |
| `source_numero_display` | `text not null` | filtro exato em `painting_entries.numero_display` |
| `source_codigo_pintura` | `text not null` | filtro exato em `painting_entries.codigo_pintura` |
| `week_start` | `date not null` | segunda-feira da semana planejada |
| `week_end` | `date not null` | sexta-feira da semana planejada |
| `target_sets` | `integer not null check (target_sets > 0)` | meta da semana em conjuntos |
| `status` | `text not null` com check | `planned`, `active` ou `closed` |
| `created_at` | `timestamptz not null default now()` | auditoria |
| `updated_at` | `timestamptz not null default now()` | auditoria |

Restrições:

- `week_end = week_start + 4`;
- `week_start` deve ser uma segunda-feira;
- unicidade de `project_key` e `week_start`;
- índice para localizar lotes por período e status.

### 4.2 `painting_component_requirements`

Armazena os requisitos de montagem e a apresentação dos componentes.

| Coluna | Tipo/Regra | Finalidade |
| --- | --- | --- |
| `id` | `bigint generated always as identity`, PK | identificador técnico |
| `project_key` | `text not null` | vínculo lógico com os lotes |
| `source_component_key` | `text not null` | componente normalizado encontrado em `painting_entries` |
| `display_name` | `text not null` | nome executivo exibido na tabela |
| `quantity_per_set` | `numeric not null check (quantity_per_set > 0)` | consumo por conjunto |
| `display_order` | `integer not null check (display_order >= 0)` | ordem visual |
| `active` | `boolean not null default true` | vigência do requisito |
| `created_at` | `timestamptz not null default now()` | auditoria |
| `updated_at` | `timestamptz not null default now()` | auditoria |

Restrições:

- unicidade de `project_key` e `source_component_key`;
- unicidade de `project_key` e `display_order`;
- índice para requisitos ativos por projeto e ordem.

Não será criada uma terceira tabela de projetos neste momento. `project_key` atende à necessidade atual com a menor migration possível; a normalização adicional fica adiada até existir mais de um consumidor que a justifique.

### 4.3 Segurança

As duas tabelas terão RLS habilitado. O aplicativo continuará acessando o banco somente no servidor pela conexão protegida existente. Políticas adicionais serão limitadas às funções realmente usadas pelo ambiente atual.

A inspeção encontrou RLS desabilitado em `process_forecasts`. Essa tabela não participa desta entrega e não será alterada sem uma autorização específica.

## 5. Seleção das semanas e do projeto

Todos os cálculos de calendário usarão `America/Sao_Paulo`.

- Semana atual: segunda a sexta da semana que contém a data corrente.
- Semana anterior: segunda a sexta imediatamente anterior.
- A aba localizará o lote da semana atual com status `active`.
- O lote anterior será localizado pelo mesmo `project_key` e pelo início da semana anterior.
- A identidade de origem do lote ativo filtrará `painting_entries` por igualdade exata nas quatro colunas de origem.
- Nenhum lançamento de outro display, número ou código de pintura será combinado.
- Se houver inconsistência entre múltiplos lotes ativos, a aba mostrará erro de configuração em vez de escolher silenciosamente.

Os dois painéis usarão a mesma fotografia acumulada de movimentos do projeto ativo. Somente a meta usada na comparação será diferente.

## 6. Normalização e agregação

### 6.1 Movimento

A normalização seguirá as regras já existentes no painel:

1. `processo` contendo `RETORNO` produz movimento `retorno`;
2. `processo` contendo `ENVIO` ou `REMESSA` produz movimento `remessa`;
3. se `processo` não definir o movimento, aplicar as mesmas regras a `maquinario`;
4. texto sem movimento reconhecível não entra nas somas e gera diagnóstico de dados ignorados.

### 6.2 Componente

O nome operacional será normalizado removendo marcadores de movimento, separadores repetidos, espaços extras e diferenças de maiúsculas/acentuação para formar `source_component_key`. A mesma função será usada ao preparar os requisitos e ao ler os movimentos, evitando regras divergentes.

### 6.3 Totais

Para cada componente configurado:

```text
totalRemessa = soma de quantidade dos movimentos de remessa
totalRetorno = soma de quantidade dos movimentos de retorno
saldoPintura = totalRemessa - totalRetorno

necessidadeLoteAnterior = metaConjuntosSemanaPassada × qtdPorConjunto
saldoLoteAnterior = totalRetorno - necessidadeLoteAnterior

necessidadeLoteAtual = metaConjuntosSemanaAtual × qtdPorConjunto
saldoLoteAtual = totalRemessa - necessidadeLoteAtual
```

- Saldo negativo é pendente.
- Saldo igual ou maior que zero está coberto.
- Peças pendentes são a soma do valor absoluto somente dos saldos negativos.
- Referências pendentes são a contagem dos componentes com saldo negativo.
- Total de componentes do lote é a meta em conjuntos multiplicada pela soma das quantidades por conjunto.

Ausência de um movimento não será convertida silenciosamente em zero. A célula exibirá `—`; cálculos dependentes também ficarão indisponíveis. Um zero gravado explicitamente permanece zero.

### 6.4 TINTA

Processos normalizados iniciados por `TINTA` serão agregados separadamente e apresentados como a última linha. TINTA não terá quantidade por conjunto e não participará da capacidade, do total de componentes ou das pendências.

## 7. Interface Streamlit

O aplicativo terá navegação direta entre:

- **Visão gerencial** — conteúdo atual preservado;
- **Controle semanal** — nova visualização executiva.

A interface semanal terá:

- cabeçalho grafite com filete vermelho, etiqueta, título, projeto e subtítulo;
- painel esquerdo vinho para a semana passada, com coluna `P/ FECHAR`;
- painel direito verde-petróleo para a semana atual, com coluna `P/ ENVIAR`;
- colunas `COMPONENTE`, `QT/DY`, `REMESSA`, `RETORNO`, `SALDO` e saldo da meta;
- linha TINTA destacada no final;
- legenda que não dependa somente de cores;
- totais de conjuntos, componentes, peças pendentes e referências pendentes;
- card `Próxima ação: priorizar linhas em vermelho`;
- data/hora da última atualização em `America/Sao_Paulo`.

Em desktop, os painéis ficarão lado a lado sem rolagem horizontal. Em telas menores, serão empilhados com semana passada primeiro. A tabela terá marcação semântica e foco visível na navegação.

## 8. Estados e erros

A aba distinguirá explicitamente:

- carregamento;
- conexão ou consulta indisponível;
- migration ainda não aplicada;
- nenhum lote ativo para a semana;
- lote anterior ausente;
- múltiplos lotes ativos;
- projeto sem movimentos;
- requisito ausente ou incompleto;
- dados válidos.

Erros do Supabase nunca serão substituídos por dados demonstrativos. O painel poderá exibir os dados disponíveis parcialmente, desde que sinalize quais cálculos estão indisponíveis e por quê.

## 9. Organização do código

A implementação deverá manter responsabilidades separadas:

- `streamlit_app.py`: integração da navegação e composição de alto nível;
- novo módulo de domínio semanal: tipos, calendário, normalização, fórmulas e montagem do modelo de apresentação;
- novo módulo de acesso semanal: consultas de lotes, requisitos e movimentos;
- novo módulo de visualização semanal: HTML/CSS escopado e estados da aba;
- arquivo de migration SQL versionado no projeto;
- testes Python específicos para domínio, acesso e renderização.

Funções equivalentes já existentes em `streamlit_app.py` ou `painting_references.py` serão reutilizadas ou extraídas cuidadosamente. Não serão mantidas duas implementações divergentes de normalização.

## 10. Estratégia de testes

O desenvolvimento seguirá TDD. Antes de cada comportamento, será criado um teste que falha; depois será implementado apenas o necessário para fazê-lo passar.

Cobertura obrigatória:

- semanas em `America/Sao_Paulo`;
- fórmulas dos dois lotes;
- pendências e contagem de referências;
- total de componentes;
- quantidade por conjunto ausente;
- ausência de movimento versus zero explícito;
- separação de TINTA;
- normalização de remessa, retorno e componente;
- filtro exato do projeto;
- lotes ausentes ou conflitantes;
- renderização das duas áreas de navegação;
- estados de erro e base vazia;
- ausência de valores demonstrativos na produção.

Os números da página 1, incluindo 334 e 501, serão usados apenas como fixtures dos testes das fórmulas.

## 11. Validação visual e publicação

Antes de publicar:

1. executar todos os testes Python afetados;
2. executar as verificações existentes do repositório que continuarem aplicáveis;
3. executar `git diff --check`;
4. iniciar o Streamlit localmente;
5. comparar a aba com a referência em 1600×900 e 1366×768;
6. validar o empilhamento em aproximadamente 390×844;
7. conferir que os números locais correspondem às consultas reais;
8. revisar segurança e desempenho após a migration.

Depois da validação, a versão será publicada no mecanismo já usado pelo painel Streamlit oficial e o endereço `https://painel-pintura-mtech.streamlit.app/` será verificado novamente.

## 12. Dados iniciais ainda necessários

A migration criará a estrutura, mas não inventará registros de produção. Antes de popular as novas tabelas, será necessário obter ou aprovar explicitamente:

- metas reais da semana anterior e da semana atual;
- origem autorizada das quantidades por conjunto e da ordem dos componentes;
- rótulo executivo definitivo do projeto.

A planilha local inspecionada contém requisitos para oito componentes do projeto PG + Economia Híbrido, mas ela não será importada sem aprovação explícita. Os componentes da referência visual que não aparecem no projeto ativo também não serão acrescentados artificialmente.

## 13. Fora do escopo

- Next.js, Sites e Cloudflare;
- `production_entries` e `process_forecasts`;
- alteração da área de lançamentos;
- filtros adicionais de projeto;
- refatorações sem relação com a entrega;
- uso de valores da referência como dados de produção.
