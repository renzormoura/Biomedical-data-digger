# Roteiro de validação com usuários (fase 5)

Status: preparado em 2026-10-18, **nenhuma sessão feita ainda**. Parte da fase 5 de `docs/roadmap/plano-relatorio-de-tema.md`.

Este roteiro serve para descobrir, com poucas pessoas e pouco custo, **se o relatório de tema e o pacote "Saúde no Brasil" valem o esforço e o preço**. Ele não mede o produto inteiro: mede o fluxo *buscar, escolher estudos, gerar o relatório, atualizar e entregar*.

## 1. O que queremos descobrir

| # | Hipótese | Como vamos saber | Critério para considerar confirmada |
|---|---|---|---|
| H1 | Quem já faz revisão de literatura **economiza tempo** gerando o relatório aqui | Tempo da tarefa A aqui contra o tempo que a pessoa diz levar hoje | Pelo menos 3 de 4 participantes dizem levar mais tempo hoje, e ninguém leva mais de 20 minutos aqui |
| H2 | O **apêndice de método** é entendido e considerado útil (não decorativo) | Pergunta direta + a pessoa explica com as próprias palavras o que o método diz | 3 de 4 explicam corretamente e 3 de 4 dizem que usariam no trabalho |
| H3 | A **nota de confiabilidade** é interpretada como apoio, não como veredito | Pergunta "o que essa nota quer dizer?" | Ninguém diz que "o artigo é bom/ruim" só pela nota; 3 de 4 citam que olhariam os critérios |
| H4 | A seção **Situação no Brasil** é útil para quem trabalha com medicamentos | Tarefa C e perguntas | 2 de 2 profissionais de saúde dizem que usariam e **nenhum dado errado** foi encontrado (ou os erros foram anotados e corrigidos) |
| H5 | O produto serve a áreas **fora da saúde** | Tarefa A com tema de outra área | Os 2 participantes de outras áreas concluem a tarefa sem ajuda |
| H6 | Há **disposição de pagar** e uma faixa de preço | Perguntas da seção 8 | Pelo menos 2 de 6 dizem que pagariam por conta própria ou pela instituição |
| H7 | Os **alertas** trazem artigos úteis | Revisão dos avisos ao fim de 7 dias | Pelo menos metade dos avisos recebidos é considerada pertinente |

Hipóteses que podem **mudar o plano** se falharem: H1 (não há valor no relatório), H4 (não vale ampliar o vertical de saúde) e H6 (não há modelo comercial).

## 2. Quem convidar

Meta: **6 pessoas**, em sessões individuais. O plano original dizia "3 ou 4 pessoas"; com 6 dá para ter 2 de saúde e 4 de outros perfis sem que um caso isolado decida tudo.

| Perfil | Quantas | Critério de entrada |
|---|---|---|
| Profissional de saúde ou farmacêutico | 2 | Já precisou levantar evidência sobre um medicamento nos últimos 6 meses |
| Pesquisador ou pós-graduando | 2 | Está escrevendo ou revisando um artigo, dissertação ou tese |
| Estudante de graduação | 1 | Está fazendo TCC ou trabalho de revisão |
| Consultoria ou assessoria | 1 | Entrega panoramas ou relatórios de evidência a clientes |

Pelo menos **2 participantes de áreas fora da saúde** (direito, educação, computação, engenharia, ciências sociais...).

**Triagem (3 perguntas):** (1) O que você pesquisa ou entrega com base em artigos? (2) Como você faz isso hoje (ferramentas, tempo)? (3) Você usaria um tema real seu na sessão? Quem **não** tem um tema real não entra: o teste com tema inventado não mostra o que importa.

Evitar amigos próximos que só queiram agradar. Pedir de forma explícita: "quero saber o que não funciona".

## 3. Antes de cada sessão (checklist da equipe)

