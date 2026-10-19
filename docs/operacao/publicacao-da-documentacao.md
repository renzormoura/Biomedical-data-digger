# Publicação da documentação (código privado, documentação acessível)

## Objetivo
O produto é comercial: o **código-fonte deve ficar privado**, e a **documentação e a descrição do funcionamento** podem ser acessíveis a clientes, parceiros e avaliadores. Este documento define como separar as duas coisas.

## Estado atual e primeiro passo
1. Tornar o repositório **privado** no GitHub: *Settings → General → Danger Zone → Change repository visibility → Make private* (ou `gh repo edit renzormoura/Biomedical-data-digger --visibility private --accept-visibility-change-consequences`). Esta ação é do dono do repositório.
2. Depois de privado, repositórios e *forks* públicos existentes, caches e clones antigos podem ainda conter o código: verifique se há *forks* e remova o que não for da equipe.
3. Se o repositório já foi público, **considere o histórico comprometido** quanto a segredos: confirme que nenhuma chave, token ou senha já foi versionado (o `.gitignore` bloqueia `.env`, `*.pem` e o banco local) e **rotacione qualquer segredo** que tenha aparecido em commits antigos.
4. Em *Settings → Actions*, manter o fluxo de CI restrito ao repositório; segredos do GitHub (`APP_URL`, `ALERTS_CRON_TOKEN`) ficam só como *secrets*.

## Opções para expor só a documentação
| Opção | Como | Prós | Contras |
|---|---|---|---|
| **A. Repositório público só de documentação (recomendada)** | Criar `Biomedical-data-digger-docs`, copiar `docs/` (sem planos internos) e publicar via GitHub Pages | Simples, gratuito, controle total do que sai | Duas cópias a manter (pode ser automatizado) |
| **B. GitHub Pages do repositório privado** | Pages a partir do repositório privado | Uma única fonte | Exige plano pago (GitHub Pro/Team) e o site fica público ou restrito à organização |
| **C. Site de documentação próprio** | Gerar um site (MkDocs, Docusaurus) a partir de `docs/` e hospedar no domínio do produto | Marca própria, busca, versões | Mais trabalho de manutenção |
| **D. PDF/portal para clientes** | Exportar para PDF e entregar sob NDA | Controle por cliente | Fica desatualizado |

**Recomendação:** começar pela opção A e migrar para C quando houver domínio e clientes.

## O que publicar e o que reter
| Publicar (ok) | Reter (interno) |
|---|---|
| `docs/produto/`, `docs/features/`, `docs/api/` (visão funcional) | `docs/roadmap/` com planos, preços, estratégia e validação com usuários (ver nota) |
| `docs/glossario.md`, `docs/legal/privacidade-e-lgpd.md` (versão para público) | `docs/arquitetura/seguranca.md` (detalhes de defesa e pendências), `docs/operacao/runbook.md` |
| Visão geral da arquitetura (sem módulos e arquivos) | `docs/arquitetura/modulos.md`, `dados.md`, `integracoes-externas.md` (detalhes de implementação) |
| Changelog (versão resumida) | ADRs e `docs/development/` |

Nota: **a documentação deste repositório descreve o código em detalhe** (nomes de módulos, limites, pendências de segurança). Para a versão pública, publique apenas a coluna da esquerda, **revise cada arquivo** e remova nomes de arquivos, parâmetros de segurança, tokens de exemplo, URLs internas e pendências sensíveis.

## Procedimento sugerido (opção A)
1. Criar a pasta `docs-publico/` (ou um ramo) com a seleção acima.
2. Revisar: nenhum segredo, nenhum caminho interno, nenhuma pendência de segurança.
3. Publicar no repositório de documentação e ativar o GitHub Pages.
4. Automatizar (opcional): um fluxo do GitHub Actions que copia a lista aprovada de arquivos para o repositório público a cada release, com revisão manual.

## Cuidados legais
- A documentação pública não concede licença sobre o código nem sobre os dados de terceiros descritos nela.
- Ao citar fontes e licenças de dados (por exemplo, Rename sob CC BY-NC-SA), mantenha a atribuição correta.
- Marcas e logotipos de fontes só com autorização ou dentro das regras delas.
