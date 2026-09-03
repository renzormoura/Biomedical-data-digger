# Feature: Análises Clínicas Especializadas

## Objetivo
Oferecer 11 tipos de análise estruturada de artigos biomédicos, cada um com prompt especializado para um objetivo clínico diferente.

## Status
✅ Concluído e em produção

## Botões disponíveis na UI

| Botão | Função | Prompt | Público principal |
|---|---|---|---|
| Sumário | Bullet points + parágrafo curto | `build_message_sumario()` | Qualquer |
| Resumo Acadêmico | Análise metodológica para pesquisadores | `build_message_resumo_academico()` | Pesquisadores, pós-graduandos |
| Resumo Clínico | Foco em tomada de decisão clínica | `build_message_resumo_clinico()` | Médicos |
| Resumo | Neutro equilibrado, personalizável via filtros | `build_message_resumo()` | Qualquer |
| Medicamentos / Protocolos | Posologia, farmacocinética, toxicidade | `build_message_medicamentos()` | Médicos, farmacêuticos |
| Alertas e Contraindicações | Segurança, checklist pré-uso | `build_message_alertas()` | PS/UPA |
| Checklist Pré-Conduta | Lista `[ ]` para uso à beira do leito | `build_message_checklist()` | PS/UPA |
| Pergunta PICO | Framework PICO/PICOT | `build_message_pico()` | MBE, residentes |
| Dados Estatísticos | NNT, IC 95%, p-value, sensibilidade | `build_message_estatisticas()` | Pesquisadores, residentes |
| Aplicabilidade Brasileira | SUS, RENAME, contexto BR | `build_message_aplicabilidade_br()` | Médicos brasileiros |
| Crítica Metodológica | Vieses, validade interna/externa | `build_message_critica_metodologica()` | Pesquisadores |

## Regras importantes
- Todos os prompts contêm restrição: "apresente somente informações explicitamente descritas no artigo"
- Prompts de Medicamentos e Alertas contêm **AVISO DE USO CLÍNICO** explícito
- Formato obrigatório nos prompts clínicos: bullet points, sem tabelas (otimizado para mobile/celular)
- Esses prompts são usados em contexto real de pronto-socorro — NÃO alterar sem validação clínica

## Fluxo
1. Usuário digita PMID/PMCID
2. Clica em um botão
3. `summariser_with_label()` → `summariser()` → busca artigo (cache ou API) → monta prompt → chama LLM → retorna resultado
4. Output exibe label do tipo de análise + filtros ativos + texto

## Filtros de personalização
Sistema opcional que modifica o `SYS_PROMPT` dinamicamente via `build_dynamic_sys_prompt()`.

Categorias:
- **Público-alvo:** Médico / Residente / Estudante / Paciente / Enfermagem
- **Tom:** Formal e Técnico / Direto e Objetivo / Didático
- **Idioma:** Português (BR) / English / Español
- **Nível de detalhe:** Resumido / Completo / Ultra-detalhado
- **Foco temático:** Farmacologia / Estatística / Segurança / Metodologia / Clínico/Prático

Sem seleção: comportamento padrão de cada botão, sem alteração.

## Dependências
- Europe PMC REST API (busca de artigos)
- Groq API (geração de texto)
- Gradio (interface)