- [ ] Endereço de **homologação ou produção** funcionando. **Atenção:** o caminho com PostgreSQL (Neon) ainda não foi validado para alertas, listas e relatórios. Antes de convidar alguém, fazer um teste completo (criar conta, lista, relatório, baixar o DOCX) no ambiente que será usado.
- [ ] Conta de teste **nova** para cada pessoa (e-mail de teste, não o dela), ou a pessoa cria a própria. Nunca pedir a senha de nenhum serviço.
- [ ] Os dados do Brasil (ANVISA, Conitec, Rename) estão dentro do prazo (menos de 60 dias).
- [ ] Gravação de tela e áudio **só com consentimento** (ver seção 10). Se não houver, anotar à mão.
- [ ] Ficha de observação impressa ou aberta (seção 7) e cronômetro.
- [ ] Listas de reserva prontas (seção 4) para quem travar na escolha do tema.
- [ ] Computador e celular disponíveis (pelo menos metade das pessoas usa o celular para ler).

## 4. Temas

O ideal é o **tema real** da pessoa. Reserva, caso trave:

| Área | Tema de reserva |
|---|---|
| Medicina | Exercício físico e pressão arterial em adultos |
| Medicamento | AAS e prevenção da pré-eclâmpsia |
| Medicamento | Metformina em idosos |
| Educação | Inteligência artificial no ensino superior |
| Meio ambiente | Mudanças climáticas e produtividade agrícola |

## 5. Estrutura da sessão (45 minutos)

| Minutos | Etapa |
|---|---|
| 0–5 | Boas-vindas, consentimento, o que é e o que não é o teste |
| 5–10 | Conversa: como a pessoa faz isso hoje e quanto tempo leva |
| 10–35 | Tarefas A, B, C (ver seção 6), em voz alta |
| 35–42 | Perguntas finais (seções 8 e 9) |
| 42–45 | Agradecimento e combinação do acompanhamento de 7 dias |

### Fala de abertura (adaptar)
"Obrigado por ajudar. Estamos testando **o produto, não você**: se algo for confuso, o problema é nosso. Pense em voz alta enquanto usa. Não vou explicar como funciona; se travar, tudo bem, quero ver onde. É um protótipo: pode haver erros, e os dados do Brasil ainda **não foram revisados por especialista**. Se ver algo errado, me avise. Posso gravar a tela e o áudio? Você pode pedir para parar a qualquer momento."

### Regras do facilitador
- Não ensinar, não defender o produto, não completar frases. Perguntar "o que você esperava que acontecesse?".
- Só ajudar depois de **2 minutos travado**, e anotar que houve ajuda.
- Anotar o que a pessoa **faz**, não só o que diz.

## 6. Tarefas

Cada tarefa tem texto exato para ler, o que contar como sucesso e o que anotar.

### Tarefa A: do tema à lista e ao relatório (núcleo, todos)
**Texto:** "Imagine que você precisa de uma revisão rápida da literatura sobre [seu tema]. Use o produto para reunir uns 5 estudos que você usaria e gerar um documento que você poderia entregar."
- **Sucesso:** a pessoa busca, salva em uma lista, cria o relatório, marca o que entra, baixa o arquivo (HTML ou Word) **sem ajuda**.
- **Anotar:** tempo total; onde hesitou; se achou o botão "Criar relatório"; se usou filtros; se abriu a nota de confiabilidade; se escreveu notas; se baixou DOCX ou HTML.
- **Pergunta ao final:** "Isso está perto do que você entregaria hoje? O que falta ou sobra?"

### Tarefa B: ler o método e a nota (núcleo, todos)
**Texto:** "Abra o documento que você baixou e me explique, com suas palavras, **como esses estudos foram escolhidos** e **o que significa a nota de cada um**."
- **Sucesso:** explica corretamente que os estudos foram reunidos pela pessoa, que a nota usa só título, resumo e metadados, e que ela não substitui ler o artigo.
- **Anotar:** frases dela sobre "confiança"; se tratou a nota como veredito; se achou o método útil ou "burocrático"; se faltou algum dado.

