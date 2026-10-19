# Plano: relatório de tema (núcleo geral) com o pacote "Saúde no Brasil"

Status: fases 1 a 4 implementadas em 2026-10-18 (ver `docs/features/relatorio-de-tema.md` e `docs/features/perfil.md`); fase 5 com o roteiro preparado em `docs/roadmap/roteiro-validacao-usuarios.md` (nenhuma sessão feita); fase 6 pendente. Decisão estratégica tomada com o usuário em 2026-10-18: o produto é **um só**, com um núcleo para qualquer área do conhecimento e um pacote vertical opcional para saúde no Brasil.

## 1. Problema

O fluxo atual cobre achar, entender, organizar, acompanhar e citar artigos. Falta a etapa final: **entregar algo pronto**. O estudante entrega a revisão de literatura do TCC, o pesquisador monta o referencial teórico, a consultoria entrega um panorama ao cliente. Hoje essa pessoa copia as referências, cola trechos e escreve o método de busca à mão, fora do produto.

O relatório de tema é essa entrega: um documento com estudos escolhidos por critério visível, método declarado, datas das fontes e referências prontas, que pode ser atualizado.

## 2. Posicionamento: dois pacotes, um produto

| | Núcleo (qualquer área) | Pacote "Saúde no Brasil" (opcional) |
|---|---|---|
| Para quem | Estudante, pesquisador, consultoria | Farmácia, consultoria em saúde, pesquisador de saúde |
| Conteúdo | Busca, confiabilidade, biblioteca, alertas, citações, **relatório de tema** | Seção ANVISA, Conitec e Rename dentro do relatório de medicamentos |
| Já existe | Quase tudo, falta o relatório | Cartão "Situação no Brasil" (as três bases) |
| Preço previsto | Gratuito + plano profissional geral | Complemento ou plano próprio |

Regras para não diluir o produto:
- O núcleo recebe qualquer novidade primeiro. O pacote vertical só ganha recurso novo depois de evidência de que alguém usa e paga.
- O pacote fica limitado às três bases que já existem. **Preços (CMED), comparação de mudanças regulatórias e modelos para comissão de farmácia ficam fora** até uma validação com usuários.
- Todo recurso do núcleo precisa passar no teste: "um estudante de qualquer área usaria isto no TCC?".
- O pacote só aparece para quem diz ser de saúde (seletor de perfil, fase 4).

## 3. O que o relatório contém

Um relatório parte de **uma lista de leitura** (já existe) ou de uma **busca salva**, e de um título e uma pergunta ou tema escritos pelo usuário.

1. **Capa e pergunta:** título, pergunta de pesquisa ou tema, autor, data e versão.
2. **Estudos incluídos:** para cada um, referência, tipo de estudo, nota de confiabilidade com os critérios, marca de retratado, frases estatísticas copiadas do resumo (as que já extraímos, sempre com a frase de origem) e a nota do usuário.
3. **Panorama (por código):** contagem por tipo de estudo, por ano e por idioma; quantos têm acesso aberto.
4. **Situação no Brasil (só em temas de medicamento, pacote vertical):** registro na ANVISA, decisões da Conitec e Rename, com a data de cada base e o aviso "constar não é estar disponível na sua unidade".
5. **Referências:** nos estilos que já existem (ABNT, APA, Vancouver, IEEE, Harvard, MLA), mais exportação para Zotero, Mendeley e EndNote.
6. **Apêndice de método (obrigatório):** as buscas usadas e as fontes consultadas, o que o usuário incluiu e excluiu e quando, a data e a versão de cada base do Brasil, os critérios de confiabilidade e os limites. É o que torna o documento reproduzível e confiável.

O que o relatório **não** faz: não escreve conclusões nem recomenda conduta. Um resumo gerado por IA, se vier, será opcional e rotulado, em outra fase. A promessa do documento é "nada foi inventado".

