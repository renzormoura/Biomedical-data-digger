# Licença e confidencialidade

## Situação
O Nexus Science é um **produto comercial proprietário**. O código-fonte é **privado e confidencial**; a documentação e a descrição de funcionamento podem ser compartilhadas conforme [Publicação da documentação](../operacao/publicacao-da-documentacao.md).

O arquivo [LICENSE](../../LICENSE) na raiz declara "todos os direitos reservados". **Pendência:** preencher o nome do titular (pessoa ou empresa) antes de qualquer distribuição.

## O que isso significa na prática
| Item | Regra |
|---|---|
| Código-fonte | Privado. Acesso só a pessoas autorizadas e sob sigilo |
| Repositório no GitHub | Deve estar **privado** (ver o procedimento em [Publicação da documentação](../operacao/publicacao-da-documentacao.md)) |
| Documentação em `docs/` | Interna por padrão; só os documentos aprovados saem em versão pública |
| Dados curados (instantâneos do Brasil, lista do feed, sinônimos) | Fazem parte do ativo; os dados de origem seguem a licença de cada fonte |
| Marca, nome e identidade visual | Reservados ao titular |
| Contribuições de terceiros | Só mediante contrato que transfira ou licencie os direitos ao titular |

## Antes de abrir o produto a clientes
1. Definir o titular no `LICENSE` e nos Termos de Uso.
2. Redigir os **Termos de Uso** e a **Política de Privacidade** (revisão jurídica).
3. Fechar a [lista de pendências de licenças das fontes](licencas-e-termos.md#lista-de-pendências-para-o-lançamento-comercial).
4. Se houver prestadores ou colaboradores: contrato de confidencialidade e de cessão de direitos.
5. Confirmar que o histórico do repositório não contém segredos nem dados pessoais.

## Dependências e licenças de terceiros
O produto usa bibliotecas de código aberto (ver `requirements.txt`). A distribuição **somente como serviço** (sem entregar o código aos clientes) simplifica as obrigações de licenças de código aberto, mas o inventário de licenças deve ser arquivado e as notas de atribuição, quando exigidas, devem constar em uma página "Sobre/Créditos" do produto. Bibliotecas com *copyleft* fraco (como `psycopg`, LGPL) são usadas como dependência, sem modificação.

## Atribuições exibidas no produto
O rodapé e as páginas de dados citam as fontes (Europe PMC, PubMed, arXiv, DOAJ, OpenAIRE, ClinicalTrials.gov, OpenCitations, DataCite, ANVISA, Conitec, Rename). Mantenha essas atribuições ao alterar o front-end.
