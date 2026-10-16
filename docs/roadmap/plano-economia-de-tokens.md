# Plano: economizar tokens e usar IA só quando necessária

**Status:** Fases 0 e 1 **implementadas** · Fase 2 **parcialmente implementada** (ver abaixo) · Fases 3 a 5 pendentes · 2026-10 · **Decisão vigente:** o produto lê **apenas título + resumo** (sem texto completo).

### Medição real (Fase 0), um artigo, GPT-OSS 20B no Groq

| Botão | Tokens totais (entrada + saída) |
|---|---|
| Pontos-Chave | 1.395 |
| Sumário | 1.926 |
| Resumo Introdutório | 2.360 |
| Resumo | 2.556 |

Em 4 chamadas, a **saída foi ~48% dos tokens** (3.924 de 8.237), mais do que a estimativa inicial. Hipótese a testar na Fase 2: os modelos GPT-OSS são de raciocínio, e os tokens de raciocínio contam como saída; reduzir o esforço de raciocínio (se o provedor permitir) pode cortar bastante custo. A repetição da mesma análise levou 315 ms e custou 0 token (cache).

## 1. Objetivo e metas

Reduzir o custo de LLM por uso, sem perder fidelidade ao texto-fonte, deixando a IA apenas onde ela agrega.

| Indicador | Hoje (estimado) | Meta |
|---|---|---|
| Entrada por chamada (mediana) | ~1.350 tokens | ~600 a 700 |
| Saída por chamada | ~500 a 1.500 | ~300 a 700 |
| Análise típica (entrada + saída) | ~2.000 a 3.500 | ~800 a 1.500 |
| Repetição do mesmo artigo + botão | custo total | **0** (cache) |
| Botões que não chamam LLM | 3 (citações) | a definir na Fase 3 |

> **Os números "hoje" são estimativas** (caracteres ÷ 3,6 sobre os prompts reais, com um abstract de 156 palavras). A Fase 0 os substitui por medições. Composição medida: ~320 tokens de abstract, ~780 de prompt de sistema, ~250 a 1.100 de instruções do botão. **Cerca de 80% da entrada é overhead fixo**, não o artigo.

## 2. Princípios

1. **Medir antes de otimizar.** Nenhuma otimização entra sem número antes e depois.
2. **Código antes de IA.** Se um programa extrai ou verifica, a IA não é chamada.
3. **Fidelidade não é negociável.** Cortar tokens nunca pode enfraquecer as regras "somente a fonte". Toda mudança de prompt passa por testes de contrato e pela avaliação com modelo real (`evals/`).
4. **Na dúvida, mandar mais contexto.** Um filtro que esconde informação é pior do que gastar token.
5. **O usuário sabe o que foi lido.** Faixa permanente: "Baseado apenas no título e no resumo".

## 3. Fases

### Fase 0 — Medir ✅ concluída (pequena, baixo risco)
- Registrar `usage` (tokens de entrada e saída) devolvido pelo Groq em **cada chamada**, com modelo, aba, botão, `cached` e latência (log estruturado; sem conteúdo do artigo).
- Relatório simples por botão e por aba (média, p95, total/dia).
- **Aceite:** toda chamada gera um registro; baseline de uma semana de uso real ou de um conjunto de casos de teste.

### Fase 1 — Não gastar ✅ concluída (alto retorno, baixo risco)
- **Cache de resultados:** chave = artigo canônico + botão + filtros + modelo; LRU + validade de algumas horas. Artigos são públicos (sem problema de privacidade).
- **Deduplicar requisições simultâneas** iguais (uma só chamada serve várias).
- **Cotas por conta:** tokens por dia (visitante menor que logado), além do limite por minuto já existente.
- **Aceite:** repetição = 0 token; testes de cache (acerto, expiração, chave distinta por filtro/modelo).
- **Implementado:** `UsageLog` + `GET /api/admin/usage` (requer `ADMIN_TOKEN`); cache de resultados (6 h, até 512 entradas, chave canônica do artigo + botão + rótulo + filtros + modelo + flags); `SingleFlight` para análises idênticas simultâneas; `QuotaManager` por dia UTC (visitante 60.000 e conta 200.000 tokens por padrão; 0 = sem limite); a interface mostra "em cache", tokens da chamada e cota restante. Acertos de cache não consomem limite por minuto nem cota, e funcionam mesmo com o provedor fora do ar. Auditoria não usa cache.
- **Limites conhecidos:** cache e cotas ficam em memória (reiniciam com o processo e valem por instância); o cache é compartilhado entre usuários (artigos são públicos).

