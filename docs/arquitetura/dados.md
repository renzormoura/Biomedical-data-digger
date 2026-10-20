# Modelo de dados

## Visão geral
- **Banco único** para todo o produto. Produção: **PostgreSQL** (`DATABASE_URL`). Desenvolvimento: **SQLite** (`DATABASE_PATH`, padrão `accounts.sqlite3`, ignorado pelo Git).
- Mesmo SQL nos dois: `db.py` troca `?` por `%s` em PostgreSQL. Tipos simples (`TEXT`, `INTEGER`); datas em ISO 8601 UTC como texto; estruturas em JSON como texto.
- **Sem migrações versionadas.** Cada armazém cria suas tabelas com `CREATE TABLE IF NOT EXISTS` em `initialize()`, na subida. Alterações precisam ser **aditivas**; mudanças destrutivas exigiriam um mecanismo de migração (pendência).
- **Chave de dono:** todas as tabelas pessoais usam o **e-mail** (minúsculo) como identificador da conta. Toda consulta filtra pelo dono.
- Em produção sem `DATABASE_URL` o serviço **não inicia**, para não gravar contas no disco efêmero.
- **Validação em PostgreSQL:** em 20/10/2026 a suíte inteira (1.469 testes) passou contra PostgreSQL 16 real, com um schema por teste (ver [Testes](../desenvolvimento/testes.md#rodar-a-suíte-contra-postgresql)). Falta validar no banco **de produção** (Neon/Render) e fazer um teste de carga/restauração.
- **Diferenças já tratadas:** `users.created_at` é `TIMESTAMPTZ` no PostgreSQL e texto no SQLite; `AccountStore.created_at` normaliza ambos para UTC `AAAA-MM-DDTHH:MM:SS`. Consultas sem `ORDER BY` não têm ordem garantida no PostgreSQL: sempre ordene.

## Dicionário de tabelas

### Contas e perfil (`account_store.py`, `profiles.py`)
| Tabela | Colunas | Uso |
|---|---|---|
| `users` | `email` (PK), `password_hash`, `password_salt`, `created_at` | Contas. Hash PBKDF2-SHA256 de 600.000 iterações |
| `user_profiles` | `user_email` (PK), `profile`, `health_pack`, `updated_at` | Perfil de uso e liga/desliga do pacote Saúde no Brasil |

| `account_tokens` | `token_hash` (PK), `email`, `purpose` (`reset`/`verify`), `expires_at`, `created_at` | Tokens de uso único dos links de e-mail; **só o hash SHA-256** é guardado |
| `email_verification` | `email` (PK), `verified_at` | E-mail confirmado (por link ou ao redefinir a senha) |
| `terms_acceptance` | `email` (PK), `version`, `accepted_at` | Versão dos Termos e da Política aceita no cadastro, e quando |

### Planos e pagamentos (`billing.py`)
| Tabela | Colunas | Uso |
|---|---|---|
| `subscriptions` | `email` (PK), `plan`, `expires_at`, `updated_at` | Plano pago em vigor e validade (vencida = plano gratuito) |
| `payment_requests` | `id` (PK), `email`, `plan`, `months`, `amount_cents`, `reference` (único), `status` (`pendente`/`confirmado`/`cancelado`), `created_at`, `confirmed_at`, `note` | Pedidos de pagamento por Pix; os **confirmados** são registro fiscal e sobrevivem à exclusão da conta |

### Administração (`account_flags.py`)
| Tabela | Colunas | Uso |
|---|---|---|
| `suspended_accounts` | `email` (PK), `reason`, `suspended_at` | Contas suspensas pelo administrador |

### Biblioteca (`library_store.py`)
| Tabela | Colunas | Uso |
|---|---|---|
| `library_items` | `user_email`, `ref`, `data`, `tags`, `saved_at` (PK `user_email+ref`) | Artigo salvo: retrato JSON dos metadados e etiquetas |
| `reading_lists` | `id` (PK), `owner_email`, `name`, `share_token` (único), `created_at` | Listas de leitura; `share_token` nulo = não compartilhada |
| `reading_list_items` | `list_id` (FK → `reading_lists`, `ON DELETE CASCADE`), `ref`, `data`, `position` | Artigos da lista, com ordem |
| `saved_analyses` | `id` (PK), `user_email`, `ref`, `title`, `page`, `label`, `markdown`, `created_at` | Análises do Laboratório de IA salvas |

### Relatórios (`reports.py`)
| Tabela | Colunas | Uso |
|---|---|---|
| `reports` | `id`, `owner_email`, `title`, `question`, `method_note`, `list_name`, `created_at`, `updated_at`, `version` | Relatório de tema |
| `report_items` | `report_id` (FK, cascata), `ref`, `data`, `position`, `included`, `note` | Estudos do relatório, com inclusão/exclusão e nota do autor |
| `report_substances` | `report_id` (FK), `term`, `position` | Substâncias confirmadas pelo autor (Saúde no Brasil) |
| `report_versions` | `report_id` (FK), `version`, `saved_at`, `summary`, `state` | Versões restauráveis (até 50) |
| `report_sources` | `report_id` (PK, FK), `list_id` | Lista de origem, para detectar novidades |
| `report_log` | `id`, `report_id` (FK), `kind`, `text`, `created_at` | Histórico de mudanças (até 200) |

### Interesses e alertas (`alerts.py`)
| Tabela | Colunas | Uso |
|---|---|---|
| `interest_prefs` | `user_email` (PK), `data`, `updated_at`, `last_checked` | Áreas, subtemas, idiomas e palavras-chave |
| `interest_baselines` | `user_email`, `search_key` | Buscas cuja primeira verificação já serviu de linha de base (não avisa o que já existia) |
| `alert_seen` | `user_email`, `work_key`, `seen_at` | Artigos já vistos (até 5.000 por conta) |
| `alerts` | `id`, `user_email`, `work_key`, `ref`, `data`, `topic`, `created_at`, `read_at` (único `user_email+work_key`) | Avisos de artigo novo |

### Notificações (`notifications.py`)
| Tabela | Colunas | Uso |
|---|---|---|
| `notifications` | `id`, `user_email`, `kind`, `priority`, `dedupe_key`, `group_key`, `title`, `body`, `link`, `data`, `created_at`, `read_at` (único `user_email+dedupe_key`) | Avisos de retratação, regulatório e novidades dos relatórios |
| `retraction_status` | `ref` (PK), `retracted`, `checked_at` | Estado global de retratação por artigo (reconferido a cada semana) |
| `regulatory_state` | `user_email`, `term`, `fingerprint`, `checked_at` | Resumo do estado regulatório de cada substância acompanhada |
| `watch_state` | `user_email` (PK), `last_run` | Última execução do vigia por conta |
| `notification_prefs` | `user_email` (PK), `data` | Tipos de aviso ligados/desligados |

### Feed (`feed.py`)
| Tabela | Colunas | Uso |
|---|---|---|
| `feed_items` | `id` (PK), `source_id`, `url`, `title`, `snippet`, `published_at`, `date_known`, `topics`, `areas`, `fetched_at` | Itens das fontes; guarda **título, trecho curto (≤300 caracteres) e link**. Retenção de 45 dias |
| `feed_state` | `source_id` (PK), `last_fetch`, `last_ok`, `etag`, `last_modified`, `error`, `items` | Estado de cada fonte para atualização condicional |

O feed é **global** (não pertence a conta); a personalização é feita na leitura.

## Retenção e limpeza
| Dado | Retenção |
|---|---|
| `feed_items` | 45 dias (limpeza a cada atualização) |
| `alert_seen` | até 5.000 por conta (os mais antigos saem) |
| `alerts` e `notifications` | até 200 por conta |
| `report_versions` / `report_log` | até 50 / 200 por relatório |
| Demais dados pessoais | até a pessoa excluí-los ou excluir a conta |

## Exclusão e exportação
- `DELETE /api/account` chama `delete_user_data(user)` em cada armazém (biblioteca e listas, relatórios, alertas e interesses, notificações, perfil, tokens, confirmação de e-mail, aceite dos termos, assinatura e pedidos não confirmados; os pagamentos confirmados ficam por obrigação fiscal) e depois remove a conta. `retraction_status` e o feed são globais e não têm dados pessoais.
- `GET /api/account/export` reúne tudo o que pertence à conta em um único JSON (sem o hash de senha).

## Fora do banco
- **Instantâneos do Brasil:** `dados_brasil/*.json` (versionados no repositório).
- **Caches em memória:** buscas, obras, enriquecimento, resultados de IA, existência de conta, candidatos do feed.
- **Sessões:** cookie assinado; nada no servidor.
