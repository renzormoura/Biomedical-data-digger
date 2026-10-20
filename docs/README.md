# Documentação do Biomedical Data Digger

Biomedical Data Digger é uma plataforma web de pesquisa científica: busca em várias fontes abertas, avalia com critérios transparentes a confiabilidade de cada artigo, acompanha novidades por interesse e entrega o resultado em relatórios, listas e referências prontas para gerenciadores bibliográficos.

> **Confidencialidade.** O código-fonte é proprietário e privado (ver [Licença e confidencialidade](legal/licenca-e-confidencialidade.md)). Esta é a documentação **interna completa**: parte dela (produto, funcionalidades, guia do usuário) pode ser publicada; outra parte (módulos, segurança, runbook, pendências) deve ficar restrita. O que sai e como sai está em [Publicação da documentação](operacao/publicacao-da-documentacao.md).

## Por onde começar

| Se você é… | Leia |
|---|---|
| Cliente, parceiro ou avaliador | [Visão geral do produto](produto/visao-geral.md) → [Guia do usuário](produto/guia-do-usuario.md) |
| Pessoa de produto ou negócio | [Visão geral](produto/visao-geral.md) → [Funcionalidades](#funcionalidades) → [Licenças e termos das fontes](legal/licencas-e-termos.md) → [Roadmap](roadmap/roadmap.md) |
| Pessoa de engenharia nova no projeto | [Arquitetura](arquitetura/visao-geral.md) → [Módulos](arquitetura/modulos.md) → [Guia de desenvolvimento](desenvolvimento/guia-de-desenvolvimento.md) |
| Operação / suporte | [Implantação](operacao/implantacao.md) → [Configuração](operacao/configuracao.md) → [Rotinas agendadas](operacao/rotinas-agendadas.md) → [Runbook](operacao/runbook.md) |
| Segurança / privacidade | [Segurança](arquitetura/seguranca.md) → [Privacidade e LGPD](legal/privacidade-e-lgpd.md) |
| Integração | [Referência da API](api/referencia.md) |

## Mapa da documentação

### Produto
- [Visão geral do produto](produto/visao-geral.md): o que é, para quem, princípios e limites.
- [Guia do usuário](produto/guia-do-usuario.md): como usar cada parte, passo a passo.
- [Glossário](glossario.md)

### Funcionalidades
Cada documento explica o objetivo, o que a pessoa vê, como funciona por dentro, os limites e os arquivos envolvidos.

- [Busca em várias fontes](features/busca-artigos.md) e [Panorama do tema](features/panorama-do-tema.md)
- [Nota de confiabilidade](features/confiabilidade.md)
- [Página do artigo, enriquecimento e downloads](features/pagina-do-artigo.md)
- [Biblioteca, etiquetas e listas de leitura](features/biblioteca-e-listas.md)
- [Interesses, alertas e notificações (o sininho)](features/notificacoes.md)
- [Feed de novidades acadêmicas](features/feed.md)
- [Relatório de tema](features/relatorio-de-tema.md)
- [Citações e exportação](features/citacoes-exportacao.md)
- [Pacote Saúde no Brasil (ANVISA, Conitec, Rename)](features/saude-no-brasil.md)
- [Planos, assinatura e pagamento por Pix](features/assinaturas.md) e [Aba de Administração](features/administracao.md)
- [Perfil e conta](features/perfil.md) e [Conta, sessões e dados pessoais](features/conta-e-sessoes.md)
- [Laboratório de IA (opcional)](features/analises-clinicas.md)

### Arquitetura
- [Visão geral da arquitetura](arquitetura/visao-geral.md)
- [Catálogo de módulos](arquitetura/modulos.md)
- [Modelo de dados](arquitetura/dados.md)
- [Front-end](arquitetura/frontend.md)
- [Segurança](arquitetura/seguranca.md)
- [Integrações externas](arquitetura/integracoes-externas.md)
- [Decisões de arquitetura (ADRs)](adrs/)

### API
- [Referência da API](api/referencia.md)

### Operação
- [Tutorial: primeiro deploy no Render](operacao/tutorial-primeiro-deploy.md) · [Implantação](operacao/implantacao.md) · [Configuração](operacao/configuracao.md) · [Rotinas agendadas](operacao/rotinas-agendadas.md) · [Atualização dos dados do Brasil](operacao/dados-brasil.md) · [Runbook](operacao/runbook.md) · [Publicação da documentação](operacao/publicacao-da-documentacao.md)

### Desenvolvimento
- [Guia de desenvolvimento](desenvolvimento/guia-de-desenvolvimento.md) · [Estratégia de testes](desenvolvimento/testes.md) · [Preparar o ambiente](development/setup.md) · [Passagem de bastão](development/HANDOFF.md)

### Jurídico
- [Licença e confidencialidade](legal/licenca-e-confidencialidade.md) · [Licenças e termos das fontes](legal/licencas-e-termos.md) · [Privacidade e LGPD](legal/privacidade-e-lgpd.md)

### Planejamento e histórico
- [Roadmap](roadmap/roadmap.md) · [Changelog](changelog/CHANGELOG.md) · [Roteiro de validação com usuários](roadmap/roteiro-validacao-usuarios.md)

## Convenções desta documentação
- Idioma: português do Brasil. Nomes de arquivos, rotas e campos técnicos ficam como no código.
- Cada documento de funcionalidade tem as seções **Objetivo**, **O que a pessoa vê**, **Como funciona**, **Limites** e **Arquivos**.
- Números (limites, prazos, pesos) vêm do código; quando mudarem lá, mude aqui. Os testes em `tests/` são a fonte de verdade do comportamento.
- Estado verificado em 19/10/2026 (suíte com 1.471 testes passando).