### Resultado da Fase 2 (medido com o Groq real, GPT-OSS 20B)

| Medida | Resultado |
|---|---|
| Raciocínio `low` | Saída ~1.223 → ~564 tokens (−54%), total −27%, texto visível do mesmo tamanho. **Adotado só em 13 botões de baixo risco e nunca nas abas clínicas**, porque nas leituras o modo `low` fez algumas inferências a mais (ex.: inventou "avaliados via registros clínicos") e a amostra era pequena demais para provar equivalência. |
| Temperatura 0,2 e teto de saída por nível de detalhe | Aplicados. O teto é proteção (em modelo de raciocínio, o raciocínio conta como saída); resposta cortada ganha aviso e não é cacheada. |
| Enxugar o prompt de sistema | **Ganho desprezível e sem benefício comprovado.** A versão mais curta (~574 tokens estimados contra ~782) falhou mais no teste de injeção em 5 execuções, mas o prompt original também falha 3 em 10; a amostra não distingue as versões. Mantida a estrutura original com as regras condensadas e duas regras novas (proibir percentuais derivados; proibir variantes de "Não descrito"): ~739 tokens, economia ~5%. |
| Limpar boilerplate do abstract | Implementado (copyright/licença no fim do texto). Ganho pequeno. |

**Achados importantes desta fase**

1. **Injeção de prompt:** só o prompt não basta. O modelo cru cede à instrução escondida em ~20 a 40% das tentativas (prompt original: 14 de 17 resistências). Adicionadas defesas em código (`injection.py`: remove frases que parecem ordens ao modelo e avisa o usuário; descarte de respostas com menos de 120 caracteres). Nos evals, a proteção ponta a ponta barrou 100% das tentativas.
2. **O modelo calcula valores que o prompt proíbe** (ex.: "18%" a partir de HR 0,82). A verificação automática de números os sinaliza ao usuário; as regras novas no prompt reduziram os casos de 13 para 6 nas amostras.
3. **Limite do provedor:** o Groq impõe **200.000 tokens/dia por modelo** no plano gratuito (`on_demand`). Isso é ~100 análises por dia no total, para todos os usuários. As cotas por conta (60.000/200.000) devem ser calibradas por esse teto, e **testes ao vivo consomem a mesma cota da produção**.
4. **Mensagens de erro:** o erro 429 cru do provedor incluía o ID da organização. Agora vira mensagem amigável sem detalhes internos (`_provider_error`).

### Fase 2 — Gastar menos por chamada (parcial)
- **Enxugar o prompt de sistema** (~780) e as instruções dos botões: remover regras repetidas (a restrição "somente a fonte" aparece no sistema **e** em cada botão), preferir instruções em inglês com resposta em português.
- **`max_tokens` por botão** e limites de formato nas instruções ("no máximo N tópicos").
- **Temperatura baixa (0 a 0,2)**: hoje não é definida (ganho de fidelidade, não de custo).
- **Padrão de detalhe "Resumido"** (decisão de produto a confirmar).
- **Combinar botões** que compartilham saída (ex.: Sumário + Pontos-Chave) em uma chamada.
- **Limpar o abstract** (copyright, rótulos duplicados).
- **Manter a parte fixa no início do prompt** (já é assim) e verificar na documentação do provedor se há cache de prefixo.
- **Aceite:** entrada mediana ≤ ~700 tokens; avaliação de fidelidade igual ou melhor que o baseline; contratos de prompt passando.

### Fase 3 — IA só quando necessária
Camada **sem IA** (zero token) e bloqueios que evitam chamar o modelo:
- Abstract **dividido em seções** quando houver rótulos (se não houver, mostrar inteiro; os rótulos são irregulares).
- **Tipo de estudo** do registro oficial (Europe PMC), como rótulo, nunca como opinião.
- **Números com a frase de origem** (N, p-valor, IC 95%, HR/OR/RR) por regex.
- **Metadados:** palavras-chave, financiamento, acesso aberto, citações.
- **Bloquear sem chamar o modelo** quando o abstract não traz o dado (ex.: posologia no botão de medicamentos).
- **Dose, conduta e interações** (alto risco): somente **trechos citados** do abstract, ou removidos do modo generativo.
- **Aceite:** painel "Extraído do artigo (sem IA)" em todas as abas; testes com abstracts reais estruturados e não estruturados.

