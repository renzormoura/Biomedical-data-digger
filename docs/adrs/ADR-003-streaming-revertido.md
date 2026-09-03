# ADR-003 — Streaming de resposta: implementado e revertido

## Status
Deprecated (decisão revertida)

## Contexto
O streaming (resposta palavra por palavra como no ChatGPT) foi implementado para melhorar a experiência do usuário, usando `stream=True` na Groq API e generators no Gradio.

## Decisão original
Implementar streaming via `generate_response_stream()` e generators no Gradio.

## Motivo da reversão
O Render free tier tem CPU extremamente limitada (0.1 CPU compartilhado). Cada chunk do stream aciona uma atualização da UI no Gradio, gerando overhead contínuo que tornou a aplicação **mais lenta** do que sem streaming. O usuário reportou lentidão em todas as requisições após a implementação.

## Decisão atual
Manter resposta sem streaming: a Groq processa tudo e retorna o texto completo de uma vez. O Gradio exibe com barra de progresso (`show_progress="full"`).

## Consequências
- **Vantagem:** performance adequada no free tier do Render
- **Vantagem:** código mais simples
- **Limitação:** sem feedback visual progressivo durante geração
- **Nota:** se o projeto migrar para um plano pago do Render (mais CPU), o streaming pode ser reativado com a função `generate_response_stream()` que permanece no código

## Arquivos afetados
- `llm_service.py`: função `generate_response_stream()` mantida no backend mas não utilizada pelos botões

## Data
2026 (durante desenvolvimento)
