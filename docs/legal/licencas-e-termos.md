# Licenças e termos das fontes

> **Aviso.** Este documento é um levantamento técnico das fontes que o produto usa e das pendências para o uso comercial. **Não é parecer jurídico.** As colunas "situação conhecida" resumem o que se sabe das licenças e termos publicados; **cada item deve ser confirmado nos termos vigentes e, antes de cobrar pelo produto, validado por advogado**.

## Princípio de uso adotado
- O produto **não republica obras**: mostra metadados e resumo (já públicos nas bases de indexação), links para a fonte e trechos curtos, e oferece texto completo **somente quando a fonte o informa como aberto**, com a licença.
- Notícias e feeds: **título, trecho de até 300 caracteres e link**; quem clica vai à fonte; sem imagens e sem texto completo.
- Dados oficiais do Brasil: consultados de instantâneos versionados, com fonte e data.

## Fontes de artigos (busca e resolução)
| Fonte | Uso no produto | Situação conhecida | Antes de cobrar |
|---|---|---|---|
| Europe PMC | Busca, metadados, texto completo aberto (JATS) | API pública e gratuita; o texto completo segue a licença de cada artigo (o produto mostra a licença) | Ler os termos do serviço e a política de uso da API; manter atribuição |
| PubMed (NCBI E-utilities) | Busca e metadados | Dados do NLM de uso público; limite de requisições e identificação do cliente exigidos; resumos podem ter direitos dos editores | Ler a política de uso das E-utilities; usar `NCBI_API_KEY` e e-mail de contato |
| arXiv | Busca de preprints | Metadados abertos; termos de uso da API pedem uso moderado | Respeitar limites e atribuição |
| DOAJ | Busca | Metadados abertos da API pública | Confirmar a licença dos dados e termos da API |
| OpenAIRE | Busca | API aberta do OpenAIRE Graph | Confirmar a licença do grafo e termos de uso |
| OpenAlex | Busca (opcional, com chave) | Dados abertos | Confirmar termos e plano de uso da chave |
| Crossref | Resolução por DOI (*fallback*) | Metadados públicos | Seguir as regras de uso educado (*polite pool*) |
| Semantic Scholar | Resolução (*fallback*) | API com acordo de licença próprio | **Conferir se o acordo permite uso comercial**; se não permitir, remover do *fallback* |
| ClinicalTrials.gov | Enriquecimento | Dados públicos do governo dos EUA | Manter atribuição |
| OpenCitations | Contagem de citações | Dados abertos | Manter atribuição |
| DataCite | Dados relacionados | Metadados abertos | Manter atribuição |
| Google Acadêmico / páginas de editoras | Apenas quando a pessoa **cola um link**; o produto tenta extrair DOI ou título | Recurso herdado; raspagem de páginas pode violar termos | **Reavaliar ou remover** antes do lançamento comercial |

**Resumos de artigos.** Os resumos aparecem na página do artigo, em relatórios, fichas de leitura e exportações. Embora estejam amplamente indexados, os direitos podem ser dos editores. Mitigações atuais: atribuição de fonte e link, texto completo só quando aberto. **Avaliar com advogado** o uso de resumos em relatórios comerciais entregues a terceiros.

## Dados oficiais do Brasil
| Base | Licença / situação | Observação |
|---|---|---|
| ANVISA (dados abertos de medicamentos) | Dados abertos governamentais | Citar a fonte e a data |
| Conitec (recomendações) | Dado público governamental | Citar a fonte e a data |
| **Rename 2024** | **CC BY-NC-SA 4.0** (uso **não comercial**, atribuição e compartilhamento pela mesma licença) | **Bloqueio para uso comercial.** Opções: obter autorização/consulta formal ao Ministério da Saúde; usar apenas fatos não protegidos (a lista de nomes e componentes); retirar a Rename do produto pago |

## Feed (51 fontes)
- A lista foi montada apenas com **feeds públicos** destinados a redistribuição de manchetes.
- Cada fonte tem **termos de uso próprios**. Antes de cobrar, é preciso **revisar os termos de cada uma** e remover as que proíbem uso comercial ou agregação (basta apagar a entrada em `feed_sources.py`).
- O produto identifica o robô, usa requisição condicional e respeita o intervalo de 3 h por fonte.

## Modelos de linguagem
- **Groq:** uso conforme o contrato/plano da conta. Verificar limites de uso comercial, retenção e treinamento com dados enviados.
- Os modelos abertos (GPT-OSS, Qwen, Llama) têm licenças próprias (Apache 2.0/Llama Community License); conferir as condições de uso comercial do modelo escolhido.
- O texto enviado ao modelo é o **título e o resumo do artigo** (conteúdo público), nunca dados pessoais da conta.

## Dependências de software
Dependências Python fixadas em `requirements.txt` (FastAPI, Uvicorn, Jinja2, Requests, BeautifulSoup, lxml, loguru, groq, python-dotenv, psycopg). São bibliotecas de código aberto com licenças permissivas ou de *copyleft* fraco (psycopg: LGPL). Antes do lançamento, gerar o inventário de licenças (por exemplo, `pip-licenses`) e arquivar. O front-end não usa bibliotecas de terceiros.

## Lista de pendências para o lançamento comercial
1. Decidir a Rename (autorização ou retirada).
2. Revisar termos de cada fonte do feed.
3. Conferir licenças e termos de cada API de busca (principalmente Semantic Scholar e OpenAlex).
4. Reavaliar a extração de páginas de editoras/Google Acadêmico coladas pelo usuário.
5. Validar o uso de resumos em relatórios entregues a clientes.
6. Revisão jurídica dos [Termos de uso e da Política de privacidade](privacidade-e-lgpd.md).
7. Inventário de licenças das dependências.
