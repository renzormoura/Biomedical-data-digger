# Feature: Relatório de tema

## Objetivo
Entregar algo pronto a partir de uma lista de leitura: um documento com estudos escolhidos pelo autor, nota de confiabilidade com os critérios, frases estatísticas copiadas do resumo, panorama, referências e um apêndice de método. Serve a qualquer área (referencial do TCC, revisão de literatura, panorama para um cliente). Nada é gerado por IA.

Plano completo e fases seguintes: `docs/roadmap/plano-relatorio-de-tema.md`.

## Status
Fases 1 (relatório mínimo), 2 (seção "Situação no Brasil"), 3 (versões e atualização) e 4 (seletor de perfil, ver [Perfil](perfil.md)) implementadas. Faltam: validação com usuários (fase 5, roteiro pronto) e camada comercial (fase 6).

## Como usar
1. Na **Biblioteca**, abra uma lista e clique em **Criar relatório**. Os estudos da lista são congelados naquele momento.
2. Na tela do relatório, escreva o **título** e a **pergunta ou tema**, desmarque os estudos que não devem entrar e escreva uma **nota por estudo**.
3. Em **Método**, leia o texto automático e, se quiser, acrescente a **sua nota** sobre o método.
4. Se o tema é um medicamento, em **Situação no Brasil** marque as substâncias que o relatório deve tratar (ver a seção abaixo).
5. **Salvar alterações** grava e gera uma nova versão. Os botões de download salvam antes, para o arquivo refletir a tela: **página web (.html)**, **Word (.docx)** e **Markdown (.md)**. Para PDF, abra o HTML no navegador e use Imprimir, Salvar como PDF.

## O que o documento contém
1. Título, versão e número de estudos incluídos; pergunta ou tema.
2. **Panorama** dos incluídos: tipo de estudo, ano, idioma e fonte, mais quantos têm acesso aberto, retratados e sem resumo.
3. **Estudos incluídos:** identificação, tipo de estudo, nota de confiabilidade (0 a 100, banda e cobertura dos critérios), avisos, até 3 frases estatísticas copiadas do resumo e a nota do autor.
4. **Situação no Brasil** (opcional, só para as substâncias que o autor confirmou): Rename 2024, registro na ANVISA e decisões da Conitec, com a data de cada base.
5. **Referências** em ABNT, APA e Vancouver.
6. **Apêndice de método**, montado por código: lista de origem e data, fontes dos registros, quantos estudos foram reunidos, incluídos e excluídos, como a nota é calculada (com os critérios e pesos), limites, versão e data. Depois, os estudos excluídos e a nota do autor.

O relatório não conclui nem recomenda conduta. O método diz explicitamente que **as buscas usadas para achar os estudos não são registradas nesta versão** (a origem é uma lista montada à mão).

## Seção "Situação no Brasil" (pacote de saúde)
- O sistema **sugere** substâncias a partir dos resumos dos estudos incluídos (sinônimos conhecidos e nomes parecidos, com quantos estudos citam cada uma), mas **só entra no documento o que o autor confirma** marcando a caixa. Também dá para adicionar um medicamento pelo nome em português (confere se existe nas bases).
- Para cada substância confirmada, o documento traz: se consta na Rename 2024 (componente e apresentações), o registro na ANVISA (ativos e inativos, categorias, empresas, validade mais distante) e as decisões da Conitec (até 5, com indicação, portaria, data e relatório técnico).
- Fecha com dois avisos fixos: constar na Rename ou ter registro **não** é disponibilidade na unidade de saúde (e a Conitec trata de incorporação ao SUS), e os dados **ainda não foram revisados** por farmacêutico ou médico. A data de extração de cada base aparece na seção e no apêndice de método.
- Os dados são consultados no momento de abrir ou baixar o relatório, nos instantâneos atuais do repositório (não ficam congelados no relatório). Se as bases não puderem ser lidas, o download responde 503 em vez de entregar um documento sem a seção que o autor confirmou.
- Código: `report_brasil.py` (sugerir, descrever e montar os blocos); rotas e tela no mesmo lugar do relatório.

