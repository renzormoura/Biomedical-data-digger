# Biomedical Data Digger

Aplicação web em Gradio para buscar artigos científicos, gerar resumos e executar análises especializadas com Groq ou Ollama.

## Funcionalidades

- Busca de artigos por palavra-chave em Europe PMC, OpenAlex, Semantic Scholar, Crossref e arXiv.
- Busca direta por PMID, PMCID, DOI, arXiv ID, OpenAlex ID, Semantic Scholar ID ou URL.
- Deduplicação e ordenação dos resultados por **Índice de Relevância Bibliográfica**.
- Filtros por áreas médicas, tecnologia, engenharias, química, física, matemática, ciências sociais, psicologia, economia, educação, direito, sustentabilidade e agricultura.
- Resumos gerais, acadêmicos e clínicos, além de análises de PICO, estatística, metodologia, medicamentos, alertas e aplicabilidade brasileira.
- Filtros de público, tom, idioma, nível de detalhe e foco temático.
- Cache em memória dos últimos 20 artigos e histórico das últimas 10 consultas.
- Cadastro e login com SQLite local ou PostgreSQL em produção.

## Índice de Relevância Bibliográfica

O indicador ajuda a ordenar resultados para descoberta bibliográfica. Ele **não é uma avaliação da qualidade metodológica, da validade clínica ou do risco de viés** do artigo.

O cálculo combina quatro componentes normalizados:

| Componente | Peso | Critério |
|---|---:|---|
| Impacto por ano | 40% | Citações divididas pela idade do artigo; o valor máximo é atingido em 20 citações por ano. |
| Atualidade | 25% | Pontuação decresce linearmente ao longo de 15 anos. |
| Metadados | 20% | Presença de título, revista, ano, DOI/PMID e URL. |
| Cobertura da fonte | 15% | Peso técnico da cobertura e identificação oferecida pela fonte consultada. |

O resultado fica entre `0.00` e `0.99`:

- `0.90` ou mais: alta relevância bibliográfica;
- `0.75` a `0.89`: boa relevância bibliográfica;
- abaixo de `0.75`: relevância bibliográfica moderada.

As citações são lidas de forma compatível com cada API (`citedByCount`, `cited_by`, `citationCount` ou `is-referenced-by-count`). Assim, fontes não médicas não recebem score artificialmente baixo por usarem nomes de campos diferentes.

## Execução local

Requisitos: Python 3.11.9 e Git.

```powershell
python -m venv venv
venv\Scripts\activate
pip install -r biomedical-article-summariser\requirements.txt
```

Crie `biomedical-article-summariser/.env`:

```env
GROQ_API_KEY=sua_chave_aqui
DATABASE_PATH=accounts.sqlite3
```

Execute:

```powershell
cd biomedical-article-summariser
python biomedical_data_digger.py
```

Acesse `http://localhost:7860`.

Sem `GROQ_API_KEY`, o projeto usa Ollama localmente. Nesse caso, o Ollama deve estar instalado e o modelo escolhido precisa estar disponível na máquina.

## Testes

Na raiz do repositório:

```powershell
python -m unittest discover -s tests -v
```

Os testes cobrem a busca multi-fonte, deduplicação, áreas gerais e cálculo do índice com campos normalizados.

## Deploy no Render

O deploy ocorre automaticamente após `git push` para `main`.

| Configuração | Valor |
|---|---|
| Root Directory | `biomedical-article-summariser` |
| Build Command | `pip install -r requirements.txt` |
| Start Command | `python biomedical_data_digger.py` |
| Python | `3.11.9` |
| Ambiente | `APP_ENV=production` |

Em produção, configure `GROQ_API_KEY` e `DATABASE_URL`. O PostgreSQL é necessário para preservar contas, pois o disco do plano Free do Render é efêmero.

## Estrutura principal

- `biomedical_data_digger.py`: interface Gradio e orquestração das análises.
- `article_services.py`: APIs de artigos, normalização, deduplicação, cache e índice de relevância.
- `llm_service.py`: integração Groq/Ollama.
- `prompt_builders.py`: prompts das análises.
- `account_store.py`: autenticação e persistência de contas.
- `tests/test_keyword_search.py`: testes da busca e do índice.

## Limitações

- O índice bibliográfico não substitui leitura crítica nem avaliação metodológica.
- A sumarização usa o abstract; a extração de texto completo existe para Europe PMC, mas ainda não está exposta como opção na interface.
- O Render Free pode hibernar após um período sem tráfego.
- Streaming permanece desativado por desempenho no plano Free.
