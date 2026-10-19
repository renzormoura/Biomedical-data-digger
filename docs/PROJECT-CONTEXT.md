# Contexto do projeto

> Este arquivo foi **reescrito em 19/10/2026**. A versão anterior descrevia o produto como um sumarizador de artigos biomédicos; o produto hoje é uma plataforma de pesquisa científica geral com pacote opcional de saúde no Brasil. O conteúdo detalhado está nos documentos abaixo.

## Em uma frase
Plataforma web que ajuda a **encontrar, entender, acompanhar e entregar** pesquisa científica, com critérios abertos de confiabilidade, avisos por interesse e relatórios com método, e com um Laboratório de IA opcional.

## Estado
- Em produção no Render (`https://biomedical-data-digger.onrender.com`), PostgreSQL em produção, SQLite em desenvolvimento.
- Suíte com 1.471 testes (pytest, cobertura mínima de 80%), ruff e mypy limpos, testes de JavaScript.
- Produto comercial: **código privado**, documentação acessível (ver [Publicação da documentação](operacao/publicacao-da-documentacao.md)).

## Onde ler o quê
| Preciso entender… | Documento |
|---|---|
| O que é e para quem | [Visão geral do produto](produto/visao-geral.md) |
| Como usar | [Guia do usuário](produto/guia-do-usuario.md) |
| Cada funcionalidade | [Índice da documentação](README.md#funcionalidades) |
| Como o sistema é montado | [Arquitetura](arquitetura/visao-geral.md), [Módulos](arquitetura/modulos.md), [Dados](arquitetura/dados.md) |
| Rotas | [Referência da API](api/referencia.md) |
| Colocar no ar e manter | [Implantação](operacao/implantacao.md), [Configuração](operacao/configuracao.md), [Runbook](operacao/runbook.md) |
| Trabalhar no código | [Guia de desenvolvimento](desenvolvimento/guia-de-desenvolvimento.md), [Testes](desenvolvimento/testes.md) |
| Riscos jurídicos | [Licenças e termos](legal/licencas-e-termos.md), [Privacidade e LGPD](legal/privacidade-e-lgpd.md) |
| Para onde vamos | [Roadmap](roadmap/roadmap.md) |
| Por que foi feito assim | [ADRs](adrs/) |

## Decisões que não mudam sem motivo
1. Sem IA no que sustenta confiança (nota, extração, relatório, citações, alertas).
2. Dados oficiais do Brasil como instantâneos versionados, nunca consultados em tempo de uso.
3. Falha isolada por fonte: nenhuma fonte externa derruba o produto.
4. Avisos só no sininho por enquanto.
5. Prompts clínicos do Laboratório não mudam sem validação clínica.
6. Segredos só em variáveis de ambiente.
