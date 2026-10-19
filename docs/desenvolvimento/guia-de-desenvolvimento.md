# Guia de desenvolvimento

Para quem vai alterar o código. Ambiente e comandos: [Preparar o ambiente](../development/setup.md). Visão do sistema: [Arquitetura](../arquitetura/visao-geral.md).

## Princípios ao programar
1. **Núcleo determinístico.** Se o resultado sustenta confiança (nota, extração, relatório, citação, alerta), **não use IA**. IA só no Laboratório.
2. **Serviços sem framework.** Regras de negócio ficam em módulos que não importam FastAPI; as rotas só validam entrada, chamam o serviço e formatam a resposta.
3. **Falha isolada.** Chamadas externas têm prazo, tratam erro e viram aviso ou "sem dados". Nunca derrube uma página por causa de uma fonte.
4. **Entrada não confiável.** Valide tamanhos e formatos na borda (Pydantic/`Query`), trate parâmetros de URL como hostis, nunca injete texto externo como HTML.
5. **Dono em toda consulta pessoal.** Qualquer leitura/escrita de dado de conta filtra pelo e-mail do dono.
6. **Limites explícitos.** Toda coleção por conta tem teto e mensagem clara ao atingi-lo.
7. **Declare os limites ao usuário.** Se um recurso mede algo parcial (nota, panorama), a interface diz o que não mede.

## Convenções de código
- Python **3.10+**, `from __future__ import annotations`, linhas de até 120 caracteres.
- **ruff** com as regras `E, F, W, I, B, UP, SIM, C4, RET, PIE, S` (config em `pyproject.toml`); **mypy** com a lista explícita de arquivos em `[tool.mypy] files`: **ao criar um módulo novo, inclua-o ali**.
- Comentários e docstrings em português, curtos; explique o **porquê**, não o óbvio. Nomes de domínio em português quando já são assim no módulo (ex.: `situacao`, `candidato`).
- Sem emojis na interface (testado).
- Tratamento de erros: use as exceções de `domain.py` (`DiggerError` e derivadas) com **mensagem segura para o usuário**; exceções inesperadas viram "Erro interno" e vão para o log.
- Tempo e aleatoriedade injetáveis (`clock`, `TTLCache`) para testar sem `sleep` longo.

## Como fazer mudanças comuns

### Adicionar uma fonte de busca
1. Criar `xxx_catalog.py` com uma classe que implemente `Catalog` (`id`, `name`, `study_types()`, `search(query)`, `get(ref)`; defina `combined = True` para a fonte entrar em "Todas as fontes") e converta tudo para `Work`.
2. Tratar erros de rede como `CatalogError` (o serviço os converte em aviso).
3. Registrar em `create_app()` (`biomedical_data_digger.py`).
4. Testes com respostas simuladas (sem rede), seguindo `tests/test_more_sources.py`.
5. Atualizar [Busca](../features/busca-artigos.md), [Integrações](../arquitetura/integracoes-externas.md) e [Licenças](../legal/licencas-e-termos.md).

### Adicionar uma fonte ao feed
1. `python scripts/verificar_feeds.py` com a URL candidata (título, link e data em cada item).
2. Escolher o **tipo** (`TIERS`) e as **áreas** (chaves de `interests.py`).
3. Acrescentar em `feed_sources.py`; atualizar `docs/features/feed.md` (contagem e lista).
4. Conferir os termos de uso da fonte.

### Adicionar uma área ou subtema de interesse
Editar o catálogo em `interests.py` (rótulo, termos em português e inglês). Cuidado com termos muito amplos: geram ruído nos alertas e no feed. Rode `tests/test_alerts.py` e `tests/test_feed.py`.

### Adicionar um tipo de aviso (sininho)
1. Incluir em `KINDS` (`notifications.py`) com prioridade e rótulo.
2. Produzir os avisos no vigia (`NotificationService.run`), com `dedupe_key` estável para não repetir.
3. Incluir na exportação e na exclusão de dados se houver nova tabela.
4. Testes e atualização de [Notificações](../features/notificacoes.md).

### Adicionar um critério à nota de confiabilidade
Mudar pesos altera **todas** as notas já exibidas e os relatórios: documente em [Confiabilidade](../features/confiabilidade.md), ajuste `tests/test_reliability.py` e registre no Changelog. Os pesos somam 100.

### Adicionar uma tabela ou coluna
Use `CREATE TABLE IF NOT EXISTS` em `initialize()` do armazém (**mudanças só aditivas**: não há migração). Garanta SQL compatível com SQLite e PostgreSQL (`?` como marcador; evite funções específicas). Implemente `delete_user_data` e inclua o dado na exportação da conta. Atualize [Modelo de dados](../arquitetura/dados.md).

### Adicionar uma rota
1. Modelo Pydantic com limites (ou `Query(max_length=…)`).
2. Rotas pessoais começam com `require_user(request)`; rotas que chamam fontes usam `identity(request)` para o limitador.
3. Resposta em JSON simples; erros por exceção de domínio.
4. Teste em `tests/test_browse_api.py` (ou próprio) e linha em [Referência da API](../api/referencia.md).

### Alterar o front-end
- Sem `style` nem `<script>` inline (CSP). Dimensões dinâmicas: `elemento.style.width = …` em JavaScript.
- Reinicie o servidor para atualizar o hash dos assets.
- Funções puras vão em `browse-lib.js` com teste em `tests/js/`.
- Verifique no desktop e no celular; veja [Front-end](../arquitetura/frontend.md).

### Alterar prompts do Laboratório de IA
Prompts clínicos foram usados em pronto-socorro: **só altere com validação clínica**. Rode `tests/test_prompt_contract.py` e, quando possível, a avaliação real em `evals/`.

## Fluxo de trabalho
1. Entender o pedido e ler o código vizinho.
2. Implementar com testes.
3. `ruff check`, `mypy`, `pytest`, `node --test` (ver [Testes](testes.md)).
4. Verificar no navegador quando houver mudança visual.
5. Atualizar documentação e [Changelog](../changelog/CHANGELOG.md).
6. Commit atômico (`tipo(escopo): descrição`), adicionando **arquivos por caminho explícito**.
7. Push para `main` somente com confirmação; o CI valida e o Render publica.

## Armadilhas já encontradas
- Heredocs com aspas e escapes (`\25`…) corrompem arquivos: prefira editar por ferramenta de arquivo.
- Atributo `style` inline não renderiza (CSP).
- Cookie `Secure` e HSTS só em produção: não aparecem em `localhost`.
- Mudar hash de assets exige reiniciar o servidor de desenvolvimento.
- Fontes públicas podem ficar lentas (OpenAIRE >20 s): o prazo de 8 s da busca combinada é de propósito.
- A ligação inglês ↔ português de substâncias **não** usa distância de edição (errava `valganciclovir` vs `valaciclovir`).
- `git add docs` pode incluir PDFs ou pastas que não devem subir; adicione por caminho.
