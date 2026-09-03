# HANDOFF — Estado atual para continuação

## Data
Setembro 2026

## Estado geral
O projeto está **funcional e em produção** no Render. Não há tarefas interrompidas no momento.

## URL de produção
https://biomedical-data-digger.onrender.com

## Repositório
https://github.com/renzormoura/Biomedical-data-digger

## Último trabalho realizado
- Sistema universal de busca implementado: PMID, PMCID, DOI, arXiv, OpenAlex, Semantic Scholar e URLs
- 11 novos botões em 6 seções (accordions)
- Botão "Confiabilidade do Artigo" com score percentual
- Redesign visual completo com tema escuro/claro
- Documentação atualizada

## Próximos passos sugeridos (por prioridade)
1. **Atualizar README.md** — ainda desatualizado, descreve versão antiga com Ollama
2. **Testar novas fontes em produção** — arXiv, DOI via Semantic Scholar/CrossRef, OpenAlex
3. **Busca por palavras-chave** — permitir buscar artigos sem saber o ID (usando OpenAlex ou Semantic Scholar search)
4. **Export PDF/Word** — download do resultado formatado
5. **Texto completo** — ativar `fetch_full_text()` para PMCIDs quando decidir a UX

## Arquivos principais
| Arquivo | Descrição |
|---|---|
| `biomedical-article-summariser/biomedical_data_digger.py` | Orquestração e interface Gradio |
| `biomedical-article-summariser/article_services.py` | Busca, normalização e cache de artigos |
| `biomedical-article-summariser/llm_service.py` | Integração Groq/Ollama |
| `biomedical-article-summariser/prompt_builders.py` | Prompt base e análises especializadas |
| `biomedical-article-summariser/requirements.txt` | Dependências pinadas |
| `biomedical-article-summariser/runtime.txt` | Força Python 3.11.9 no Render |
| `biomedical-article-summariser/.env` | Secrets locais (NÃO commitado) |
| `docs/PROJECT-CONTEXT.md` | Contexto completo do projeto |

## Arquivos que NÃO devem ser modificados sem cuidado
- `runtime.txt` — remover ou alterar quebra o build no Render
- `.env` — nunca commitar
- Prompts clínicos em `prompt_builders.py` — usados em contexto real de PS
- `article_services.py` e `llm_service.py` — contratos usados pela interface e pelo fluxo de sumarização

## Próximos passos sugeridos (por prioridade)
1. **Atualizar README.md** — está desatualizado, descreve versão antiga com Ollama
2. **Decidir UX para texto completo** — `fetch_full_text()` já está implementada no código; falta definir como expor ao usuário sem sobrecarregar a interface
3. **Busca por palavras-chave** — permitir buscar artigos sem saber o PMID
4. **Export PDF/Word** — gerar documento formatado com o resultado

## Observações importantes
- Streaming foi implementado e revertido (ver ADR-003) — NÃO reimplementar sem upgrade do plano Render
- Toggle Rápido/Completo foi implementado e revertido a pedido do usuário — `fetch_full_text()` permanece no código para uso futuro
- A função `generate_response_stream()` existe no código mas não é usada — pode ser ativada futuramente
- O Render hiberna após 15 min sem uso — normal no free tier
- Modelos disponíveis na conta Groq atual: gpt-oss-20b (padrão), gpt-oss-120b, qwen3.6-27b, qwen3.8-27b
