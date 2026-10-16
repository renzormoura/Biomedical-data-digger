# Navegador de artigos — estudo de descoberta

**Status:** proposta para estudo · 2026-10 · nada implementado
**Decisões já tomadas:** leitura "descoberta e leitura" (não embutir páginas de editoras); público amplo (estudantes, professores, pesquisadores e profissionais); sem demanda concreta da faculdade até agora; IA vira camada opcional.

## 1. Hipótese em uma frase (a validar)

> Um lugar para **achar, entender e organizar artigos** em português, que mostra primeiro o que está no registro e no texto do artigo (sem IA) e oferece IA como complemento opcional, é mais útil e mais confiável para quem estuda e trabalha com literatura científica do que um resumidor com IA.

## 2. O risco central: "todos os clientes"

Atender "o máximo de pessoas" é uma meta de alcance, não de produto. Sem um primeiro público definido, o risco é construir algo que não é a melhor escolha de ninguém. A proposta é um **núcleo único** que serve a todos, com um **público de partida** escolhido pela descoberta:

| Núcleo comum (serve a todos) | Entradas por perfil (hipóteses) |
|---|---|
| Buscar → filtrar → abrir o cartão do artigo → organizar → citar | **Estudante:** "achar artigos para o TCC e citar certo" · **Professor:** "montar e compartilhar uma lista de leitura" · **Pesquisador:** "acompanhar um tema e comparar estudos" · **Profissional:** "achar rápido a evidência sobre uma pergunta" |

A descoberta decide qual dessas entradas vem primeiro. Minha aposta inicial, sem dados, é **estudante + professor**, porque o público universitário é o que o projeto já alcança e porque listas de leitura geram uso recorrente. Isso é uma hipótese, não uma conclusão.

## 3. Panorama de ferramentas (a verificar na pesquisa)

Lista de partida para a análise competitiva; os pontos fortes e lacunas abaixo vêm do conhecimento geral e **precisam ser conferidos** ao testar cada uma.

| Ferramenta | Para que serve | Lacuna a investigar |
|---|---|---|
| PubMed / Europe PMC | Busca biomédica de referência | Interface técnica; pouca ajuda para quem começa; pouco português |
| Google Acadêmico | Busca ampla | Poucos filtros, sem organização nem extração |
| SciELO, BVS, Portal de Periódicos CAPES | Literatura em português/ibero-americana e acesso institucional | Experiência de uso e integração entre fontes |
| Semantic Scholar, OpenAlex, Lens | Índices e dados abertos | Voltados a quem já pesquisa; foco em inglês |
| Zotero / Mendeley | Gerenciar referências | Não ajudam a descobrir nem entender o artigo |
| Connected Papers, ResearchRabbit | Explorar relações entre artigos | Curva de aprendizado; pouco foco educacional |
| Elicit, Consensus e similares (IA) | Responder perguntas com IA | Dependem de IA; confiança e custo |

**Pergunta da análise:** onde um estudante brasileiro desiste ou erra usando essas ferramentas?

## 4. Diferenciais candidatos (do mais ao menos promissor, segundo a hipótese)

1. **Listas de leitura compartilháveis** (por professor, por disciplina, por tema), com link para a turma.
2. **Cartão do artigo "sem IA primeiro":** tipo de estudo oficial, resumo organizado, números com a frase de origem, se há versão aberta, citação ABNT/APA/Vancouver. Já existe em grande parte.
3. **Busca em português** (traduzir a consulta e usar descritores DeCS/MeSH) e contexto brasileiro.
4. **Aviso de acesso aberto:** indicar quando existe cópia gratuita legal.
5. **Biblioteca pessoal** com etiquetas e exportação (BibTeX e RIS, sem IA).
6. IA como botão opcional, com as salvaguardas atuais.

## 5. O que já existe e o que falta

