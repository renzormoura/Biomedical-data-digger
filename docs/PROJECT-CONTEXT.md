# Biomedical Data Digger

## 1. Visão Geral

**O que é:** Aplicação web de sumarização de artigos biomédicos com interface Gradio, hospedada no Render.

**Problema resolvido:** Médicos, residentes e profissionais da saúde precisam extrair informações clínicas relevantes de artigos científicos de forma rápida, especialmente em ambientes de urgência/emergência onde o tempo é crítico.

**Público-alvo:** Médicos, residentes, estudantes de medicina, enfermeiros, farmacêuticos e profissionais da área da saúde em geral. Uso principal em pronto-socorro (PS) e UPA.

**Contexto de utilização:** O usuário pode inserir PMID, PMCID, DOI, arXiv ID, OpenAlex ID, Semantic Scholar ID ou URL. A aplicação busca o abstract na fonte correspondente, monta um prompt especializado e gera análises estruturadas usando LLM (Groq API em produção, Ollama local em desenvolvimento).

---

## 2. Estado Atual

```
STATUS: 🟢 Desenvolvimento ativo — Em produção no Render

CONCLUÍDO:
- Interface Gradio funcional
- Busca direta por PMID, PMCID, DOI, arXiv, OpenAlex, Semantic Scholar e URLs
- Busca por palavras-chave agregando Europe PMC, OpenAlex, Semantic Scholar, Crossref e arXiv
- Índice de Relevância Bibliográfica com fórmula documentada e campos normalizados por fonte
- Filtros de pesquisa médicos e gerais: tecnologia, engenharias, química, física, matemática, ciências sociais, psicologia, economia, educação, direito, sustentabilidade e agricultura
- 11 tipos de análise com prompts especializados
- Sistema de filtros de personalização (público, tom, idioma, detalhe, foco)
- Cache de artigos em memória (até 20 artigos por sessão)
- Histórico de sessão (últimas 10 consultas)
- Backend Groq API (produção) + Ollama local (desenvolvimento)
- Deploy no Render (free tier)
- .env para configuração local
- .gitignore protegendo secrets

EM DESENVOLVIMENTO:
- Nenhum item ativo no momento

PENDENTE / PLANEJADO:
- Integração com texto completo dos artigos (atualmente usa apenas o abstract)
- Export PDF/Word do resultado
- Streaming de resposta (implementado e revertido — ver ADR-003)

PROBLEMAS CONHECIDOS:
- Render free tier hiberna após 15 min sem uso (primeira requisição lenta)
- Streaming foi revertido por causar lentidão no free tier do Render

PRÓXIMO PASSO:
- Melhorar a avaliação metodológica sem confundir esse recurso com o índice bibliográfico
```

---

## 3. Stack Tecnológica

| Componente | Tecnologia | Versão |
|---|---|---|
| Linguagem | Python | 3.11.9 |
| Interface web | Gradio | 5.33.0 |
| HTTP client | requests | 2.32.3 |
| HTML/XML parser | beautifulsoup4 + lxml | 4.12.3 / 5.3.0 |
| Logging | loguru | 0.7.3 |
| LLM API (produção) | Groq SDK | 0.28.0 |
| LLM local (dev) | Ollama | (instalação local) |
| Variáveis de ambiente | python-dotenv | 1.0.1 |
| Hospedagem | Render (free tier) | — |
| Dados de artigos | Europe PMC, OpenAlex, Semantic Scholar, Crossref e arXiv | — |
| Controle de versão | Git + GitHub | — |
| Runtime (Render) | Python 3.11.9 via runtime.txt | — |

---

## 4. Arquitetura

**Padrão:** Aplicação Gradio com orquestração no arquivo principal e serviços separados por responsabilidade.

**Módulos:**
- `article_services.py`: cache, limpeza, detecção de identificadores e busca nas fontes externas.
- `llm_service.py`: seleção do backend Groq/Ollama e geração de respostas.
- `prompt_builders.py`: `SYS_PROMPT`, personalização e builders das análises.
- `biomedical_data_digger.py`: orquestração e interface Gradio.

**Fluxo principal:**
```
Usuário digita identificador, URL ou palavra-chave
        ↓
[Busca direta ou agregada] → fontes externas em paralelo
        ↓
Normalização + deduplicação + índice de relevância
        ↓
Cache armazena resultado
        ↓
build_dynamic_sys_prompt() → monta SYS_PROMPT com filtros
        ↓
build_message_*() → monta payload [system + user]
        ↓
Groq API (ou Ollama local) → gera resposta
        ↓
summariser_with_label() → formata output com label e filtros
        ↓
Gradio → exibe no output_box + atualiza histórico
```

