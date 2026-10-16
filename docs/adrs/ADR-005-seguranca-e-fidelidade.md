# ADR-005 — Modelo de ameaças e garantias de fidelidade

**Status:** Aceito · 2026-10

## Ameaças consideradas

| Ameaça | Vetor | Mitigação | Limite conhecido |
|---|---|---|---|
| SSRF | URL colada pelo usuário buscada pelo servidor | `safe_get`: só http/https, rejeita hosts que resolvem para IP não público (inclui IPv4-mapeado e metadata `169.254.169.254`), revalida cada redirect, limita redirects e bytes | DNS rebinding: validação e conexão são etapas separadas |
| Abuso de custo | Visitantes anônimos consomem a chave Groq | Limitador por cliente (`RATE_LIMIT_PER_MINUTE`) | Em memória, por processo; atrás de múltiplas instâncias o limite é por instância |
| Spoofing de IP | `X-Forwarded-For` forjado | Usa o hop confiável do fim da lista (`TRUSTED_PROXY_HOPS`) | Exige configurar corretamente o nº de proxies |
| Prompt injection | Abstract/página com instruções ou com o marcador de fim | Delimitadores + sistema que trata a fonte como não confiável + neutralização de `<<<`/`>>>` + truncamento + **remoção em código das frases que parecem ordens ao modelo** (aviso ao usuário) + **descarte de respostas curtas demais** | Heurística não cobre todo ataque. Medido: o modelo cru ignora a instrução escondida em apenas ~60 a 80% das tentativas, por isso as defesas em código; ver `evals/` |
| Vazamento por erro do provedor | Mensagem de erro com ID de organização ou detalhes internos | `_provider_error`: 429 amigável, demais erros mostram só o código HTTP; detalhes só no log | Erros sem `status_code` ainda mostram a mensagem original |
| Enumeração/força bruta | Login e cadastro | Rate limit, mensagem genérica, custo PBKDF2 equalizado, limite de tamanho de senha | Sem MFA nem lockout persistente |
| Alucinação numérica | LLM inventa dose/percentual | `grounding.check_numeric_grounding` sinaliza números ausentes da fonte | Não valida unidades/semântica nem números sem unidade/decimal |

## Decisões sobre uso clínico

- Toda resposta da aba Medicina e as comparações clínicas recebem aviso persistente de que o
  conteúdo é apoio à leitura, gerado só de título + resumo.
- Botões do contexto brasileiro desativam a checagem numérica (o contexto curado pode conter
  números que não estão no resumo) e anexam o status de verificação das fontes oficiais.
- Não substitui bula, diretriz institucional nem texto completo. Uso como dispositivo de decisão
  clínica exigiria avaliação regulatória (ANVISA/SaMD), fora do escopo deste projeto.
