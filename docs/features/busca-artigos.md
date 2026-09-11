# Feature: Busca de Artigos

## Objetivo

Permitir pesquisa por identificador, URL ou palavra-chave sem depender de uma única base. A aplicação combina resultados de fontes acadêmicas, remove duplicatas e apresenta uma lista ordenada por relevância bibliográfica.

## Fontes suportadas

| Fonte | Uso na busca | Identificadores |
|---|---|---|
| Europe PMC | Artigos biomédicos e abstracts | PMID, PMCID |
| OpenAlex | Obras acadêmicas e citações | OpenAlex ID, DOI |
| Semantic Scholar | Artigos, DOI e citações | Semantic Scholar ID, DOI |
| Crossref | Metadados editoriais e DOI | DOI |
| arXiv | Preprints | arXiv ID |

Na busca por palavra-chave, as cinco fontes são consultadas em paralelo. Se uma delas falhar, os resultados das outras continuam disponíveis. Se todas falharem, a aplicação informa o erro das fontes consultadas.

## Identificadores aceitos

- PMID: `33984217`
- PMCID: `PMC8234567`
- DOI: `10.1038/s41586-021-03819-2`
- arXiv: `2301.00001`
- OpenAlex: `W2741809807`
- URL completa de uma das fontes

A função `detect_input_type()` identifica o formato e `resolve_article()` encaminha a consulta para o adaptador correspondente.

## Normalização

Cada API retorna nomes e estruturas diferentes. Os adaptadores convertem os resultados para um formato comum:

```text
title, pmid, journal, year, doi, source, cited_by, url
```

A deduplicação prioriza DOI, depois PMID e, por fim, o título normalizado. Isso evita que o mesmo artigo apareça várias vezes quando é encontrado em bases diferentes.

## Filtro de áreas

O filtro compara palavras-chave do título e da revista. Ele inclui:

- Todas;
- Tecnologia e Computação;
- Engenharias Civil, Elétrica e Química;
- Química, Física e Matemática/Estatística;
- Ciências Sociais e Sociologia;
- Psicologia;
- Economia e Negócios;
- Educação;
- Direito e Políticas Públicas;
- Meio Ambiente e Sustentabilidade;
- Agricultura e Alimentos;
- Cardiologia, Oncologia, Endocrinologia, Infectologia, Neurologia, Pulmologia, Imunologia, Nefrologia e Pediatria.

O filtro é baseado em correspondência textual e não substitui classificação semântica completa.

## Índice de Relevância Bibliográfica

O índice serve para ordenar resultados de pesquisa. Ele não afirma que um artigo é metodologicamente melhor, clinicamente seguro ou livre de vieses.

### Fórmula

```text
impacto_por_ano = min((citações / idade_do_artigo) / 20, 1.0)
atualidade = max(0, 1 - idade_do_artigo / 15)
metadados = campos_presentes / 5

índice = (
    impacto_por_ano * 0.40
    + atualidade * 0.25
    + metadados * 0.20
    + cobertura_da_fonte * 0.15
)
```

A idade mínima é um ano para evitar divisão por zero. Quando o ano não está disponível, a idade padrão é 10 anos e a pontuação de atualidade é zero.

Os campos de metadados são título, revista, ano, DOI/PMID e URL. A cobertura da fonte é um peso técnico usado apenas para diferenciar a completude e a estabilidade dos metadados disponíveis:

| Fonte | Peso de cobertura |
|---|---:|
| Europe PMC / PubMed | 1.00 |
| OpenAlex | 0.95 |
| Semantic Scholar | 0.90 |
| Crossref | 0.85 |
| arXiv | 0.80 |
| Fonte não reconhecida | 0.70 |

As citações são normalizadas de acordo com a API: `citedByCount`, `cited_by`, `citationCount` ou `is-referenced-by-count`.

### Faixas exibidas

- `0.90` a `0.99`: Alta relevância bibliográfica;
- `0.75` a `0.89`: Boa relevância bibliográfica;
- `0.00` a `0.74`: Relevância bibliográfica moderada.

A interface mostra o índice e a fonte, mas recomenda leitura crítica do artigo antes de qualquer decisão acadêmica, técnica ou clínica.

## Arquivos relacionados

- `biomedical-article-summariser/article_services.py`
- `biomedical-article-summariser/biomedical_data_digger.py`
- `tests/test_keyword_search.py`