| Já existe (reaproveitar) | Novo |
|---|---|
| Busca em 5 fontes e índice de relevância (`article_services`) | Fonte principal por busca, filtros, paginação, ordenação |
| Resolução de PMID/DOI/URL, cache, limites | Página própria por artigo (URL estável) |
| Extração sem IA, tipo de estudo oficial (`extraction`, `europepmc`) | Detecção de acesso aberto (OpenAlex, Europe PMC, Unpaywall) |
| Citações ABNT/APA/Vancouver (`citations`) | Biblioteca do usuário e listas (modelo de dados no PostgreSQL) |
| Contas, sessões, rate limit, registro de uso | Exportação BibTeX/RIS, compartilhamento de listas |

## 6. Riscos técnicos e como tratá-los

| Risco | Tratamento |
|---|---|
| Mesclar 5 fontes dá ranking e paginação confusos | Escolher **uma fonte principal por busca** (OpenAlex para geral, Europe PMC para biomédico) e usar as outras para enriquecer |
| APIs sem garantia de serviço, com limites e regras de uso (identificação educada, e-mail de contato) | Cache, tolerância a falha por fonte, métrica de erros; verificar os termos de cada API antes de depender dela |
| Armazenar dados de usuários | Contas já existem; definir o mínimo de dados e a política de privacidade (LGPD) |
| Direitos autorais | Só metadados, resumos e links; **nunca** hospedar nem fazer proxy de texto completo de editoras |
| Escopo crescer | MVP com corte claro (seção 7) |
| Qualidade da busca percebida pelo usuário | Medir com consultas reais de alunos e professores antes de lançar |

## 7. MVP proposto (para o protótipo)

**Dentro:** busca com filtros (ano, tipo de estudo, acesso aberto, área); resultados em cartões com selos (tipo de estudo, acesso aberto, citações, fonte); página do artigo com resumo organizado, números, citação e botão opcional de IA; salvar em biblioteca com etiquetas; lista compartilhável por link; exportar BibTeX/RIS.

**Fora (por enquanto):** alertas por e-mail, grafo de citações, texto completo, anotações no PDF, recomendações personalizadas, aplicativo móvel nativo.

## 8. Plano de estudo (2 a 4 semanas)

**Semana 1 — Descoberta**
- Entrevistar 5 a 8 pessoas (ao menos 2 de cada perfil). Roteiro na seção 9.
- Fazer a análise competitiva (seção 3) com tarefas reais: "achar 5 artigos recentes sobre X e gerar as referências".

**Semana 2 — Definição**
- Escolher o público de partida e o diferencial em uma frase.
- Fechar o escopo do MVP e os critérios de sucesso.

**Semanas 3 a 4 — Protótipo e teste**
- Protótipo navegável (busca + cartão + biblioteca) sem mexer no app atual.
- Teste com 5 a 8 pessoas, com tarefas cronometradas.

**Critérios de decisão (a combinar antes de testar; valores abaixo são sugestões)**
- A maioria dos participantes completa a tarefa sem ajuda e prefere o protótipo (ou o usa junto) às ferramentas atuais.
- Pelo menos metade salva 3 ou mais artigos na primeira sessão.
- Os participantes citam um motivo claro para voltar.
- Se não, reavaliar o diferencial antes de investir mais.

## 9. Roteiro de entrevista (perguntas abertas)

1. Conte a última vez que você precisou achar artigos. O que fez, passo a passo?
2. Quais ferramentas usa? O que gosta e o que atrapalha em cada uma?
3. Como você decide se um artigo vale a leitura?
4. Como guarda e organiza o que encontra? Já perdeu algum artigo?
5. Como cita e formata referências? Já teve problemas?
6. Já usou IA para ler ou resumir artigos? Confiou? Já viu erros?
7. (Professor) Como indica leituras à turma hoje? O que faltaria para ser mais simples?
8. (Pesquisador/profissional) Como acompanha novidades de um tema?
9. O que faria você trocar sua ferramenta atual por outra?
10. Se pudesse pedir uma coisa, o que seria?

## 10. Perguntas em aberto

- Qual perfil entra primeiro e por quê?
- A faculdade aceita ser parceira no teste (turmas, professores)?
- Qual a política de dados da instituição para contas e listas?
- Há integração desejada com o acesso institucional (Portal de Periódicos CAPES)?
- Qual a meta de uso para considerar a ideia validada?
