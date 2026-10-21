# Atualização dos dados do Brasil

Os dados de ANVISA, Conitec e Rename ficam em **instantâneos versionados** no repositório (`nexus-science/dados_brasil/`). O servidor só lê esses arquivos; nenhuma consulta de usuário acessa os sites oficiais. Por isso a atualização é um **passo manual, com revisão**.

## Quando atualizar
| Base | Arquivo | Aviso de defasagem na interface | Frequência sugerida |
|---|---|---|---|
| ANVISA (medicamentos registrados) | `anvisa.json` | 60 dias | Mensal |
| Conitec (recomendações) | `conitec.json` | 60 dias | Mensal (a planilha muda de nome a cada versão) |
| Rename | `rename.json` | 400 dias | A cada nova edição da Rename (revista a cada 1 a 2 anos) |
| Sinônimos inglês ↔ português | `aliases_en_pt.json` | — | Conforme a revisão de especialista e as falhas observadas |

Quando um instantâneo passa do prazo, a interface mostra um aviso de que os dados podem estar desatualizados.

## Procedimento
1. Estar na raiz do repositório com o ambiente de desenvolvimento ativo (`pip install -r requirements-dev.txt`; a Rename usa `pypdf`).
2. Rodar o script da base:
   ```bash
   python scripts/atualizar_anvisa.py
   python scripts/atualizar_conitec.py
   python scripts/atualizar_rename.py
   ```
   Cada script baixa a fonte oficial, monta o instantâneo e imprime um resumo (arquivo de origem, datas e contagens).
3. **Revisar o diff** do JSON (`git diff --stat` e amostras): contagens coerentes com a edição anterior, sem queda abrupta, nomes sem lixo de extração. O instantâneo é a única fonte do servidor.
4. Conferir **por amostra** (principalmente a Rename, extraída de PDF): sortear substâncias e comparar com o documento oficial.
5. Rodar os testes (`pytest tests/test_brasil_*.py` e a suíte completa).
6. Registrar a atualização no [Changelog](../changelog/CHANGELOG.md) (data da fonte e contagens) e fazer o commit.

## Como cada base é obtida
| Base | Origem | Detalhes |
|---|---|---|
| ANVISA | CSV de dados abertos `dados.anvisa.gov.br/dados/DADOS_ABERTOS_MEDICAMENTOS.csv` (≈46 MB) | Reduz de uma linha por registro para uma por **substância** (sem sal e forma farmacêutica): registros ativos e inativos, categorias, classes terapêuticas, empresas e validade mais distante |
| Conitec | Planilha Excel de recomendações no portal da Conitec | O script descobre o link atual na página oficial, lê o XLSX só com a biblioteca padrão e mantém **somente medicamentos**; o nome do arquivo contém a data |
| Rename | PDF oficial da Rename 2024 (2ª edição, 2025) | Extração por script (`pypdf`); itens, apresentações, componente e substâncias; **licença CC BY-NC-SA 4.0** |

Os metadados de cada instantâneo (`meta`) registram fonte, URL, data do arquivo, data da extração e contagens; a interface os mostra junto com os resultados.

## Cuidados
- **Revisão por especialista pendente:** os dados ainda não foram revisados por farmacêutico ou médico; a lista de sinônimos e os textos de aviso também.
- Mudança de formato nas fontes (colunas, nomes de arquivo) quebra os scripts de propósito: melhor falhar do que gravar dados errados.
- **Licença da Rename:** resolver antes de uso comercial (ver [Licenças e termos das fontes](../legal/licencas-e-termos.md)).
- Os instantâneos ficam no Git: o histórico serve de trilha de auditoria de "o que o produto dizia em cada data".
