# Feature: Relatório de tema

## Objetivo
Entregar algo pronto a partir de uma lista de leitura: um documento com estudos escolhidos pelo autor, nota de confiabilidade com os critérios, frases estatísticas copiadas do resumo, panorama, referências e um apêndice de método. Serve a qualquer área (referencial do TCC, revisão de literatura, panorama para um cliente). Nada é gerado por IA.

Plano completo e fases seguintes: `docs/roadmap/plano-relatorio-de-tema.md`.

## Status
Fase 1 implementada (relatório mínimo). Faltam: seção "Situação no Brasil" para medicamentos (fase 2), versões e atualização (fase 3), seletor de perfil (fase 4) e validação com usuários (fase 5).

## Como usar
1. Na **Biblioteca**, abra uma lista e clique em **Criar relatório**. Os estudos da lista são congelados naquele momento.
2. Na tela do relatório, escreva o **título** e a **pergunta ou tema**, desmarque os estudos que não devem entrar e escreva uma **nota por estudo**.
3. Em **Método**, leia o texto automático e, se quiser, acrescente a **sua nota** sobre o método.
4. **Salvar alterações** grava e gera uma nova versão. Os botões de download salvam antes, para o arquivo refletir a tela: **página web (.html)**, **Word (.docx)** e **Markdown (.md)**. Para PDF, abra o HTML no navegador e use Imprimir, Salvar como PDF.

## O que o documento contém
1. Título, versão e número de estudos incluídos; pergunta ou tema.
2. **Panorama** dos incluídos: tipo de estudo, ano, idioma e fonte, mais quantos têm acesso aberto, retratados e sem resumo.
3. **Estudos incluídos:** identificação, tipo de estudo, nota de confiabilidade (0 a 100, banda e cobertura dos critérios), avisos, até 3 frases estatísticas copiadas do resumo e a nota do autor.
4. **Referências** em ABNT, APA e Vancouver.
5. **Apêndice de método**, montado por código: lista de origem e data, fontes dos registros, quantos estudos foram reunidos, incluídos e excluídos, como a nota é calculada (com os critérios e pesos), limites, versão e data. Depois, os estudos excluídos e a nota do autor.

O relatório não conclui nem recomenda conduta. O método diz explicitamente que **as buscas usadas para achar os estudos não são registradas nesta versão** (a origem é uma lista montada à mão).

## Código
- `reports.py`: armazenamento (`ReportStore`: tabelas `reports` e `report_items`, sempre filtradas pela conta), cálculo puro (`assess_study`, `panorama`, `method_paragraphs`) e montagem do documento em blocos (`report_blocks`), que o `downloads.render` converte em HTML, DOCX, Markdown ou texto.
- `browse_api.py`: rotas. `static/browse.js`: botão na lista, seção "Relatórios de tema" na biblioteca e a tela `#/relatorio/<id>`.

## API (exige conta)

| Rota | O que faz |
|---|---|
| `POST /api/reports` | Cria a partir de `list_id` (e título e pergunta opcionais) |
| `GET /api/reports` | Lista os relatórios da conta |
| `GET /api/reports/{id}` | Relatório completo: estudos com nota e frases, panorama, método e critérios |
| `PUT /api/reports/{id}` | Salva título, pergunta, nota do método e, por estudo, inclusão e nota (nova versão) |
| `DELETE /api/reports/{id}` | Exclui |
| `GET /api/reports/{id}/download?format=html\|docx\|md\|txt` | Baixa o documento |

## Limites
- Até 30 relatórios por conta e 200 estudos por relatório; texto de notas limitado (título 200, pergunta 2.000, nota por estudo 1.000, nota do método 3.000 caracteres).
- A nota de confiabilidade usa só título, resumo e metadados. Registros sem resumo ficam com nota indeterminada.
- Os estudos são um retrato do momento da criação: não se atualizam sozinhos (isso é a fase 3).
- A ordem dos estudos é a da lista; ainda não é possível reordenar.
- Não há link público de leitura do relatório nem PDF direto.

## Testes
`tests/test_reports.py` (armazenamento, limites, isolamento entre contas, panorama, método, seções do documento, rotas e downloads em HTML, DOCX, Markdown e texto, incluindo escape de HTML).
