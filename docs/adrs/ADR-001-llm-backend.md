# ADR-001 — Backend de LLM: Groq API + Ollama fallback

## Status
Accepted

## Contexto
O projeto inicialmente usava exclusivamente Ollama (LLM local) para geração de resumos. O deploy em nuvem (Render, Hugging Face Spaces) não tem acesso ao Ollama local da máquina do usuário, tornando impossível hospedar o app publicamente com essa arquitetura.

## Decisão
Implementar detecção automática de backend:
- Se `GROQ_API_KEY` estiver definida → usa Groq API (nuvem)
- Se não estiver → usa Ollama local (fallback para desenvolvimento)

## Motivo
- Groq oferece plano gratuito com modelos de qualidade (gpt-oss, qwen)
- Zero custo para o caso de uso atual
- Mantém compatibilidade com desenvolvimento local via Ollama
- Sem necessidade de alterar código ao alternar entre ambientes

## Alternativas consideradas
- **Hugging Face Inference API:** descartado (requer assinatura PRO para Gradio Spaces)
- **OpenAI API:** descartado (custo)
- **Apenas Ollama:** inviável para produção em nuvem

## Consequências
- **Vantagem:** deploy gratuito no Render com modelos de qualidade
- **Vantagem:** desenvolvimento local continua funcionando sem internet
- **Limitação:** modelos disponíveis dependem da conta Groq (pode mudar)
- **Limitação:** sujeito a rate limits do plano gratuito Groq

## Data
2026 (durante desenvolvimento)
