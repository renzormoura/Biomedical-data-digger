/* DADOS 100% FICTÍCIOS — criados só para a maquete.
   Nenhum título, autor, periódico, DOI ou número abaixo corresponde a um estudo real. */
(function (root) {
  "use strict";

  const A = (family, given) => ({ family, given });

  root.NAV_DATA = [
    {
      id: "d001", area: "Medicina", type: "Ensaio clínico randomizado", lang: "pt", year: 2023, oa: true, citations: 38,
      title: "Efeito do exercício supervisionado sobre a pressão arterial de adultos com hipertensão leve: ensaio clínico randomizado (exemplo)",
      authors: [A("Moraes Teixeira", "Helena"), A("Bastos", "Ricardo"), A("Lemos", "Paula Cristina")],
      journal: "Revista Exemplo de Cardiologia", volume: "41", issue: "2", pages: "112-124", doi: "10.0000/exemplo.001",
      source: "Exemplo (Europe PMC)", keywords: ["hipertensão", "exercício físico", "pressão arterial", "ensaio clínico"],
      abstract: "Contexto: O exercício físico é recomendado na hipertensão, mas faltam dados sobre programas supervisionados curtos. Métodos: Ensaio clínico randomizado com 240 adultos (n=240) com hipertensão leve, alocados para exercício supervisionado ou cuidado usual por 12 semanas. Resultados: A pressão arterial sistólica caiu 8,4 mmHg no grupo exercício e 2,1 mmHg no controle (diferença -6,3 mmHg; IC 95% -9,1 a -3,5; p<0,001). Eventos adversos leves ocorreram em 4,2% dos participantes. Conclusões: O programa supervisionado reduziu a pressão arterial em comparação ao cuidado usual. Estudos mais longos são necessários.",
    },
    {
      id: "d002", area: "Medicina", type: "Estudo de coorte", lang: "en", year: 2021, oa: false, citations: 112,
      title: "Statin use and incident dementia in adults over 65: a population-based cohort (example)",
      authors: [A("Hartley", "Simon"), A("Okafor", "Chidi"), A("Brandt", "Lena")],
      journal: "Example Journal of Geriatrics", volume: "19", issue: "4", pages: "301-312", doi: "10.0000/exemplo.002",
      source: "Exemplo (OpenAlex)", keywords: ["statins", "dementia", "older adults", "cohort"],
      abstract: "Background: Whether statin therapy changes dementia risk in older adults remains uncertain. Methods: We followed 31,200 adults aged 65 years or older without dementia for a median of 6.1 years. Cox models were adjusted for age, sex, vascular risk factors and baseline cognition. Results: Statin use was associated with a lower risk of incident dementia (HR 0.88; 95% CI 0.80-0.96; p=0.004). The association was weaker in participants over 80 years. Conclusions: Statin use was associated with a modest reduction in dementia risk. Residual confounding cannot be excluded.",
    },
    {
      id: "d003", area: "Saúde Pública", type: "Estudo de casos e controles", lang: "es", year: 2020, oa: false, citations: 6,
      title: "Factores asociados con la mortalidad por una arbovirosis en hospitales de una región (ejemplo)",
      authors: [A("Quintero", "Marta"), A("Villalba", "Jorge")],
      journal: "Revista Ejemplo de Salud Pública", volume: "22", issue: "1", pages: "45-53", doi: "10.0000/exemplo.003",
      source: "Exemplo (SciELO)", keywords: ["arbovirosis", "mortalidad", "casos y controles"],
      abstract: "Objetivo. Identificar factores asociados con la mortalidad por arbovirosis grave en cuatro hospitales. Métodos. Estudio de casos y controles con 62 casos y 130 controles admitidos entre 2015 y 2018. Resultados. La presencia de comorbilidad se asoció con la mortalidad (OR 3,4; IC95% 1,5-7,8), así como la consulta previa por el mismo cuadro (OR 3,9; IC95% 1,6-9,5). Conclusiones. Los factores identificados pueden orientar la vigilancia hospitalaria.",
    },
    {
      id: "d004", area: "Saúde Pública", type: "Revisão sistemática", lang: "pt", year: 2022, oa: true, citations: 21,
      title: "Cobertura vacinal em crianças no Brasil: revisão sistemática (exemplo)",
      authors: [A("Siqueira Neto", "Aline"), A("Duarte", "Fernando"), A("Campos", "Beatriz")],
      journal: "Cadernos Exemplo de Saúde Coletiva", volume: "30", issue: "3", pages: "e2205", doi: "10.0000/exemplo.004",
      source: "Exemplo (SciELO)", keywords: ["vacinação", "cobertura vacinal", "crianças", "Brasil"],
      abstract: "Introdução: A queda da cobertura vacinal preocupa gestores de saúde. Objetivo: Sintetizar estudos sobre cobertura vacinal infantil no Brasil. Métodos: Revisão sistemática com busca em quatro bases; foram incluídos 38 estudos publicados entre 2010 e 2021. Resultados: A cobertura variou de 62,5% a 97,1% entre regiões e vacinas, com as menores taxas em regiões remotas. Conclusão: Há desigualdade regional importante; recomenda-se vigilância ativa nas áreas de menor cobertura.",
    },
    {
      id: "d005", area: "Ambiental", type: "Estudo observacional", lang: "pt", year: 2024, oa: true, citations: 9,
      title: "Concentração de material particulado e internações respiratórias em uma capital brasileira (exemplo)",
      authors: [A("Farias", "Gustavo"), A("Nogueira Lima", "Tatiane")],
      journal: "Revista Exemplo de Ciências Ambientais", volume: "12", issue: "1", pages: "77-90", doi: "10.0000/exemplo.005",
      source: "Exemplo (OpenAlex)", keywords: ["material particulado", "poluição do ar", "internações", "saúde respiratória"],
      abstract: "Objetivo: Estimar a associação entre material particulado fino (PM2,5) e internações respiratórias. Métodos: Série temporal de 2016 a 2021 com 48.300 internações; modelos aditivos generalizados ajustados para temperatura e sazonalidade. Resultados: Cada aumento de 10 µg/m³ de PM2,5 associou-se a 3,2% mais internações no mesmo dia (IC 95% 1,8 a 4,6; p<0,001). Conclusão: A exposição a PM2,5 aumentou as internações respiratórias; as concentrações excederam o valor de referência em 27% dos dias.",
    },
    {
      id: "d006", area: "Ambiental", type: "Estudo experimental", lang: "en", year: 2019, oa: false, citations: 64,
      title: "Biochar amendment reduces nitrate leaching in tropical soils: a field experiment (example)",
      authors: [A("Mendes", "Rafael"), A("Ibrahim", "Salma"), A("Costa Ribeiro", "Marcos")],
      journal: "Example Journal of Soil and Environment", volume: "8", issue: "3", pages: "201-214", doi: "10.0000/exemplo.006",
      source: "Exemplo (Crossref)", keywords: ["biochar", "nitrate", "soil", "tropical agriculture"],
      abstract: "Background: Nitrate leaching degrades groundwater quality in tropical agriculture. Methods: A two-year field experiment compared biochar at 0, 10 and 20 t/ha in 36 plots. Results: Nitrate leaching decreased by 22% at 10 t/ha and 35% at 20 t/ha relative to control (p<0.01), with no yield penalty. Conclusions: Biochar reduced nitrate losses under the tested conditions; long-term effects remain unknown.",
    },
    {
      id: "d007", area: "Tecnologia e IA", type: "Preprint", lang: "en", year: 2024, oa: true, citations: 17,
      title: "A lightweight transformer for clinical text classification with limited labels (example)",
      authors: [A("Varga", "Nora"), A("Ito", "Kenji"), A("Pereira", "Lucas")],
      journal: "Preprint Server Example", volume: "", issue: "", pages: "", doi: "10.0000/exemplo.007",
      source: "Exemplo (arXiv)", keywords: ["transformer", "text classification", "clinical notes", "few-shot"],
      abstract: "We propose a lightweight transformer for classifying clinical notes when only a few hundred labeled examples are available. On three public benchmarks, our model reached a macro-F1 of 0.81, compared with 0.78 for the strongest baseline, using 60% fewer parameters. Ablation studies show that contrastive pretraining contributes most of the gain (p<0.05). Code and data splits are not yet released.",
    },
    {
      id: "d008", area: "Tecnologia e IA", type: "Revisão", lang: "en", year: 2022, oa: true, citations: 55,
      title: "Reproducibility of machine learning studies in healthcare: a meta-research survey (example)",
      authors: [A("Okonkwo", "Ada"), A("Lindqvist", "Erik")],
      journal: "Example Journal of Biomedical Informatics", volume: "7", issue: "2", pages: "88-101", doi: "10.0000/exemplo.008",
      source: "Exemplo (Semantic Scholar)", keywords: ["reproducibility", "machine learning", "healthcare", "open science"],
      abstract: "Background: Reproducibility is a concern in clinical machine learning. Methods: We screened 410 published studies and checked code, data and protocol availability. Results: Only 19% shared code and 8% shared data; 46% reported enough detail to attempt replication. Conclusions: Reporting standards and data sharing practices need to improve.",
    },
    {
      id: "d009", area: "Engenharias", type: "Estudo experimental", lang: "pt", year: 2021, oa: false, citations: 14,
      title: "Desempenho de concreto com substituição parcial de cimento por cinza de casca de arroz (exemplo)",
      authors: [A("Barreto", "Wesley"), A("Machado", "Sílvia"), A("Andrade Filho", "Otávio")],
      journal: "Revista Exemplo de Engenharia Civil", volume: "15", issue: "4", pages: "233-245", doi: "10.0000/exemplo.009",
      source: "Exemplo (Crossref)", keywords: ["concreto", "cinza de casca de arroz", "resistência à compressão", "sustentabilidade"],
      abstract: "Objetivo: Avaliar a resistência à compressão de concretos com 0%, 10% e 20% de substituição de cimento por cinza de casca de arroz. Métodos: Foram moldados 90 corpos de prova ensaiados aos 7, 28 e 90 dias conforme norma técnica. Resultados: Aos 28 dias, a mistura com 10% atingiu 38,2 MPa, contra 36,5 MPa do concreto de referência; com 20% houve queda para 31,9 MPa. Conclusão: A substituição de até 10% manteve ou melhorou a resistência; o efeito sobre a durabilidade não foi avaliado.",
    },
    {
      id: "d010", area: "Engenharias", type: "Estudo de modelagem", lang: "en", year: 2023, oa: true, citations: 29,
      title: "Optimal sizing of photovoltaic-battery systems for rural microgrids (example)",
      authors: [A("Alvarez", "Diego"), A("Nakamura", "Yui")],
      journal: "Example Journal of Energy Systems", volume: "11", issue: "1", pages: "15-31", doi: "10.0000/exemplo.010",
      source: "Exemplo (OpenAlex)", keywords: ["photovoltaic", "battery storage", "microgrid", "optimization"],
      abstract: "Background: Rural microgrids need reliable and affordable sizing methods. Methods: We formulated a mixed-integer optimization model validated with one year of load data from 14 villages. Results: The optimal configurations reduced the levelized cost of energy by 17.5% compared with rule-of-thumb sizing, while keeping loss of power supply probability below 2%. Conclusions: Optimization-based sizing lowered cost; results depend on local solar resource data.",
    },
    {
      id: "d011", area: "Educação", type: "Revisão de escopo", lang: "pt", year: 2022, oa: true, citations: 33,
      title: "Metodologias ativas e desempenho acadêmico no ensino superior: revisão de escopo (exemplo)",
      authors: [A("Rocha", "Camila"), A("Vieira Santos", "Eduardo")],
      journal: "Revista Exemplo de Educação Superior", volume: "9", issue: "2", pages: "140-158", doi: "10.0000/exemplo.011",
      source: "Exemplo (SciELO)", keywords: ["metodologias ativas", "ensino superior", "aprendizagem", "revisão de escopo"],
      abstract: "Introdução: Metodologias ativas são adotadas em cursos de graduação, mas as evidências sobre desempenho são heterogêneas. Métodos: Revisão de escopo de 52 estudos publicados entre 2012 e 2021. Resultados: 71% dos estudos relataram melhora do desempenho ou do engajamento, porém apenas 12 usaram grupo comparação. Conclusão: Há indícios favoráveis, com qualidade metodológica limitada.",
    },
    {
      id: "d012", area: "Medicina", type: "Meta-análise", lang: "en", year: 2020, oa: true, citations: 140,
      title: "Metformin and cardiovascular outcomes in type 2 diabetes: a meta-analysis of randomized trials (example)",
      authors: [A("Weber", "Anika"), A("Suzuki", "Hiro"), A("Oliveira Prado", "Marina"), A("Clarke", "James")],
      journal: "Example Journal of Diabetes Research", volume: "27", issue: "5", pages: "890-903", doi: "10.0000/exemplo.012",
      source: "Exemplo (Europe PMC)", keywords: ["metformin", "type 2 diabetes", "cardiovascular", "meta-analysis"],
      abstract: "Background: The cardiovascular effect of metformin is debated. Methods: We pooled 14 randomized trials including 18,450 participants (n=18,450) and used random-effects models. Results: Metformin was associated with a lower risk of major cardiovascular events (RR 0.89; 95% CI 0.81-0.98; p=0.02), with moderate heterogeneity (I2=41%). Gastrointestinal adverse events were more frequent (12.4% vs 6.9%). Conclusions: Metformin was associated with a modest reduction in cardiovascular events in trials of type 2 diabetes.",
    },
    {
      id: "d013", area: "Medicina", type: "Relato de caso", lang: "pt", year: 2018, oa: false, citations: 2,
      title: "Hipoglicemia grave associada à interação medicamentosa: relato de caso (exemplo)",
      authors: [A("Pacheco", "Daniela"), A("Freitas", "Lucas")],
      journal: "Revista Exemplo de Medicina de Urgência", volume: "6", issue: "1", pages: "22-26", doi: "10.0000/exemplo.013",
      source: "Exemplo (Crossref)", keywords: ["hipoglicemia", "interação medicamentosa", "urgência"],
      abstract: "Apresentamos o caso de uma paciente de 74 anos com diabetes tipo 2 em uso de glibenclamida 10 mg ao dia que evoluiu com hipoglicemia grave após início de um antibiótico. Houve interação medicamentosa provável com aumento do efeito hipoglicemiante. A paciente recebeu glicose intravenosa e permaneceu em observação por 48 horas. Os autores recomendam revisar as associações medicamentosas em idosos diabéticos. Relato de um único caso; não é possível generalizar.",
    },
    {
      id: "d014", area: "Psicologia", type: "Estudo transversal", lang: "pt", year: 2023, oa: true, citations: 12,
      title: "Sintomas de ansiedade em universitários após a pandemia: estudo transversal (exemplo)",
      authors: [A("Lopes", "Raquel"), A("Dantas", "Vinícius"), A("Ferraz", "Isabela")],
      journal: "Revista Exemplo de Psicologia da Saúde", volume: "14", issue: "3", pages: "301-314", doi: "10.0000/exemplo.014",
      source: "Exemplo (SciELO)", keywords: ["ansiedade", "universitários", "saúde mental", "pandemia"],
      abstract: "Objetivo: Estimar a prevalência de sintomas de ansiedade em estudantes universitários. Métodos: Estudo transversal com 1.850 estudantes (n=1.850) de seis cursos, usando escala validada. Resultados: A prevalência de sintomas moderados a graves foi de 34,6% (IC 95% 32,4 a 36,8), maior entre mulheres (razão de prevalência 1,4; p<0,001). Conclusão: A prevalência foi elevada; são necessários serviços de apoio no campus.",
    },
  ];

  root.NAV_PERSONAS = [
    { id: "estudante", title: "Sou estudante", hint: "Preciso achar artigos para o meu TCC e citar certo.", q: "diabetes", task: "Achar artigos recentes e gerar as referências em ABNT." },
    { id: "professor", title: "Sou professor", hint: "Quero montar uma lista de leitura para a minha turma.", q: "saúde pública", task: "Criar uma lista e compartilhar o link." },
    { id: "pesquisador", title: "Sou pesquisador", hint: "Quero comparar estudos e ver a qualidade da evidência.", q: "ensaio clínico", task: "Filtrar por tipo de estudo e comparar números." },
    { id: "profissional", title: "Sou profissional", hint: "Preciso achar rápido a evidência sobre uma pergunta.", q: "hipoglicemia", task: "Achar o estudo certo e ler o essencial em um minuto." },
  ];
})(typeof self !== "undefined" ? self : globalThis);
