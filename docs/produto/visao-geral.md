# Visão geral do produto

## O que é
Biomedical Data Digger é uma plataforma web que ajuda pessoas a **encontrar, entender, acompanhar e entregar** pesquisa científica. Ela reúne fontes abertas numa única busca, mostra com critérios abertos o quanto cada artigo merece confiança, avisa quando sai algo novo sobre os temas de interesse e transforma as leituras em listas, relatórios e referências.

O núcleo serve **qualquer área do conhecimento**. Para quem trabalha com saúde no Brasil, há um **pacote opcional** que cruza os medicamentos citados nos artigos com dados oficiais brasileiros (ANVISA, Conitec e Rename).

## Para quem
| Público | Uso típico |
|---|---|
| Estudantes | Achar artigos para TCC e dissertações, entender o resumo, citar no formato certo (ABNT, APA…), montar referencial com método declarado |
| Professores | Montar listas de leitura e compartilhar com a turma por link |
| Pesquisadores | Acompanhar a literatura, ver tipo de evidência, levar referências para Zotero, Mendeley ou EndNote |
| Profissionais de saúde e farmácia | Evidência sobre uma pergunta, situação do medicamento no Brasil, aviso de artigo retratado |
| Consultorias | Relatório de tema com método e histórico para entregar a clientes, atualizado quando sai artigo novo |

## O que o produto faz
1. **Descobrir.** Busca única em Europe PMC, PubMed, arXiv, DOAJ e OpenAIRE (OpenAlex quando há chave), sem repetir o mesmo artigo; feed de novidades de 51 fontes curadas em 14 áreas; artigos semelhantes.
2. **Entender.** Resumo dividido por seções, números e estatísticas copiados do resumo com a frase de origem, nota de confiabilidade de 0 a 100 com 8 critérios abertos, panorama do tema, registros abertos (ensaios, citações, dados).
3. **Acompanhar.** Interesses por área, subtema, idioma e palavras-chave; avisos no sininho de artigo novo, artigo retratado que a pessoa guarda, mudança regulatória de substâncias acompanhadas e novidades nos relatórios.
4. **Organizar e entregar.** Biblioteca com etiquetas, listas de leitura (com link público somente leitura), relatório de tema com versões e histórico, citações em 6 estilos e exportação para gerenciadores.
5. **Opcional: Laboratório de IA.** 16 áreas de análise geradas por modelo de linguagem, sempre rotuladas, com cota diária. Nada do restante depende dele.

## Princípios de produto
- **Sem IA primeiro.** Tudo o que sustenta confiança (resumo, números, nota, citações, relatórios) é copiado ou calculado de dados do registro, sem geração de texto. IA é camada opcional e separada.
- **Critérios abertos.** A nota mostra o cálculo: o que contou, o que faltou e a evidência usada. Dado ausente na fonte não pune o artigo; reduz a cobertura da nota.
- **Limites declarados.** A nota mede sinais verificáveis no registro e no resumo; não mede execução do estudo nem substitui leitura crítica. Isso aparece na interface e nos relatórios.
- **Fonte sempre citada.** Cada dado traz a origem e, quando aplicável, a data da base.
- **Privacidade por padrão.** Buscar e ler não exige conta; dados da conta podem ser baixados e excluídos pela própria pessoa.
- **Notícia não é nota.** O feed identifica o tipo de cada fonte (instituição, revista, preprint…), mas comunicados e notícias não passam pela nota dos artigos.

## O que o produto não faz
- Não dá conselho clínico, jurídico ou financeiro, nem decide por conduta.
- Não avalia risco de viés nem a validade clínica de um estudo.
- Não armazena nem republica texto completo de artigos: oferece o texto completo apenas quando a fonte o disponibiliza em acesso aberto.
- Não copia textos de notícias: o feed mostra título, trecho curto (até 300 caracteres) e link para a fonte.

## Mapa de módulos do produto
```
                      ┌─────────────────────────────────────────────┐
  Descobrir ─────────▶│ Busca · Feed · Semelhantes · Panorama       │
                      ├─────────────────────────────────────────────┤
  Entender  ─────────▶│ Página do artigo · Nota · Registros abertos │
                      │ Saúde no Brasil (opcional)                  │
                      ├─────────────────────────────────────────────┤
  Acompanhar ────────▶│ Interesses · Alertas · Sininho              │
                      ├─────────────────────────────────────────────┤
  Entregar  ─────────▶│ Biblioteca · Listas · Relatório · Citações  │
                      ├─────────────────────────────────────────────┤
  Opcional  ─────────▶│ Laboratório de IA                           │
                      └─────────────────────────────────────────────┘
```

## Estado atual
Em operação no Render (web service Python) com PostgreSQL em produção e SQLite em desenvolvimento. A validação do caminho PostgreSQL para todas as tabelas novas ainda está pendente (ver [Roadmap](../roadmap/roadmap.md)). A rotina agendada de alertas está preparada, mas depende da configuração dos segredos (ver [Rotinas agendadas](../operacao/rotinas-agendadas.md)).

## Documentos relacionados
[Guia do usuário](guia-do-usuario.md) · [Funcionalidades](../README.md#funcionalidades) · [Arquitetura](../arquitetura/visao-geral.md) · [Licenças e termos](../legal/licencas-e-termos.md)
