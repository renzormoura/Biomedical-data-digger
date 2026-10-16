# ADR-004 — Arquitetura em camadas, composição explícita e UI declarativa

**Status:** Aceito · 2026-10

## Contexto

O código evoluiu por acréscimo: `biomedical_data_digger.py` misturava layout Gradio, regras de
negócio (cache, resolução, prompts, chamada ao LLM) e estado global. Havia duplicação entre as
páginas Geral/Medicina (tema, histórico, handlers), três cópias do fluxo "cache ou resolver",
botões que reutilizavam prompts de outros botões, falhas codificadas como texto no campo
`título` e módulos com efeitos colaterais no import (conexão ao banco, cliente do Groq).

## Decisão

1. **Camadas com dependência unidirecional**
   `ui` → `workflow` → (`domain`, `article_services`, `llm_service`, `cache`, `ratelimit`).
   `workflow.py` não importa Gradio: é testável com dublês injetados (`Resolver`, `TextGenerator`).
2. **Composição na borda.** Só `biomedical_data_digger.create_app()` instancia dependências
   concretas (repositório, roteador de LLM, limitador). Nada de singletons criados no import.
3. **Estratégia para LLMs.** `LLMBackend` (Protocol) + `LLMRouter`; adicionar um provedor é
   escrever uma classe, sem tocar nos chamadores.
4. **Modelo de domínio.** `Article` imutável (abstract obrigatório) e erros tipados cujo
   `user_message` é seguro para exibição. A UI apenas converte `DiggerError` em `gr.Error`.
5. **UI declarativa.** Cada aba é um `PageSpec` (dados); uma única fábrica monta os componentes.
   O smoke test garante que toda a interface constrói, e invariantes impedem builders duplicados
   ou mortos.
6. **Evolução incremental de `article_services`.** O núcleo de resolução (heurísticas extensas e
   bem testadas) foi mantido; foram corrigidos bugs, timeouts e o acesso à rede de páginas
   arbitrárias passou por `security.safe_get`.

## Consequências

- (+) Casos de uso testáveis sem rede nem Gradio; cobertura ≥ 80% imposta no CI.
- (+) Novas análises/abas exigem editar dados, não copiar código.
- (−) `article_services.py` ainda é grande e retorna tuplas `(título, abstract)` internamente; o
  `ArticleRepository` converte para `Article` e classifica falhas. Próximo passo natural: extrair
  `ArticleSource` (Protocol) por provedor e substituir os títulos-sentinela por exceções.
- (−) A autenticação ainda não restringe funcionalidades; está documentada como limitação.
