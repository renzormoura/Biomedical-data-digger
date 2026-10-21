# Funcionalidade: Laboratório de IA (opcional)

## Objetivo
Oferecer análises de um artigo geradas por **modelo de linguagem** (LLM), em 16 áreas de atuação, para quem quer uma leitura guiada além dos dados extraídos por código. É uma camada **opcional e separada**: nada do restante do produto (busca, nota, relatório, citações, alertas) depende dela, e tudo o que ela produz é rotulado como gerado por IA.

Acesso: `/ia` (menu "Laboratório de IA").

## O que a pessoa vê
- Seletor de **área de análise** e, em cada área, **botões** de análise específicos, mais "Direto do artigo (sem IA)" (extração por código).
- Campo para o artigo (PMID, PMCID, DOI, arXiv, OpenAlex ou URL), escolha do **modelo** e **filtros** opcionais: público, tom, idioma, nível de detalhe e foco.
- O resultado em Markdown, com o rótulo da análise, os filtros usados, avisos de segurança, o aviso de uso clínico (nas áreas clínicas) e a verificação de números.
- **Comparar dois artigos** (10 tipos de comparação), **Auditar resposta** (revisão crítica de uma resposta anterior), **Citar** (sem IA) e **Baixar** a análise em TXT, Markdown, HTML ou DOCX.
- Contas podem **salvar** análises na biblioteca (até 200).
- Cota diária restante é mostrada; "Entrar com uma conta aumenta o limite".

### As 16 áreas
| Grupo | Áreas |
|---|---|
| Geral | Geral · Acadêmico |
| Saúde | Medicina · Saúde Pública · Enfermagem · Farmácia · Nutrição · Psicologia · Para o Paciente |
| Exatas e Tecnologia | Tecnologia e IA · Engenharias · Biotecnologia |
| Sociedade e Ambiente | Ambiental · Direito e Políticas · Educação · Agro e Veterinária |

Cada área é uma especificação declarativa (`pages.py`: botões, rótulos, público e foco sugeridos, texto de ajuda). Os botões de análise ligam a um construtor de prompt (`prompt_builders.py`, `prompt_specs.py`). Exemplos: Sumário, Resumo acadêmico, Resumo clínico, Pergunta PICO, Dados estatísticos, Crítica metodológica, Medicamentos/Protocolos, Alertas e contraindicações, Checklist pré-conduta, Aplicabilidade brasileira.

## Como funciona
1. **Resolução do artigo** pelo mesmo caminho da busca (cache de artigos de 1 hora).
2. **Defesa contra injeção de prompt** (`injection.py`): antes de chamar o modelo, remove do texto-fonte frases com formato de ordem ao modelo ("ignore as instruções anteriores…") e avisa a pessoa. O texto-fonte entra no prompt dentro de marcadores (`wrap_source`), nunca como instrução.
3. **Bloqueio sem IA** (`requires`): botões de alto risco (dose, conduta, interação, reação adversa) exigem que o resumo traga indícios do tema (`has_cues`); sem eles, a análise é bloqueada **sem chamar o modelo** (zero token), em vez de deixar a IA preencher a lacuna. Nas áreas clínicas, os botões geradores de dose/conduta ficam desligados, a menos que `ENABLE_GENERATIVE_CLINICAL` esteja ligado.
4. **Prompt** montado com o sistema dinâmico (`build_dynamic_sys_prompt`) conforme os filtros. Todos os prompts exigem "apresente somente informações explicitamente descritas no artigo".
5. **Geração** (`llm_service.py`): `LLMRouter` escolhe o backend pelo nome do modelo. **Groq** em produção (GPT-OSS 20B e 120B, Qwen 3.6 e 3.8 27B) e **Ollama** local (Llama) em desenvolvimento. Temperatura padrão 0,2 (`LLM_TEMPERATURE`), esforço de raciocínio reduzido em botões de baixo risco e teto de saída por nível de detalhe (1.500, 3.000 e 4.500 tokens).
6. **Verificação de números** (`grounding.py`): confere, sem outro LLM, se os valores numéricos da resposta (percentuais, doses, p-values) aparecem no título/resumo fornecidos; o que não aparece é sinalizado.
7. **Avisos:** aviso de uso clínico nas áreas de saúde; aviso de truncamento quando o modelo estoura o teto; avisos de segurança do artigo.
8. **Cache e deduplicação** (`workflow.py`): resultados idênticos (mesmo artigo, botão, filtros, modelo e política) vêm do cache e **não gastam tokens nem cota**; pedidos idênticos simultâneos são unificados (*single flight*); respostas truncadas não vão para o cache.
9. **Cotas e limites:** limite de chamadas ao modelo por minuto por identidade (`RATE_LIMIT_PER_MINUTE`, padrão 8) e **cota diária de tokens** (padrão 60.000 para visitantes e 200.000 para contas; `DAILY_TOKEN_BUDGET_GUEST`/`_USER`); renova às 00:00 UTC. A cota é em memória, por instância.
10. **Consumo registrado** (`usage.py`): só contagens (tokens, modelo, botão, tipo de cliente), nunca conteúdo de artigos, respostas nem identificação de pessoas. Resumo agregado em `GET /api/admin/usage` (exige `ADMIN_TOKEN`).

