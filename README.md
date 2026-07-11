# Mortes Violentas Intencionais nos bairros do Rio de Janeiro

Este repositório reúne os dados, códigos e resultados necessários para
reproduzir o Trabalho de Conclusão de Curso sobre Mortes Violentas
Intencionais (MVI) nos bairros do município do Rio de Janeiro entre 2019 e
2024.

A unidade da base final é o par bairro-ano. O painel é balanceado, com 159
bairros acompanhados em seis anos, totalizando 954 observações e 15 variáveis.
Anos sem registro de MVI, tiroteio ou ação policial são mantidos com contagem
zero. Ausências de covariáveis estruturais não são convertidas em zero.

## Resultados reproduzidos

- 7.419 Mortes Violentas Intencionais;
- 15.380 tiroteios;
- 4.337 ocorrências com ação policial;
- 159 bairros;
- 954 pares bairro-ano;
- nenhuma duplicata na chave `bairro + ano`;
- nenhuma ausência na base analítica final.

O modelo principal é um GEE binomial negativo com estrutura de correlação
permutável (`Exchangeable`). A especificação contém o polinômio completo do
tempo até o terceiro grau, ação policial, população total, domínio milícia,
renda e a interação entre ação policial e todos os termos do tempo.

## Estrutura do repositório

```text
01_preparacao_dados/      Tratamento e integração das fontes
02_analise_exploratoria/  Tabelas e figuras do Capítulo 5
03_modelagem/             GEE final e sensibilidade por distância de Cook
dados/brutos/             Arquivos originais necessários à reprodução
dados/intermediarios/     Bases produzidas por fonte
dados/finais/             Base longitudinal final
documentacao/             PDF final do TCC
resultados/figuras/       Figuras exportadas
resultados/tabelas/       Tabelas exportadas
resultados/relatorios/    HTMLs renderizados dos Rmds
resultados/auditorias/    Auditoria consolidada da reprodução
```

## História dos dados

O ponto de partida do estudo são os Registros de Ocorrência do Instituto de
Segurança Pública do Estado do Rio de Janeiro. Os registros foram filtrados
para o município do Rio de Janeiro, para o período de 2019 a 2024 e para as
categorias que compõem as Mortes Violentas Intencionais. Em seguida, os nomes
de bairros foram normalizados, comparados por distância textual, revisados
manualmente quando necessário e compatibilizados com a malha oficial de bairros.
O resultado dessa etapa é a contagem anual de MVI por bairro.

Os dados do Fogo Cruzado entram por duas variáveis anuais: número de tiroteios
e número de ocorrências com ação policial. O repositório contém o recorte usado
no fechamento do TCC, preservado como base padrão para reprodução. A consulta
atual da API continua disponível no alvo `make atualizar-fontes`, mas sua saída
é salva separadamente e não substitui a base congelada do TCC.

As variáveis do IPS Rio 2022 são Água e Saneamento e Pessoas Vivendo em
Favelas Não Urbanizadas. Elas são fixas no período porque têm um único ano de
referência. O Censo Demográfico de 2010 fornece população total e renda
domiciliar média por bairro, também repetidas nos seis anos do painel.

Os mapas anuais de domínio dos grupos armados são extraídos dos HTMLs
publicados pelo Fogo Cruzado, convertidos para GeoJSON e cruzados com as malhas
de bairros. As áreas são calculadas em SIRGAS 2000 / UTM zona 23S
(`EPSG:31983`) e expressas como percentual da área do bairro sob domínio de
ADA, CV, milícia e TCP.

A base final reúne essas fontes na mesma chave bairro-ano. Essa organização em
formato longo unidade-período permite acompanhar cada bairro ao longo do tempo
e sustenta a análise exploratória e a modelagem longitudinal do TCC.

## Execução

Requisitos principais:

- R 4.5 ou compatível;
- Python 3.11 ou 3.12;
- Pandoc;
- bibliotecas geoespaciais exigidas por `sf` e `geopandas`.

Crie os ambientes:

```bash
make setup
```

Reproduza todas as etapas usadas no TCC:

```bash
make all
```

Também é possível rodar por etapa:

```bash
make dados
make analise
make modelagem
make verificar
```

Para consultar novamente a API do Fogo Cruzado e os mapas on-line:

```bash
cp .env.exemplo .env
make atualizar-fontes
```

As credenciais devem ficar apenas no arquivo local `.env`, que não é
versionado. A atualização das fontes não altera a base congelada usada para
reproduzir o TCC.

## Relação entre capítulos e códigos

| Parte do TCC | Código principal | Resultado |
|---|---|---|
| Capítulo 3: fontes e variáveis | `01_preparacao_dados/` | Arquivos intermediários por fonte |
| Capítulo 4: tratamento do ISP | `01_preparacao_dados/01_tratamento_isp.ipynb` | MVI por bairro e ano |
| Capítulo 4: Fogo Cruzado | `01_preparacao_dados/02_baixar_fogo_cruzado.py` e `01_preparacao_dados/03_tratamento_fogo_cruzado.Rmd` | Tiroteios e ações policiais |
| Capítulo 4: IPS e IBGE | `01_preparacao_dados/04_tratamento_ips.Rmd` e `01_preparacao_dados/07_tratamento_ibge.Rmd` | Covariáveis estruturais |
| Capítulo 4: mapas das facções | `01_preparacao_dados/05_extrair_mapas_faccoes.py` e `01_preparacao_dados/06_calcular_areas_faccoes.Rmd` | Área anual dominada por grupo |
| Capítulo 4: base analítica | `01_preparacao_dados/08_construir_base_longitudinal.Rmd` | Painel balanceado com 954 linhas |
| Capítulo 5: análise exploratória | `02_analise_exploratoria/01_analise_exploratoria_centralizada.Rmd` | Tabelas e figuras descritivas |
| Capítulo 6: modelagem | `03_modelagem/01_modelagem_gee_final_distancia_de_cook.Rmd` | GEE final e sensibilidade por Cook |

## Dicionário de variáveis da base final

| Variável | Tipo | Variação | Definição | Fonte |
|---|---|---|---|---|
| `bairro` | texto | bairro | Nome oficial da unidade territorial | Prefeitura do Rio |
| `ano` | inteiro | 2019-2024 | Ano de observação | Painel longitudinal |
| `n_mvi` | inteiro | bairro-ano | Número de Mortes Violentas Intencionais | ISP-RJ |
| `bairro_id` | inteiro | bairro | Identificador interno do bairro | Painel longitudinal |
| `periodo` | inteiro | ano | Tempo de 1 a 6, correspondente a 2019-2024 | Painel longitudinal |
| `pct_area_dominacao_ada` | numérico | bairro-ano | Percentual da área sob domínio de ADA | Mapas do Fogo Cruzado |
| `pct_area_dominacao_cv` | numérico | bairro-ano | Percentual da área sob domínio do CV | Mapas do Fogo Cruzado |
| `pct_area_dominacao_milicia` | numérico | bairro-ano | Percentual da área sob domínio de milícia | Mapas do Fogo Cruzado |
| `pct_area_dominacao_tcp` | numérico | bairro-ano | Percentual da área sob domínio do TCP | Mapas do Fogo Cruzado |
| `ips_2022_agua_saneamento` | numérico | bairro | Indicador de Água e Saneamento | IPS Rio 2022 |
| `ips_2022_pessoas_vivendo_em_favelas_nao_urbanizadas` | numérico | bairro | Proporção de pessoas em favelas não urbanizadas | IPS Rio 2022 |
| `censo_2010_populacao_total` | inteiro | bairro | População total | IBGE, Censo 2010 |
| `censo_2010_rendimento_domiciliar_medio_brl` | numérico | bairro | Rendimento domiciliar médio, em reais | IBGE, Censo 2010 |
| `fc_total_tiroteios` | inteiro | bairro-ano | Número de tiroteios | Fogo Cruzado |
| `fc_acao_policial` | inteiro | bairro-ano | Número de ocorrências com ação policial | Fogo Cruzado |

As variáveis do IPS e do Censo são repetidas nos seis anos para preservar a
estrutura unidade-período. Essa repetição não representa atualização anual.

## Auditoria

O arquivo `resultados/auditorias/auditoria_reproducao_tcc.json` concentra as
checagens principais: dimensão da base, totais por fonte, duplicatas,
ausências, coeficientes do modelo final e presença dos artefatos esperados.

O PDF final está em `documentacao/TCC_Homicidios_2019_2024.pdf`.