**Detecção de backend:**
- Se `GROQ_API_KEY` estiver definida → usa Groq
- Se não estiver → usa Ollama local
- Definida via `.env` localmente, via Environment Variables no Render

---

## 5. Estrutura do Projeto

```
Biomedical_data_digger/
├── biomedical-article-summariser/
│   ├── biomedical_data_digger.py   ← prompts, orquestração e interface Gradio
│   ├── article_services.py         ← busca, normalização e cache de artigos
│   ├── llm_service.py              ← integração Groq/Ollama
│   ├── prompt_builders.py          ← prompt base e análises especializadas
│   ├── biomedical_data_digger.ipynb ← notebook de demonstração (legado)
│   ├── requirements.txt             ← dependências pinadas
│   ├── runtime.txt                  ← força Python 3.11.9 no Render
│   ├── README.md                    ← documentação de execução e arquitetura
│   └── .env                         ← secrets locais (não commitado)
├── docs/                            ← documentação técnica (criada agora)
│   ├── PROJECT-CONTEXT.md
│   ├── adrs/
│   ├── features/
│   ├── development/
│   └── roadmap/
├── .gitignore
└── venv/                            ← ambiente virtual local (não commitado)
```

---

## 6. Banco de Dados

Contas são persistidas pelo `account_store.py`. Em produção, o serviço usa
PostgreSQL por meio da variável `DATABASE_URL`; a tabela `users` é criada
automaticamente na inicialização. Em desenvolvimento local, SQLite é usado
como fallback em `accounts.sqlite3`. O Render Free usa disco efêmero, então
PostgreSQL é obrigatório em produção para que contas sobrevivam a hibernações,
reinícios e novos deploys.

Cache de artigos: implementado em memória Python (`dict` com lock de thread), válido apenas durante a sessão ativa do servidor. Limite de 20 entradas.

---

## 7. Autenticação e Autorização

O cadastro e login usam e-mail normalizado e senha derivada com PBKDF2-HMAC-SHA256,
com salt aleatório por usuário. A sessão ainda é mantida no estado da interface
Gradio; não há autorização por função ou controle de acesso a dados de artigos.

A única credencial é a `GROQ_API_KEY`, armazenada como variável de ambiente e nunca exposta na UI ou no código commitado.

---

## 8. Funcionalidades

| # | Funcionalidade | Status | Localização |
|---|---|---|---|
| F-01 | Busca por PMCID (texto completo XML) | ✅ | `get_xml_from_url()` + `fetch_article_abstract()` |
| F-02 | Busca por PMID numérico (abstract via JSON) | ✅ | `get_abstract_from_pmid()` |
| F-03 | Cache de artigos em memória | ✅ | `get_cached_article()` / `set_cached_article()` |
| F-04 | Histórico de sessão (últimas 10 consultas) | ✅ | `session_history` (gr.State) + `update_history()` |
| F-05 | Sumário geral (bullet points) | ✅ | `build_message_sumario()` |
| F-06 | Resumo Acadêmico | ✅ | `build_message_resumo_academico()` |
| F-07 | Resumo Clínico | ✅ | `build_message_resumo_clinico()` |
| F-08 | Resumo genérico neutro | ✅ | `build_message_resumo()` |
| F-09 | Medicamentos / Protocolos | ✅ | `build_message_medicamentos()` |
| F-10 | Alertas e Contraindicações | ✅ | `build_message_alertas()` |
| F-11 | Checklist Pré-Conduta | ✅ | `build_message_checklist()` |
| F-12 | Pergunta PICO | ✅ | `build_message_pico()` |
| F-13 | Dados Estatísticos | ✅ | `build_message_estatisticas()` |
| F-14 | Aplicabilidade Brasileira | ✅ | `build_message_aplicabilidade_br()` |
| F-15 | Crítica Metodológica | ✅ | `build_message_critica_metodologica()` |
| F-16 | Filtros de personalização (público, tom, idioma, detalhe, foco) | ✅ | `build_dynamic_sys_prompt()` |
| F-17 | Suporte Groq API (produção) | ✅ | `generate_response()` |
| F-18 | Suporte Ollama local (desenvolvimento) | ✅ | `generate_response()` |

---

## 9. Integrações Externas

### Europe PMC REST API
- **PMCID (texto completo):** `https://www.ebi.ac.uk/europepmc/webservices/rest/{pmcid}/fullTextXML`
- **PMID (abstract):** `https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=EXT_ID:{pmid}&resultType=core&format=json`
- Autenticação: nenhuma (API pública)

