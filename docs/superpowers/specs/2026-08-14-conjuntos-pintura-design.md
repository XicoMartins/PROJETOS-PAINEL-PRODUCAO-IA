# Conjuntos completos de pintura — especificação de desenho

## Objetivo

Acrescentar ao resumo inferior esquerdo do painel as quantidades de conjuntos completos enviados e retornados. O cálculo deve usar as referências `QNT` das planilhas mantidas em `S:\PROJETOS EM ANDAMENTO\PAINEL DE CONTROLE MTECH\PROGRAMAS\PROJETOS - PAINEL PRODUÇÃO IA\planilhas_pintura`, detectar arquivos novos ou alterados automaticamente e nunca indisponibilizar o painel por causa de uma referência ausente ou inválida.

## Escopo

- Alterar o painel Streamlit, que é a implementação operacional do relatório.
- Manter a exportação PNG coerente com a tabela exibida no navegador.
- Não alterar as planilhas de referência.
- Não alterar os cálculos atuais de peças, ritmo semanal, prazos ou status.
- Não ampliar este trabalho para a página Next.js de demonstração, que não é a fonte operacional do painel.

## Fonte e descoberta das referências

O diretório será configurável pela variável `MTECH_PAINTING_LISTS_DIR`. Na ausência da variável, o caminho de rede informado acima será usado como padrão.

O carregador deverá:

1. Enumerar arquivos `.xlsx` diretamente no diretório, sem percorrer subpastas.
2. Ignorar arquivos temporários do Excel cujo nome comece por `~$`.
3. Construir uma assinatura com nome, tamanho e data de modificação de cada arquivo. A assinatura invalida o cache quando um arquivo é criado, removido ou alterado.
4. Abrir as planilhas em modo somente leitura e com valores calculados.
5. Localizar colunas pelo texto normalizado do cabeçalho, e não pela letra física. `QNT` pode estar em D ou E.
6. Aceitar as variações observadas de estrutura: `CLIENTE` é opcional; `ACABADO`, `FERRAMENTAL`, `PROCESSO` e `QNT` são campos de referência.
7. Tratar `QNT` vazio, não numérico, zero ou negativo como referência inválida.

Para manter a leitura simples e rápida, será adicionada a dependência `openpyxl>=3.1,<4`, usada somente para leitura dos `.xlsx`.

## Normalização e relacionamento

As comparações devem ser tolerantes a caixa, acentos, espaços repetidos e variações dos textos de envio/retorno.

- `ACABADO` identifica o display e será comparado com o display dos lançamentos após a normalização já usada pelo painel.
- O movimento será derivado de `FERRAMENTAL` e, como alternativa, de `PROCESSO`: textos contendo envio ou remessa representam `remessa`; textos contendo retorno representam `retorno`.
- `PROCESSO` será convertido ao mesmo nome-base usado nas linhas filhas do painel, removendo marcadores de envio/retorno e normalizando o texto.
- A chave efetiva da referência será display + processo normalizado + movimento.
- Referências duplicadas com o mesmo `QNT` serão consolidadas. Duplicidades com valores diferentes serão consideradas ambíguas e produzirão alerta, sem escolher silenciosamente um divisor.

## Regra de cálculo

O cálculo usa os totais históricos já mostrados nas colunas `Enviado total` e `Retornado total`, não apenas o período filtrado.

Para cada linha de processo:

- `conjuntos enviados = floor(enviado total do processo / QNT de remessa)`
- `conjuntos retornados = floor(retornado total do processo / QNT de retorno)`

Somente conjuntos completos são contabilizados; qualquer parte fracionária é descartada.

Para a linha principal do display:

- `Conj. enviados` é o menor valor de conjuntos enviados entre os processos necessários e relacionados.
- `Conj. retornados` é o menor valor de conjuntos retornados entre os processos necessários e relacionados.

Se qualquer processo necessário não possuir uma referência válida para o movimento calculado, o valor do display para esse movimento será desconhecido (`None`) em vez de zero. Isso evita apresentar ausência de cadastro como ausência de conjuntos.

## Modelo de dados

Um módulo dedicado, `painting_references.py`, será responsável por descobrir, ler, normalizar e indexar as referências. Ele exporá estruturas pequenas e testáveis, sem depender do Streamlit para a regra de negócio.

`ProcessVolume` ganhará:

- `sent_sets: int | None`
- `returned_sets: int | None`

`Project` ganhará:

- `sent_sets: int | None`
- `returned_sets: int | None`
- `reference_warnings: tuple[str, ...]`

O carregador retornará o índice das referências e diagnósticos de arquivos. `build_projects` receberá esse índice, calculará os conjuntos por processo e consolidará o mínimo por display.

## Apresentação

A tabela ganhará duas colunas:

- `Conj. enviados`, imediatamente depois de `Enviado total`.
- `Conj. retornados`, imediatamente depois de `Retornado total`.

As linhas de processo e as linhas principais exibirão números inteiros. Quando o cálculo não for possível, exibirão `—`.

As larguras serão redistribuídas para manter a tabela legível dentro do painel inferior esquerdo, sem rolagem horizontal no tamanho normal do relatório. O rodapé explicará que conjuntos são totais completos calculados por `total ÷ QNT`, e que a linha do display usa o menor resultado entre os processos.

Quando houver falha de diretório, arquivo, cabeçalho, `QNT`, duplicidade ambígua ou correspondência, o painel exibirá um aviso compacto de referências. O aviso identificará os arquivos ou display/processos afetados, será escapado antes de entrar no HTML e não impedirá os demais dados de serem mostrados. A exportação PNG também levará as duas colunas e uma indicação compacta de referência ausente.

## Desempenho e resiliência

- A assinatura do diretório será barata e executada a cada atualização automática.
- O conteúdo das planilhas será mantido em cache enquanto a assinatura não mudar.
- Cada arquivo será processado de forma isolada; a falha de um arquivo não cancela os demais.
- Arquivos bloqueados temporariamente pelo Excel serão registrados como aviso, preservando o funcionamento do painel.
- O cache não esconderá adições, remoções ou atualizações de arquivos porque a assinatura fará parte da chave de leitura.

## Testes e critérios de aceitação

Serão adicionados testes Python com planilhas temporárias que comprovem:

1. Descoberta de `QNT` tanto na coluna D quanto na E.
2. Ignorar arquivos `~$`.
3. Invalidação lógica da assinatura após criar ou alterar um arquivo.
4. Normalização de display, processo e movimento.
5. Cálculo inteiro por piso para envio e retorno.
6. Consolidação pelo menor número de conjuntos entre processos.
7. `—` e aviso quando uma referência estiver ausente, inválida ou ambígua.
8. Continuidade quando um dos arquivos estiver ilegível ou bloqueado.
9. Presença das duas novas colunas e do texto explicativo no HTML.
10. Presença dos valores de conjuntos na exportação PNG sem cortar cabeçalhos ou linhas relevantes.

A implementação estará concluída quando os testes Python passarem, o painel puder ser construído com referências válidas e inválidas, a exportação PNG for gerada com sucesso e a inspeção visual confirmar que a tabela inferior esquerda permanece legível.