### Fase 4 — Extrair uma vez, reaproveitar (só se a Fase 0 mostrar que vale)
- Uma chamada gera uma **extração compacta** (objetivo, desenho, N, resultados, conclusão, limitações), cada item com **citação literal verificada em código**.
- Botões derivados (flashcards, glossário, questões, roteiro) usam a extração, não o abstract com prompt longo.
- **Risco:** erro na extração se propaga; mitigado pela citação verificada.
- **Aceite:** custo do 2º botão no mesmo artigo ≤ ~40% do atual; fidelidade mantida.

### Fase 5 — Texto completo (opcional, futura)
Hoje fora do escopo. Deixar a base pronta sem mudar o comportamento:
- Modelo `Document` (seções) e interface `SectionSelector` (com abstract, devolve o abstract inteiro).
- Mapa botão → seções, com orçamento de tokens (ex.: 3.000), sempre incluindo Resultados e Conclusão, e nova tentativa com mais seções se houver muitos "Não descrito".
- Faixa de cobertura sempre visível; **nunca** voltar ao resumo em silêncio.
- Dependências a resolver antes: acesso legal (acesso aberto, upload do usuário, licença institucional), direitos autorais e LGPD.
- **Custo esperado:** ~2 a 5 vezes o atual (não 10 a 20), porque só as seções necessárias são enviadas.

## 4. Camadas por tipo de botão (proposta)

| Camada | Botões | Chamada de LLM |
|---|---|---|
| Sem IA | Referências ABNT/APA/Vancouver; abstract estruturado; tipo de estudo; números com frase de origem; metadados | Nenhuma |
| IA curta (prompt enxuto, saída limitada) | Sumário, Pontos-Chave, Glossário, Flashcards, Questões, Roteiro, Fichamento | 1 |
| IA com extração reaproveitada | Botões derivados, quando a Fase 4 existir | 1 curta |
| Extrativo / bloqueado | Medicamentos, Conduta em Urgência, Interações, Alertas (dose e conduta) | 0 ou trecho citado |
| Opt-in | Auditoria da resposta, segunda opinião | 1 extra, só sob pedido |

## 5. Qualidade e segurança (transversal)

- **Avaliação de fidelidade** (`evals/`) rodada antes e depois de cada mudança de prompt, com casos validados por professores das áreas.
- Contratos de prompt e testes continuam obrigatórios no CI.
- A checagem de números e a verificação de citações são código: **não custam token**.
- Todas as respostas mantêm a faixa "só o resumo" e, nas abas de saúde, o aviso clínico.

## 6. Ordem sugerida

| Ordem | Fase | Esforço | Dependência |
|---|---|---|---|
| 1 | 0 — Medir | Pequeno | Nenhuma |
| 2 | 1 — Cache, deduplicação, cotas | Pequeno | Fase 0 (para validar) |
| 3 | 2 — Prompts enxutos, teto de saída, temperatura | Médio | Avaliação de fidelidade de base |
| 4 | 3 — Camada sem IA e bloqueios | Médio | Decisão sobre os botões clínicos |
| 5 | 4 — Extração reaproveitada | Alto | Dados da Fase 0 |
| 6 | 5 — Texto completo | Alto | Decisão jurídica e de produto |

## 7. Decisões pendentes

1. **Detalhe padrão "Resumido"?** Reduz saída, mas o aluno pode querer mais.
2. **Dose e conduta:** extrativo (trechos citados) ou remover do app na primeira versão?
3. **Cota diária por conta:** valores para visitante e logado.
4. **Aba Medicina na primeira versão** ou só depois das Fases 3 e 4 validadas por professor?
5. **Texto completo:** a faculdade tem licença institucional ou aceita upload de PDF pelo aluno?

## 8. Riscos

| Risco | Mitigação |
|---|---|
| Prompt enxuto reduz fidelidade | Avaliação antes/depois; reverter se piorar |
| Cache serve resposta desatualizada | Validade curta; chave inclui filtros e modelo |
| Filtro/extração esconde informação | Na dúvida, contexto completo; faixa "partes usadas" |
| Erro de extração se propaga (Fase 4) | Citação literal verificada em código |
| Estimativas de token erradas | Fase 0 mede antes de decidir as demais |