### Sem IA dentro do Laboratório
- **Extrair do artigo** (`POST /api/extract`): copia trechos do resumo (visão geral, números, dose, conduta…) com `extraction.py`; nada é gerado.
- **Citar** (`POST /api/cite`): referências ABNT, APA, Vancouver a partir dos metadados.

## Limites e cuidados
- Modelos de linguagem podem errar; a verificação de números reduz um tipo de erro, não todos. O produto recomenda leitura crítica do artigo antes de qualquer decisão.
- A injeção de prompt é tratada por heurística; a avaliação com o modelo real mostrou que só o prompt falha em ≈20% das tentativas, por isso a defesa em código. Não cobre todo ataque (ver [Segurança](../arquitetura/seguranca.md)).
- Prompts de áreas clínicas foram usados em contexto de pronto-socorro: **não alterar sem validação clínica**. A revisão de 2026-10 (abaixo) só **restringiu** o que o modelo pode afirmar, mas ainda **não foi validada com o modelo real nem por profissional de saúde**: rode `RUN_LIVE_EVALS=1 GROQ_API_KEY=... pytest evals -m live` antes de colocar em produção.

## Princípios dos prompts (revisão de 2026-10)
- **Um prompt de sistema só diz o que vale para todas as análises:** marcadores do texto não confiável (`<<<SOURCE_TITLE_START>>>` etc., o mesmo formato de `wrap_source`), idioma (português, salvo outro escolhido na personalização), restrição à fonte, frase única para dado ausente, números copiados sem cálculo, segurança e formato-padrão. Foi removida a sobra do exercício original que obrigava "resumo em bullets + parágrafo" em **todas** as análises, inclusive na crítica metodológica e no glossário.
- **Ausência de dado:** a frase é sempre "Não descrito no resumo fornecido", e o modelo é instruído a **omitir campos vazios** em vez de repeti-la dezenas de vezes (economia de saída). Variantes como "Não descrito no artigo" foram eliminadas dos prompts escritos à mão; "Não avaliável pelo resumo fornecido" e "Não explicado no resumo fornecido" continuam, por terem sentido próprio.
- **Personalização só muda estilo:** público, tom, detalhe e foco nunca autorizam acrescentar fatos, definições ou números. A opção "English" prevalece sobre o idioma padrão, o que antes entrava em conflito com o prompt de sistema.
- **Auditoria com prompt próprio** (`AUDIT_SYS_PROMPT`: revisor de fatos, não extrator), e a **resposta auditada passou a ser tratada como texto não confiável** (`<<<RESPONSE_UNDER_AUDIT_START>>>`), pois pode ter nascido de um resumo malicioso. O limite do trecho auditado subiu de 12.000 para 30.000 caracteres (igual ao da rota), porque antes uma análise longa era cortada em silêncio. Número só é "suportado" se coincidir exatamente.
- **Pedidos que o resumo não sustenta foram retirados:** estatística (risco de erro tipo II, interpretação própria, "decisão clínica"), PICO ("pacientes que você atende"; nível de evidência só se informado), aplicabilidade ao Brasil (grau de confiança recomendado; comparações com a população brasileira só com fonte), resumo para leigos ("por que isso importa para mim"; sem conselhos de saúde), populações especiais (omite as não mencionadas) e medicamentos (copiar doses sem converter).
- **Contagens exatas viraram tetos:** "exatamente 5 perguntas/questões" e "8 a 12 flashcards" agora são "até N", para o modelo não inventar conteúdo quando o resumo é curto.
- **Disponibilidade no SUS** recebe o veredito das bases oficiais como contexto (ver [Disponibilidade no SUS](disponibilidade-sus.md)).
- Testes: `tests/test_prompt_quality.py` (offline) trava essas regras; `evals/test_fidelity_live.py` ganhou o caso de injeção na resposta auditada.
- Cota e limitadores são por processo: com mais de uma instância, cada uma conta separado.

## API
`POST /api/analyze`, `/api/audit`, `/api/compare`, `/api/extract`, `/api/cite`, `/api/export/analysis`, `GET/POST/DELETE /api/analyses…`. Ver [Referência da API](../api/referencia.md).

## Arquivos
`pages.py`, `prompt_builders.py`, `prompt_specs.py`, `workflow.py`, `llm_service.py`, `generation.py`, `injection.py`, `grounding.py`, `quota.py`, `usage.py`, `extraction_view.py`, `templates/ia.html`, `static/app.js`, `static/app.css`. Testes: `tests/test_workflow.py`, `tests/test_prompt_contract.py`, `tests/test_injection_guards.py`, `tests/test_grounding.py`, `tests/test_llm_router.py`, `tests/test_quota.py`, `tests/test_lab_analyses.py`, `evals/test_fidelity_live.py` (avaliação com o modelo real, fora da suíte padrão).