### Busca agregada de artigos
- **Europe PMC:** pesquisa bibliográfica e abstracts biomédicos.
- **OpenAlex:** obras, DOI, ano, revista e citações.
- **Semantic Scholar:** artigos, DOI, venue e citações.
- **Crossref:** DOI, título, revista, ano e referências recebidas.
- **arXiv:** preprints, título, ano e URL.
- As fontes são consultadas em paralelo; uma fonte indisponível não impede resultados das demais.

## 10. Índice de Relevância Bibliográfica

O índice é uma heurística de ordenação para descoberta bibliográfica. Ele não é
uma avaliação de qualidade metodológica, validade clínica ou risco de viés.

```text
40% impacto por ano: citações / idade do artigo, limitado a 20 citações por ano
25% atualidade: queda linear ao longo de 15 anos
20% metadados: título, revista, ano, DOI/PMID e URL presentes
15% cobertura da fonte: peso técnico da fonte consultada
```

O resultado é limitado ao intervalo `0.00`–`0.99` e classificado como alta
relevância (`>= 0.90`), boa relevância (`>= 0.75`) ou relevância moderada.
As APIs usam campos diferentes para citações; a camada de normalização converte
esses campos para `cited_by` antes do cálculo.

### Groq API
- SDK: `groq==0.28.0`
- Autenticação: `GROQ_API_KEY` via variável de ambiente
- Modelos disponíveis na conta atual:
  - `openai/gpt-oss-20b` ← **padrão** (mais rápido)
  - `openai/gpt-oss-120b`
  - `qwen/qwen3.6-27b`
  - `qwen/qwen3.8-27b`

### Ollama (desenvolvimento local)
- Usado apenas quando `GROQ_API_KEY` não está definida
- Modelos: qualquer modelo instalado localmente

---

## 11. Configurações (variáveis de ambiente)

```
GROQ_API_KEY=          ← obrigatória em produção
PORT=                  ← injetada automaticamente pelo Render
PYTHON_VERSION=        ← definida no painel do Render (3.11.9)
```

Arquivo `.env` local (não commitado) contém `GROQ_API_KEY` para desenvolvimento.

---

## 12. Regras que NÃO devem ser quebradas

- **NÃO commitar o arquivo `.env`** — o `.gitignore` já o protege
- **NÃO expor `GROQ_API_KEY` em código, logs ou documentação**
- **NÃO remover o `runtime.txt`** — sem ele o Render usa Python 3.14 e o build falha
- **NÃO remover a variável `PYTHON_VERSION=3.11.9`** do painel do Render
- **NÃO remover o cache de artigos** — ele evita chamadas redundantes às fontes externas
- **NÃO usar streaming no Render free tier** — causa lentidão por CPU limitada (ver ADR-003)
- **NÃO subir a pasta `venv/`** para o GitHub — já está no `.gitignore`
- **NÃO alterar os prompts especializados** sem validação clínica — são usados em contexto de pronto-socorro real
- **MANTER o aviso "AVISO DE USO CLÍNICO"** nos prompts de Medicamentos e Alertas
- **MANTER a restrição absoluta nos prompts** ("nunca preencha com conhecimento externo")

---

## 13. Banco de Dados / Migrations

Não aplicável.

---

## 14. Testes

Há testes automatizados em `tests/test_keyword_search.py` para busca e normalização,
combinação das cinco fontes, deduplicação, filtros de áreas gerais e cálculo do
Índice de Relevância Bibliográfica com campos normalizados.

PMIDs usados para teste durante o desenvolvimento:
- `33984217`
- `34238458`

---

## 15. Comandos Importantes

```bash
# Instalar dependências (com venv ativado)
pip install -r biomedical-article-summariser/requirements.txt

# Executar localmente
cd biomedical-article-summariser
python biomedical_data_digger.py

# Subir para o GitHub (aciona redeploy automático no Render)
git add biomedical-article-summariser/biomedical_data_digger.py
git commit -m "descrição"
git push

# Verificar sintaxe Python
python -c "import ast; ast.parse(open('biomedical_data_digger.py', encoding='utf-8').read()); print('OK')"

# Executar testes
python -m unittest discover -s tests -v
```

**Configuração do Render:**
- Root Directory: `biomedical-article-summariser`
- Build Command: `pip install -r requirements.txt`
- Start Command: `python biomedical_data_digger.py`
- Environment Variable: `GROQ_API_KEY`
- Environment Variable: `PYTHON_VERSION=3.11.9`

---

## 16. Referências funcionais

- `docs/features/busca-artigos.md`: fontes, normalização, filtros e fórmula do índice.
- `docs/features/analises-clinicas.md`: análises especializadas e regras dos prompts clínicos.