## Versões e atualização (fase 3)
- **Versões:** cada salvamento que muda algo cria uma nova versão, com um resumo do que mudou (título, pergunta, nota do método, estudos incluídos ou excluídos, notas, substâncias, estudos adicionados). Salvar sem mudar nada **não** cria versão (o download também salva antes). Ficam as últimas 50. **Restaurar** devolve o estado editável de uma versão como uma nova versão; estudos adicionados depois continuam no relatório, mas excluídos.
- **Novos na lista de origem:** o relatório lembra de qual lista veio e mostra os artigos que entraram nela depois, com "Adicionar" e "Adicionar todos". Relatórios criados antes da fase 3 não têm lista de origem registrada.
- **Procurar artigos novos sobre o tema:** busca em todas as fontes, mais recentes primeiro, por palavras-chave, idioma e ano inicial (padrão: ano da criação menos 1), e mostra só o que ainda não está no relatório. O autor adiciona o que quiser; o sistema busca os metadados na fonte, não confia no navegador.
- **Acompanhar nos meus alertas:** depois de uma busca, o botão acrescenta aquelas palavras às palavras-chave dos alertas (até 5), para o sininho avisar quando sair artigo novo.
- **Histórico no método:** cada busca e cada adição fica registrada (data e texto) e entra no apêndice como "Histórico de atualizações". Com isso o método deixa de dizer que as buscas não são registradas, mas ainda avisa que a busca que levou aos estudos da lista de origem não foi guardada.
- Código: `ReportStore` (`report_versions`, `report_sources`, `report_log`), `describe_change` e `new_in_list` em `reports.py`.

## Código
- `reports.py`: armazenamento (`ReportStore`: tabelas `reports` e `report_items`, sempre filtradas pela conta), cálculo puro (`assess_study`, `panorama`, `method_paragraphs`) e montagem do documento em blocos (`report_blocks`), que o `downloads.render` converte em HTML, DOCX, Markdown ou texto.
- `browse_api.py`: rotas. `static/browse.js`: botão na lista, seção "Relatórios de tema" na biblioteca e a tela `#/relatorio/<id>`.

## API (exige conta)

| Rota | O que faz |
|---|---|
| `POST /api/reports` | Cria a partir de `list_id` (e título e pergunta opcionais) |
| `GET /api/reports` | Lista os relatórios da conta |
| `GET /api/reports/{id}` | Relatório completo: estudos com nota e frases, panorama, método e critérios |
| `PUT /api/reports/{id}` | Salva título, pergunta, nota do método, substâncias confirmadas (opcional; sem o campo, mantém) e, por estudo, inclusão e nota (nova versão) |
| `GET /api/reports/{id}/brasil` | Sugestões de substâncias (a confirmar) e a situação das já confirmadas, com a data de cada base |
| `GET /api/reports/{id}/history` | Versões, histórico de buscas e adições e artigos novos na lista de origem |
| `POST /api/reports/{id}/search` | Procura artigos fora do relatório (`query`, `language`, `yearFrom`) e registra a busca |
| `POST /api/reports/{id}/add` | Adiciona estudos (`refs`, `origin` = `lista` ou `busca`, `query`) e cria uma versão |
| `POST /api/reports/{id}/restore` | Restaura uma versão (`version`) como nova versão |
| `DELETE /api/reports/{id}` | Exclui |
| `GET /api/reports/{id}/download?format=html\|docx\|md\|txt` | Baixa o documento |

## Limites
- Até 30 relatórios por conta e 200 estudos por relatório; texto de notas limitado (título 200, pergunta 2.000, nota por estudo 1.000, nota do método 3.000 caracteres).
- A nota de confiabilidade usa só título, resumo e metadados. Registros sem resumo ficam com nota indeterminada.
- Os metadados de cada estudo são um retrato do momento em que ele entrou no relatório e não se atualizam sozinhos; só entram estudos novos quando o autor adiciona.
- A busca de novidades tem os mesmos limites das demais buscas (ruído, poucos resultados em português) e traz no máximo 20 resultados por vez.
- Versões guardam o estado editável, não uma cópia dos metadados dos estudos.
- A ordem dos estudos é a da lista; ainda não é possível reordenar.
- Até 10 substâncias por relatório; a sugestão analisa os 120 primeiros estudos incluídos.
- A ligação de nomes é automática e pode errar ou deixar nomes de fora: por isso a confirmação é do autor.
- Não há link público de leitura do relatório nem PDF direto.

## Testes
`tests/test_reports.py` (armazenamento, limites, isolamento entre contas, panorama, método, seções do documento, rotas e downloads em HTML, DOCX, Markdown e texto, incluindo escape de HTML).