### Tarefa C: situação no Brasil (só saúde e quem trabalha com medicamentos)
**Texto:** "O tema envolve um medicamento. Inclua no relatório a situação dele no Brasil e me diga o que você aprendeu."
- **Sucesso:** confirma a substância, salva, vê Rename, ANVISA e Conitec no documento e explica **sem confundir** "consta na Rename" com "tem na minha unidade".
- **Anotar:** se entendeu que precisa confirmar a substância; se **algum dado parece errado** (anotar o dado e a fonte conferida); se faltou algo (preço, estoque, protocolo).

### Tarefa D: atualizar (todos, rápida)
**Texto:** "Passou um mês. Você quer saber se saiu algo novo sobre o tema. Como faria aqui?"
- **Sucesso:** usa "Procurar artigos novos sobre o tema" ou os alertas; adiciona um estudo; encontra o histórico.
- **Anotar:** se achou o painel "Atualizar o relatório"; se entendeu as versões; se entendeu o "Acompanhar nos meus alertas".

### Tarefa E: alertas (todos; deixar ligado por 7 dias)
**Texto:** "Escolha áreas, subtemas e idiomas que você quer acompanhar e salve."
- **Sucesso:** conclui em até 3 minutos.
- **Acompanhamento no 7º dia:** pedir que abra o sininho e classifique **cada aviso** como pertinente, mais ou menos ou irrelevante.

### Observação no celular
Se a pessoa lê no celular, repetir **só a parte de leitura** (abrir o artigo, ver a nota, abrir o relatório, usar o botão Exportar) no telefone dela por 5 minutos.

## 7. Ficha de observação (uma por participante)

```
Participante: P__   Data: __/__/____   Perfil: ____________   Área do tema: ____________
Tema usado: ______________________  (real / reserva)    Dispositivo: computador / celular
Gravação com consentimento: sim / não

Tarefa | Concluiu sem ajuda? (S/N) | Minutos | Ajuda dada | Onde travou | Citações marcantes
A      |                           |         |            |             |
B      |                           |         |            |             |
C      |                           |         |            |             |
D      |                           |         |            |             |
E      |                           |         |            |             |

Tempo que diz levar hoje para a tarefa A: ______ min    Ferramentas que usa hoje: ______________
Entendeu a nota como apoio (S/N): __   Explicou o método corretamente (S/N): __
Dados do Brasil errados ou faltando (dado | fonte conferida): ______________________________
Erros ou bugs vistos: ____________________________________________
Pedidos espontâneos (o que sentiu falta): ____________________________
```

Planilha de consolidação (uma linha por participante): `id, perfil, area, tema_real, dispositivo, A_sem_ajuda, A_min, B_correto, B_util, C_sem_ajuda, D_sem_ajuda, E_min, tempo_hoje_min, usaria, pagaria, faixa_preco, notas_pertinentes_7d, bugs`.

## 8. Perguntas finais

**Valor**
1. Em uma frase, para que serve isso?
2. Você usaria no seu trabalho real? Com que frequência?
3. O que você **não** faria aqui e continuaria fazendo à mão?
4. O que está faltando para você entregar o documento sem retocar?

**Confiança**
5. Você confia no que o relatório diz? Em que parte menos?
6. A nota de confiabilidade ajudou a decidir? Em algum momento você discordou dela?

**Comparação**
7. Quanto tempo você leva hoje para fazer algo equivalente? Com quais ferramentas?
8. O que é melhor aqui? O que é pior?

**Preço** (perguntar só depois de a pessoa ter usado)
9. Você pagaria por isso, do próprio bolso ou pela instituição? Quem decide a compra?
10. A que preço mensal você acharia **barato demais, que desconfiaria** de qualidade? E **caro, mas ainda pensaria**? E **caro demais**?
11. O que teria de ter para valer pagar (relatórios ilimitados, alertas, equipe, logo da instituição, DOCX)?

## 9. Questionário curto de satisfação (após as tarefas)

Escala de 1 (discordo totalmente) a 5 (concordo totalmente):
1. Eu usaria isso com frequência.
2. Achei o fluxo mais complexo do que precisava.
3. Foi fácil de usar.
4. Eu precisaria de ajuda para usar sozinho(a).
5. As partes do produto pareciam bem integradas.
6. Aprenderia a usar com rapidez.

