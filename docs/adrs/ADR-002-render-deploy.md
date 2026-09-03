# ADR-002 — Plataforma de hospedagem: Render

## Status
Accepted

## Contexto
O projeto precisava de hospedagem pública gratuita para uma aplicação Gradio/Python. Hugging Face Spaces (opção inicial) exige assinatura PRO para hospedar apps Gradio no plano gratuito.

## Decisão
Usar Render.com como plataforma de hospedagem.

## Motivo
- Free tier gratuito sem cartão de crédito
- Suporta processos persistentes (essencial para Gradio — WebSocket)
- Deploy automático via push no GitHub
- SSL automático
- Suporte nativo a Python

## Alternativas consideradas
- **Hugging Face Spaces:** descartado — exige PRO para Gradio (erro 402)
- **Railway.app:** avaliado, Render escolhido por melhor documentação
- **Google Colab com share=True:** viável apenas para demos temporários (link expira em 72h)

## Consequências
- **Vantagem:** deploy gratuito e automático
- **Vantagem:** URL pública permanente
- **Limitação:** free tier hiberna após 15 minutos sem tráfego (primeira requisição lenta)
- **Limitação:** 512MB RAM, 0.1 CPU — streaming de LLM causa lentidão (ver ADR-003)
- **Restrição crítica:** `runtime.txt` com `python-3.11.9` e variável `PYTHON_VERSION=3.11.9` são obrigatórios — sem eles o Render usa Python 3.14 e o build falha (pydantic-core não tem wheel)

## Data
2026 (durante desenvolvimento)
