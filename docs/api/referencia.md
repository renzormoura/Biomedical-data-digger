# Referência da API

API JSON interna do produto, consumida pela própria SPA. Todas as rotas ficam sob o mesmo domínio do site. **Não é uma API pública versionada**: o contrato pode mudar com o produto (ver [Estabilidade](#estabilidade)).

## Convenções
- **Formato:** requisições e respostas em JSON (`application/json`), exceto downloads (arquivos).
- **Autenticação:** cookie de sessão `bdd_session` (HttpOnly) obtido em `POST /api/auth/login` ou `/register`. Colunas "Acesso": **pública** (sem conta), **conta** (exige sessão; sem ela responde 401), **token** (Bearer).
- **Erros:** `{"error": "mensagem em português"}` com o status adequado.

| Status | Significado |
|---:|---|
| 400 | Entrada inválida ou erro de domínio |
| 401 | Exige conta (ou token inválido) |
| 403 | Origem não permitida (verificação CSRF) |
| 404 | Não encontrado (ou rota desativada por falta de token) |
| 409 | Limite da conta atingido (ex.: 500 artigos na biblioteca) |
| 422 | Parâmetro fora do formato (validação do FastAPI) |
| 429 | Limite de taxa excedido |
| 500 | Erro interno (mensagem genérica) |
| 503 | Fonte de artigos ou modelo de linguagem indisponível |

- **Cache:** respostas de `/api/` levam `Cache-Control: no-store`.
- **Limites de taxa:** ver [Segurança](../arquitetura/seguranca.md#limites-de-uso-e-cotas).
- **Identificador de artigo (`ref`):** PMID, PMCID, DOI, ID do arXiv ou do OpenAlex; até `MAX_REF` caracteres.

## Saúde e páginas
| Método | Rota | Acesso | Descrição |
|---|---|---|---|
| GET | `/` | pública | Navegador de artigos (SPA) |
| GET | `/ia` | pública | Laboratório de IA |
| GET | `/healthz` | pública | Verificação de saúde para o Render |

## Autenticação
| Método | Rota | Acesso | Corpo / parâmetros | Descrição |
|---|---|---|---|---|
| GET | `/api/auth/me` | pública | — | `{user}` da sessão atual (ou nulo) |
| POST | `/api/auth/register` | pública | `{email, password, acceptTerms}` | Cria a conta e inicia a sessão. Com `REQUIRE_TERMS` ligado (padrão em produção), `acceptTerms: true` é obrigatório e a versão aceita é registrada |
| POST | `/api/auth/login` | pública | `{email, password}` | Inicia a sessão |
| POST | `/api/auth/logout` | pública | — | Encerra a sessão |
| POST | `/api/auth/forgot` | pública | `{email}` | Pede o link de redefinição. A resposta é **sempre a mesma** (a conta exista ou não); 503 se o servidor não tem e-mail configurado |
| POST | `/api/auth/reset` | pública | `{token, password}` | Troca a senha com o token do link (1 hora, uso único). Senha fraca não gasta o link |
| POST | `/api/auth/verify` | pública | `{token}` | Confirma o e-mail com o token do link (48 horas, uso único) |
| POST | `/api/account/resend-verification` | conta | — | Reenvia a confirmação: `{sent: true}`, `{sent: false, reason: "wait"}` (1 por minuto) ou `{alreadyVerified: true}` |

## Textos legais
| Método | Rota | Acesso | Descrição |
|---|---|---|---|
| GET | `/api/legal/{doc}` | pública | `doc` = `termos` ou `privacidade`. Devolve `{title, version, html}` (HTML já escapado, com os dados do controlador preenchidos). Documento desconhecido: 404 |

## Descoberta e artigo
| Método | Rota | Acesso | Parâmetros | Descrição |
|---|---|---|---|---|
| GET | `/api/discover/options` | pública | — | Fontes (com tipos de estudo), idiomas e ordenações |
| GET | `/api/discover/search` | pública | `q`, `yf`, `yt`, `types` (lista separada por vírgula), `oa`, `lang`, `sort` (`relevance`/`recent`/`cited`), `page`, `per_page` (≤20), `source` | Resultados: `works[]`, `total`, `page`, `pages`, `perPage`, `source`, `notes[]`. Com conta, cada obra traz `saved` |
| GET | `/api/discover/panorama` | pública | Mesmos filtros da busca (sem página) | Retrato da amostra: `sample`, `total`, `designs[]`, `timeline[]`, `openAccess`, `sources[]`, `retracted`, `strongest` |
| GET | `/api/discover/work` | pública | `ref`, `source` | Artigo completo: `work`, `sections[]`, `findings[]`, `citations{estilo→texto}`, `reliability` (nota e critérios) |
| GET | `/api/discover/brief` | pública | `ref` | Cartão resumido do artigo e nota (usado pelo Laboratório) |
| GET | `/api/discover/similar` | pública | `ref` | `terms[]` e `works[]` semelhantes |
| GET | `/api/discover/enrichment` | pública | `ref` | Ensaios, citações e dados relacionados |
| GET | `/api/discover/cite` | pública | `ref`, `format` (`ris`, `bibtex`, `endnote`, `csljson`, estilos de texto) | Referência de **um** artigo para gerenciadores |
| GET | `/api/discover/downloads` | pública | `ref` | Menu de documentos e links abertos |
| GET | `/api/discover/download` | pública | `ref`, `kind` (`abstract`/`sheet`/`citation`/`fulltext`), `format` | Arquivo para baixar |
| GET | `/api/discover/brasil` | pública | `ref` | Substâncias que o resumo parece citar + situação (ANVISA/Conitec/Rename) |
| GET | `/api/brasil/conitec` | pública | `q` (3–80) | Decisões da Conitec |
| GET | `/api/brasil/medicamento` | pública | `q` (3–80) | Registro ANVISA + Conitec + Rename |

## Biblioteca, listas e análises salvas (exigem conta)
| Método | Rota | Corpo / parâmetros | Descrição |
|---|---|---|---|
| GET | `/api/library` | — | Artigos salvos com etiquetas |
| POST | `/api/library` | `{ref, source?}` | Salva um artigo |
| DELETE | `/api/library` | `?ref=` | Remove da biblioteca |
| PUT | `/api/library/tags` | `{ref, tags[]}` | Define etiquetas (≤30 enviadas; normalizadas) |
| GET | `/api/library/export` | `?format=&list_id=` | Exporta (bibtex, ris, endnote, csljson, abnt, apa, vancouver, ieee, harvard, mla, csv, json, resumos) |
| GET | `/api/lists` | — | Listas da conta |
| POST | `/api/lists` | `{name}` | Cria lista |
| DELETE | `/api/lists/{list_id}` | — | Apaga lista |
| POST | `/api/lists/{list_id}/items` | `{ref, source?}` | Adiciona artigo |
| DELETE | `/api/lists/{list_id}/items` | `?ref=` | Remove artigo |
| POST | `/api/lists/{list_id}/share` | — | Gera `{token, path}` do link público |
| DELETE | `/api/lists/{list_id}/share` | — | Desfaz o compartilhamento |
| GET | `/api/shared/{token}` | — | **Pública.** `{name, works[]}` da lista compartilhada |
| GET/POST/DELETE | `/api/analyses`, `/api/analyses/{id}` | `{article_id, page, label, markdown}` | Análises do Laboratório salvas |
| GET | `/api/analyses/{id}/download` | `?format=` | Baixa uma análise salva |

## Relatórios de tema (exigem conta)
| Método | Rota | Corpo | Descrição |
|---|---|---|---|
| GET | `/api/reports` | — | Relatórios da conta |
| POST | `/api/reports` | `{list_id, title?, question?}` | Cria a partir de uma lista (congela os estudos) |
| GET | `/api/reports/{id}` | — | Relatório completo: itens, panorama, método automático, substâncias |
| PUT | `/api/reports/{id}` | `{title, question, methodNote, items[{ref, included, note}], substances?}` | Atualiza (cria nova versão) |
| DELETE | `/api/reports/{id}` | — | Apaga |
| GET | `/api/reports/{id}/history` | — | Versões, histórico e artigos novos na lista de origem |
| POST | `/api/reports/{id}/search` | `{query, language?, yearFrom?}` | Procura artigos que ainda não estão no relatório |
| POST | `/api/reports/{id}/add` | `{refs[], origin: lista|busca, query?}` | Acrescenta estudos |
| POST | `/api/reports/{id}/restore` | `{version}` | Restaura uma versão |
| GET | `/api/reports/{id}/brasil` | — | Sugestões de substâncias e situação das confirmadas |
| GET | `/api/reports/{id}/download` | `?format=` | Baixa o relatório (`txt`, `md`, `html`, `docx`; padrão `html`) |

## Interesses, avisos e notificações (exigem conta)
| Método | Rota | Corpo | Descrição |
|---|---|---|---|
| GET | `/api/interests/options` | — | **Pública.** 14 áreas, subtemas e idiomas |
| GET/PUT | `/api/interests` | `{topics[{area, subtopics[]}], languages[], terms[]}` | Lê/grava interesses |
| GET | `/api/alerts` | — | Caixa unificada do sininho (`kind`, `priority`, `title`, `body`, `href`, `read`…) |
| POST | `/api/alerts/check` | `{force?}` | Verifica agora |
| POST | `/api/alerts/read` | `{id?}` | Marca como lido (um ou todos) |
| DELETE | `/api/alerts` | `?id=` | Dispensa um aviso |
| GET/PUT | `/api/notifications/prefs` | `{kinds{tipo→bool}}` | Tipos de aviso ligados/desligados |
| POST | `/api/internal/alerts/run` | — | **Token** `Bearer ALERTS_CRON_TOKEN`. Rotina agendada (ver [Rotinas agendadas](../operacao/rotinas-agendadas.md)) |

## Feed
| Método | Rota | Acesso | Parâmetros | Descrição |
|---|---|---|---|---|
| GET | `/api/feed` | pública | `mode` (`voce`/`tudo`), `kind` (`todos`/`artigos`/`noticias`), `area`, `lang`, `page` | Cartões, `total`, `hasMore`, `personalized`, `hasInterests`, `updatedAt`, `refreshing` |
| GET | `/api/feed/sources` | pública | — | Fontes, tipos, áreas, última atualização e falhas |

## Perfil e conta
| Método | Rota | Acesso | Corpo | Descrição |
|---|---|---|---|---|
| GET | `/api/profile/options` | pública | — | Perfis de uso disponíveis |
| GET/PUT | `/api/profile` | conta | `{profile, healthPack?}` | Perfil de uso e pacote de saúde |
| GET | `/api/account` | conta | — | Resumo: e-mail, desde quando, contadores, `emailVerified` e `emailEnabled` (se o servidor envia e-mails) |
| POST | `/api/account/password` | conta | `{current, new}` | Troca a senha |
| GET | `/api/account/export` | conta | — | `meus-dados.json` com todos os dados |
| DELETE | `/api/account` | conta | `{password}` | Exclui a conta e os dados (irreversível) |

## Laboratório de IA
| Método | Rota | Acesso | Corpo | Descrição |
|---|---|---|---|---|
| POST | `/api/analyze` | pública (com cota) | `{page, button, article_id, model, filters{publico,tom,idioma,detalhe,foco}}` | Análise gerada por IA |
| POST | `/api/audit` | pública (com cota) | `{article_id, model, previous, page?}` | Auditoria de uma resposta anterior |
| POST | `/api/compare` | pública (com cota) | `{article_a, article_b, analysis, model, clinical?, page?}` | Comparação de dois artigos |
| POST | `/api/extract` | pública | `{page, button, article_id}` | Extração **sem IA** |
| POST | `/api/cite` | pública | `{article_id, style}` | Referência ABNT/APA/Vancouver sem IA |
| POST | `/api/search` | pública | `{query, area, limit}` | Busca simples herdada do Laboratório |
| POST | `/api/export/analysis` | pública | `{title, label, markdown, format}` | Converte uma análise em txt/md/html/docx |

## Planos e pagamento (Pix)
| Método | Rota | Acesso | Corpo | Descrição |
|---|---|---|---|---|
| GET | `/api/billing/plans` | pública | — | Planos com preço e limites, períodos (1, 3, 12), `enforced` e `pixAvailable` |
| GET | `/api/billing/me` | conta | — | Plano, validade, limites, uso e pedidos (com o Pix dos pendentes) |
| POST | `/api/billing/requests` | conta | `{plan, months}` | Cria (ou reaproveita) o pedido e devolve o Pix "copia e cola". 503 sem `PIX_KEY`; 409 com 3 pedidos pendentes |
| DELETE | `/api/billing/requests/{id}` | conta | — | Cancela um pedido pendente próprio |

## Administração
Todas com `Authorization: Bearer ADMIN_TOKEN` (comparação em tempo constante, limite por identidade); sem `ADMIN_TOKEN` configurado respondem 404; com token errado, 401.

| Método | Rota | Corpo | Descrição |
|---|---|---|---|
| GET | `/api/admin/usage` | — | Consumo agregado de tokens (sem conteúdo) |
| GET | `/api/admin/billing/requests` | — | Pedidos de pagamento pendentes (com e-mail) |
| POST | `/api/admin/billing/requests/{id}/confirm` | `{note?}` | Confirma o pagamento, ativa ou prorroga a assinatura e avisa por e-mail |
| POST | `/api/admin/billing/requests/{id}/cancel` | — | Cancela um pedido pendente |
| GET | `/api/admin/accounts?q=` | — | Contas (até 50) com plano e validade; `q` filtra por e-mail |
| POST | `/api/admin/billing/grant` | `{email, plan, days}` | Cortesia: concede o plano por `days` dias |
| POST | `/api/admin/billing/revoke` | `{email}` | Remove a assinatura da conta |

## Estabilidade
A API existe para a SPA. Não há versionamento de rotas nem garantia de compatibilidade para terceiros. Se o produto abrir uma API pública comercial, ela deverá ser projetada à parte (autenticação por chave, versionamento e limites por plano), usando esta como base. As rotas `GET /api/discover/*` e `GET /api/feed*` são candidatas naturais.
