# ADR-006 — Substituição do Gradio por FastAPI e frontend próprio

**Status:** Aceito · 2026-10 · Substitui as partes de ADR-002 e ADR-003 que dependem do Gradio

## Contexto

O produto passou a ter público e identidade próprios. O Gradio, pensado para demos de ML, limitava:
identidade visual, autenticação real (estado em `gr.State`, sem sessão), limite de uso por conta,
acessibilidade e controle da superfície de segurança (rotas e API geradas automaticamente).
Havia também o desejo de reduzir dependência de frameworks de terceiros no que o usuário vê.

## Decisão

1. **Backend FastAPI** com rotas JSON (`/api/analyze`, `/audit`, `/compare`, `/cite`, `/search`,
   `/auth/*`). Os casos de uso (`workflow.py`) não mudaram: a camada de apresentação foi trocada.
2. **Frontend próprio**: uma página Jinja2 + `static/app.css` + `static/app.js`, sem framework JS,
   sem CDN e sem fontes externas. Identidade preto e laranja, tema claro opcional, responsivo,
   com foco visível, navegação por teclado nas abas e `prefers-reduced-motion`.
3. **Sessões e contas reais**: cookie HttpOnly/SameSite=Lax assinado por HMAC (`sessions.py`),
   `SESSION_SECRET` obrigatório em produção. O limite de uso passa a ser por conta; visitantes
   continuam permitidos, limitados por IP (último hop confiável de `X-Forwarded-For`).
4. **Segurança na borda**: validação com limites de tamanho (Pydantic), checagem de `Origin` em
   métodos de escrita, CSP `default-src 'self'` (sem scripts/estilos inline), HSTS em produção,
   `docs`/`openapi` desativados e erros inesperados sem vazamento de detalhes.
5. **Renderização de markdown no servidor** (`markdown_lite.py`): escapa todo texto antes de aplicar
   marcação e só admite links `http(s)`. O navegador recebe HTML sanitizado; todo o resto do DOM é
   montado com `textContent`.
6. **Assets versionados** (`?v=<mtime>`) para cache longo sem servir JS/CSS desatualizado.

## Consequências

- (+) Controle total de UX, acessibilidade e segurança; autenticação real; menos dependências
  (removidos Gradio e seus ~40 pacotes transitivos; ficam FastAPI, Uvicorn e Jinja2).
- (+) A API JSON permite futuros clientes (mobile, integrações) sem tocar nos casos de uso.
- (−) Perdemos widgets prontos e a fila do Gradio; hoje cada requisição roda em thread do Uvicorn.
  Se a carga crescer, vale mover a geração para uma fila de tarefas.
- (−) O histórico de artigos é local ao navegador (`localStorage`). Histórico por conta no servidor é
  o próximo passo natural agora que há sessão.
- Streaming continua desativado (ADR-003); com SSE seria simples reativar quando o plano de
  hospedagem permitir.
