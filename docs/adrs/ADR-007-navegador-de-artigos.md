# ADR-007 — Pivô para navegador de artigos

Status: aceito (2026-10)

## Contexto
O produto era um resumidor com IA. O estudo em `docs/roadmap/navegador-de-artigos-descoberta.md` e a maquete em `prototype/navegador/` mostraram mais valor em descobrir, ler e organizar artigos, deixando a IA como apoio. Leitura apenas do resumo (decisão do usuário); sem incorporar páginas de editoras.

## Decisão
1. `/` é o navegador; o laboratório de IA fica em `/ia` e segue com todas as garantias anteriores (ADR-005).
2. Uma fonte primária por busca (`catalog.py`): Europe PMC por padrão, OpenAlex opcional (exige chave gratuita do operador), com fallback controlado em `discovery.py`.
3. Biblioteca, etiquetas e listas por conta em `library_store.py`, com SQL único para SQLite e PostgreSQL (`db.py`). Link público é um token revogável, somente leitura, sem dados do dono.
4. Frontend sem dependências, URL tratada como entrada não confiável, DOM por `textContent`, links só http(s).
5. Camada sem IA primeiro: seções originais, números com a frase de origem, tipos de estudo oficiais.

## Consequências
- (+) Uso sem custo de tokens no caminho principal; IA opcional e isolada.
- (−) Dependência de APIs externas (limites e disponibilidade); mitigada por cache e limites por cliente.
- (−) Caminho PostgreSQL ainda não validado em instância real; validar antes de depender dele em produção.