(Versão curta inspirada na escala SUS; itens 2 e 4 são invertidos. Com 6 pessoas serve como termômetro, não como estatística.)

## 10. Consentimento e privacidade (LGPD)

Ler e registrar o aceite verbal ou por escrito:
- A sessão é sobre o **produto**, e os dados da pessoa não serão publicados nem identificados.
- Gravação de tela e áudio é **opcional**, guardada em local protegido e apagada após a análise (prazo sugerido: 90 dias).
- **Nenhum dado de paciente** nem informação confidencial de cliente deve ser usado no teste; usar temas públicos.
- A pessoa pode parar a qualquer momento e pedir a exclusão do que foi coletado.
- A conta de teste é descartável; senhas reais não são pedidas.
- Os resultados são citados de forma anônima ("P3, farmacêutica hospitalar").

Se houver compensação (vale-presente, por exemplo), definir antes e informar no convite.

## 11. Como analisar

1. Em até 48 horas de cada sessão, preencher a planilha e escrever **3 achados** (o mais grave, o mais surpreendente, o pedido mais repetido).
2. Depois das 6 sessões, classificar cada problema por **gravidade** (impede a tarefa / atrapalha / incomoda) e **frequência** (quantos de 6).
3. Tratar como bloqueio de lançamento: qualquer problema que **impediu a tarefa A em 2 ou mais pessoas**, qualquer **dado errado do Brasil** confirmado e qualquer caso de "constar na Rename" entendido como "disponível".
4. Marcar cada hipótese (H1 a H7) como **confirmada, parcial ou refutada**, com as citações que sustentam.

### Decisões que o resultado deve alimentar

| Se... | Então... |
|---|---|
| H1 e H2 confirmadas | Seguir com a camada comercial (fase 6) do relatório |
| H1 refutada | Voltar ao núcleo (busca, alertas) e repensar o relatório antes de investir mais |
| H4 confirmada **e** os profissionais pedirem preço | Avaliar a tabela da CMED e o Banco de Preços; não antes |
| H4 confirmada, mas houver dados errados | Priorizar a **revisão por farmacêutico ou médico** e a correção dos apelidos antes de ampliar |
| H4 refutada | Manter o pacote como está, sem ampliar o vertical |
| H5 refutada | Reforçar o texto e os termos das outras áreas, que ninguém revisou |
| H6 confirmada com faixa de preço consistente | Definir planos e pagamento |
| H6 refutada | Reavaliar o modelo (instituições, gratuidade com limites, patrocínio) |
| H7 refutada | Ajustar os termos de cada tema, o filtro de relevância e o limite de avisos |
| Muitos pedidos de e-mail | Escolher um provedor e implementar o e-mail dos alertas |

## 12. O que este teste não mostra
- Não há análise automática de uso no produto (nenhum rastreamento): tudo vem de observação e das respostas.
- Seis pessoas não dão estatística: servem para achar problemas e rejeitar ideias fracas.
- Participantes recrutados na rede da equipe tendem a ser mais gentis. Pelo menos 2 devem ser pessoas sem vínculo pessoal.
- O teste avalia a primeira impressão; o valor dos alertas e das atualizações só aparece depois de dias de uso.

## 13. Cronograma sugerido

| Dia | Atividade |
|---|---|
| 1 a 2 | Escolher e convidar (envio da triagem); fechar os horários; teste completo do ambiente |
| 3 a 7 | Sessões (no máximo 2 por dia, para anotar com calma) |
| 14 | Acompanhamento do 7º dia de alertas por mensagem |
| 15 a 16 | Consolidar, classificar e decidir |

## 14. Mensagem de convite (modelo)

"Olá, [nome]! Estou testando uma ferramenta que ajuda a levantar artigos científicos, avaliar a confiança de cada um e gerar um relatório com método e referências. Preciso de 45 minutos seus, de forma remota, usando **um tema real do seu trabalho** (nada confidencial). Você ia me ajudar muito dizendo o que não funciona. [Compensação, se houver.] Posso marcar?"