## 4. Arquitetura (o que reaproveita)

- **Estudos e curadoria:** `library_store` (listas, etiquetas) ganha a noção de relatório como um conjunto de itens com nota e posição.
- **Avaliação de cada estudo:** `discovery.analysis` já devolve confiabilidade, seções e dados estatísticos. O relatório usa o resultado, sem recalcular nada.
- **Panorama:** funções puras sobre a lista de `Work`.
- **Situação no Brasil:** `brasil.consulta` (já pronto), acionado só quando o usuário confirma a substância.
- **Documento:** o gerador de downloads (`downloads.py`) já transforma blocos em TXT, Markdown, HTML e DOCX. O PDF vem da impressão do HTML, sem dependência nova na primeira versão.
- **Dados novos:** tabelas `reports` e `report_items` (com versão), sempre filtradas pela conta, como a biblioteca.
- **Interface:** uma tela "Relatório" a partir da lista de leitura, com pré-visualização, e rota pública de leitura por link (opcional, como o compartilhamento de listas).

## 5. Fases

1. **Relatório mínimo (núcleo):** criar a partir de uma lista; título e pergunta; estudos com nota do usuário; panorama; referências; apêndice de método; visualização na tela e download em HTML e DOCX. Critério de pronto: um estudante consegue gerar o referencial de um TCC em minutos e o documento declara o método sem edição manual.
2. **Encaixe do pacote de saúde:** a seção "Situação no Brasil" entra quando o tema é um medicamento, com a substância confirmada pelo usuário e a data de cada base.
3. **Versões e atualização:** reabrir um relatório, ver o que é novo desde a última versão e juntar com os alertas ("novidades deste tema desde o seu relatório").
4. **Seletor de perfil:** na primeira entrada o usuário diz o que faz; o pacote de saúde liga ou desliga conforme o perfil.
5. **Validação com usuários:** 5 temas reais (3 de áreas diferentes, 2 de medicamentos) e 3 ou 4 pessoas comparando com o que fazem hoje, medindo tempo e o que faltou. Só depois disso decidir preços, CMED e o que mais entra no vertical. Roteiro pronto (6 pessoas, 7 hipóteses, tarefas, fichas e critérios de decisão): `docs/roadmap/roteiro-validacao-usuarios.md`.
6. **Camada comercial:** logo e modelo da instituição, compartilhamento por equipe, plano pago.

## 6. Riscos

- **Responsabilidade clínica:** o texto diz sempre que é apoio e não parecer técnico, e nunca conclui "recomendamos".
- **Dado defasado:** cada seção mostra a data da base e alerta quando passa de 60 dias (regra que já existe no cartão).
- **Licença da Rename (CC BY-NC-SA):** o relatório é justamente um produto comercial. Resolver antes de cobrar pelo pacote de saúde.
- **Nome ligado à substância errada:** a confirmação da substância pelo usuário é obrigatória no relatório.
- **Promessa maior que a entrega:** "todas as áreas" exige que os termos dos alertas e a qualidade da busca sejam revisados fora da saúde. Dizer isso na interface.
- **Diluição do foco:** mitigada pelas regras da seção 2.
- **Qualidade da nota de confiabilidade:** ela é calculada só com o resumo e os metadados. O relatório precisa repetir o aviso de limitação ao lado de cada nota.

## 7. Decisões que preciso de você

1. Formato inicial: HTML imprimível e DOCX bastam para a fase 1, com o PDF vindo da impressão? Recomendo que sim.
2. O relatório parte só de listas de leitura, ou também de buscas salvas? Recomendo começar só com listas (já existem) e adicionar buscas salvas depois.
3. O apêndice de método deve ser editável pelo usuário (por exemplo, para acrescentar critérios próprios)? Recomendo gerar automático na fase 1 e permitir uma nota livre.
4. Há alguém para validar os relatórios na fase 5, ou preparo um roteiro de teste para você aplicar?
