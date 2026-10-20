# Roadmap

Estado em **19/10/2026**. O que já existe está descrito em [Funcionalidades](../README.md#funcionalidades); o histórico detalhado, no [Changelog](../changelog/CHANGELOG.md).

## Concluído
| Área | Entregas |
|---|---|
| Descoberta | Busca única em Europe PMC, PubMed, arXiv, DOAJ e OpenAIRE (OpenAlex opcional), junção sem repetidos com prazo por fonte; filtros e ordenação; panorama do tema; artigos semelhantes |
| Entendimento | Resumo por seções; números com a frase de origem; nota de confiabilidade (8 critérios); ensaios, citações e dados abertos; downloads (txt, md, html, docx, json) e texto completo aberto |
| Brasil | ANVISA, Conitec e Rename por substância, com ligação inglês ↔ português confirmada pelo autor |
| Acompanhamento | Interesses por 14 áreas, subtemas, idiomas e palavras-chave; sininho com artigo novo, retratação, mudança regulatória e novidades de relatórios; feed com 51 fontes curadas |
| Organização e entrega | Biblioteca, etiquetas, listas (com link público), relatório de tema (HTML, DOCX, Markdown) com versões e histórico, 6 estilos de citação e exportação para Zotero, Mendeley e EndNote |
| Conta | Cadastro e login, perfil de uso, troca de senha, exportação e exclusão de dados |
| Laboratório de IA | 16 áreas de análise, comparação, auditoria, verificação de números, cotas e defesas de injeção |
| Plataforma | CI (ruff, mypy, pytest ≥80%, testes de JS), 1.471 testes, deploy no Render, PostgreSQL, front-end próprio com CSP restrita |

## Em andamento
Nenhum item ativo.

## Próximo: pré-lançamento comercial
Itens que **bloqueiam ou condicionam a cobrança**. Ordem sugerida:

| # | Item | Por quê | Referência |
|---:|---|---|---|
| 1 | Tornar o repositório privado e publicar só a documentação aprovada | O código é ativo comercial | [Publicação da documentação](../operacao/publicacao-da-documentacao.md) |
| 2 | Validar o PostgreSQL **de produção** (Neon/Render) e testar backup/restauração | A suíte já passa em PostgreSQL 16 local (20/10/2026); falta o banco real | [Modelo de dados](../arquitetura/dados.md) |
| 3 | Ativar a rotina agendada (`ALERTS_CRON_TOKEN` no Render e segredos no GitHub) | Sem ela, avisos e feed só atualizam com visitas | [Rotinas agendadas](../operacao/rotinas-agendadas.md) |
| 4 | Resolver a licença da **Rename** (CC BY-NC-SA 4.0) | Uso não comercial | [Licenças e termos](../legal/licencas-e-termos.md) |
| 5 | Revisar os termos de cada fonte do feed e de cada API de busca | Uso comercial e agregação | idem |
| 6 | Revisão dos dados do Brasil por farmacêutico/médico (e dos textos de aviso) | Dados sensíveis para decisão | [Saúde no Brasil](../features/saude-no-brasil.md) |
| 7 | E-mail transacional: confirmação de endereço, recuperação de senha, avisos por e-mail | Sem recuperação de senha, o suporte é manual | [Conta e sessões](../features/conta-e-sessoes.md) |
| 8 | Termos de Uso e Política de Privacidade; encarregado (DPO) | LGPD | [Privacidade e LGPD](../legal/privacidade-e-lgpd.md) |
| 9 | Plano de hospedagem sempre ligado, backups testados e monitoramento | Hoje hiberna e não há alertas de operação | [Implantação](../operacao/implantacao.md) |
| 10 | Rodar o roteiro de validação com usuários e decidir o que priorizar | Evidência de valor antes de investir | [Roteiro de validação](roteiro-validacao-usuarios.md) |
| 11 | Revisão de segurança independente | Antes de abrir para clientes | [Segurança](../arquitetura/seguranca.md) |
| 12 | Planos, cobrança e limites por plano | Modelo de negócio | a definir |

## Depois
Ideias candidatas, **sem compromisso de ordem** (cada uma exige validação com usuários):

- **Avisos por e-mail e *push*** (depende do item 7).
- **Cartão de compartilhamento** (imagem com a nota e os critérios de um artigo ou o resumo de uma lista) para divulgação orgânica.
- **Comparar dois ou três artigos lado a lado** (desenho, amostra, resultado, nota).
- **Resumo semanal "O que mudou no seu tema"** (artigos novos, retratações e novidades do feed).
- **Página pública de relatório** com identidade visual, para consultorias entregarem a clientes.
- **Mapa de artigos semelhantes** (grafo interativo colorido pela nota).
- **API pública comercial** (chaves, versionamento, limites por plano) a partir das rotas de descoberta.
- **Limitadores e cotas compartilhados** (para mais de uma instância) e fila para tarefas longas.
- **Migrações de banco versionadas** (hoje o esquema só cresce).
- **Mais fontes do feed** em ciências agrárias e direito em português (hoje sem feed utilizável de Embrapa, Conjur e Migalhas).
- **Medidas de uso do produto sem rastreamento** (contagens agregadas no servidor) para orientar prioridades.
- **Segundo fator de autenticação** e encerramento de sessões ao trocar a senha.

## Decisões já tomadas (para não rediscutir sem motivo)
- Um produto com **núcleo geral** (qualquer área) e **pacote opcional de saúde no Brasil**.
- **Sem IA no que sustenta confiança**; IA só no Laboratório, opcional e rotulada.
- **Notificações só no sininho** por enquanto; e-mail e *push* depois.
- **Feed só para áreas acadêmicas** com fontes curadas; o clique leva à fonte.
- **Tradução automática removida**: o navegador da pessoa já traduz.
- **Streaming de IA revertido** ([ADR-003](../adrs/ADR-003-streaming-revertido.md)).

## Planos detalhados (histórico)
[Plano de dados do Brasil](plano-dados-brasil.md) · [Plano do relatório de tema](plano-relatorio-de-tema.md) · [Descoberta no navegador](navegador-de-artigos-descoberta.md) · [Redesenho visual](plano-redesign-visual.md) · [Economia de tokens](plano-economia-de-tokens.md)
