"""Lista curada das fontes do feed de novidades academicas.

So entram fontes que (1) oferecem feed publico para quem quer redistribuir manchetes, (2) tratam de ciencia, pesquisa ou ensino
superior e (3) foram verificadas funcionando em 2026-10-18 (titulo, link e data em cada item). O feed mostra apenas titulo,
um trecho curto e o link: quem clica vai para o site da fonte. Nenhuma imagem e nenhum texto completo sao copiados.

O nivel da fonte (`tier`) NAO e uma nota de confiabilidade de cada noticia: diz que tipo de fonte e (instituicao, revista,
preprint, divulgacao cientifica ou jornal) para a pessoa julgar. Noticias nao passam pela nota dos artigos.

Para acrescentar uma fonte: confira o feed com `scripts/verificar_feeds.py`, escolha o nivel e as areas (chaves de `interests.py`;
vazio = serve a qualquer area) e registre aqui.
"""

from __future__ import annotations

from dataclasses import dataclass

# nivel -> (rotulo curto, descricao para a pessoa)
TIERS: dict[str, tuple[str, str]] = {
    "instituicao": ("Instituição", "Instituição de pesquisa, universidade ou órgão público de saúde."),
    "revista": ("Revista", "Revista científica; o feed pode trazer artigos e notícias da própria revista."),
    "preprint": ("Preprint", "Trabalho ainda sem revisão por pares."),
    "divulgacao": ("Divulgação científica", "Divulgação de pesquisas e comunicados de imprensa de instituições."),
    "jornal": ("Jornal", "Imprensa geral; reportagens que passam pela redação do jornal. Só entram as que citam pesquisa ou ciência."),
    "blog": ("Blog acadêmico", "Análises de pesquisadores publicadas em blogs de revistas e universidades; não passam por revisão por pares."),
}


@dataclass(frozen=True)
class Source:
    id: str
    name: str
    url: str  # endereco do feed
    site: str  # pagina inicial, para atribuicao
    language: str  # pt, en
    tier: str
    areas: tuple[str, ...] = ()  # chaves de area de interests.py; vazio = qualquer area
    max_items: int = 40  # itens mais recentes guardados por busca (alguns feeds trazem milhares)
    undated: bool = False  # o feed nao informa datas (ex.: NBER); os itens usam o horario em que foram vistos


SOURCES: tuple[Source, ...] = (
    # ---- saude (pt)
    Source("fiocruz", "Agência Fiocruz de Notícias", "https://agencia.fiocruz.br/rss.xml", "https://agencia.fiocruz.br/", "pt", "instituicao", ("medicina", "farmacia", "biologia", "enfermagem")),
    Source("opas", "OPAS/OMS (português)", "https://www.paho.org/pt/rss.xml", "https://www.paho.org/pt", "pt", "instituicao", ("medicina", "enfermagem")),
    Source("agencia-brasil-saude", "Agência Brasil: Saúde", "https://agenciabrasil.ebc.com.br/rss/saude/feed.xml", "https://agenciabrasil.ebc.com.br/saude", "pt", "jornal", ("medicina", "farmacia", "enfermagem", "nutricao")),
    Source("folha-saude", "Folha de S.Paulo: Equilíbrio e Saúde", "https://feeds.folha.uol.com.br/equilibrioesaude/rss091.xml", "https://www1.folha.uol.com.br/equilibrioesaude/", "pt", "jornal", ("medicina", "nutricao", "psicologia")),
    Source("g1-ciencia-saude", "G1: Ciência e Saúde", "https://g1.globo.com/rss/g1/ciencia-e-saude/", "https://g1.globo.com/ciencia-e-saude/", "pt", "jornal", ("medicina", "biologia", "ambiente")),
    # ---- saude (en)
    Source("oms", "Organização Mundial da Saúde", "https://www.who.int/rss-feeds/news-english.xml", "https://www.who.int/news", "en", "instituicao", ("medicina",)),
    Source("cdc-mmwr", "CDC: Morbidity and Mortality Weekly Report", "https://tools.cdc.gov/api/v2/resources/media/342778.rss", "https://www.cdc.gov/mmwr/", "en", "instituicao", ("medicina",), max_items=30),
    Source("bmj", "The BMJ", "https://www.bmj.com/rss/recent.xml", "https://www.bmj.com/", "en", "revista", ("medicina",)),
    Source("jama", "JAMA Network", "https://jamanetwork.com/rss/site_3/67.xml", "https://jamanetwork.com/", "en", "revista", ("medicina",)),
    Source("plos-medicine", "PLOS Medicine", "https://journals.plos.org/plosmedicine/feed/atom", "https://journals.plos.org/plosmedicine/", "en", "revista", ("medicina",)),
    Source("medrxiv", "medRxiv (preprints)", "https://connect.medrxiv.org/medrxiv_xml.php?subject=all", "https://www.medrxiv.org/", "en", "preprint", ("medicina",)),
    Source("sciencedaily-saude", "ScienceDaily: Saúde", "https://www.sciencedaily.com/rss/top/health.xml", "https://www.sciencedaily.com/news/health_medicine/", "en", "divulgacao", ("medicina", "nutricao", "enfermagem")),
    Source("medicalxpress", "Medical Xpress", "https://medicalxpress.com/rss-feed/", "https://medicalxpress.com/", "en", "divulgacao", ("medicina", "farmacia", "odontologia")),
    # ---- ciencia em geral (pt)
    Source("pesquisa-fapesp", "Revista Pesquisa FAPESP", "https://revistapesquisa.fapesp.br/feed/", "https://revistapesquisa.fapesp.br/", "pt", "divulgacao"),
    Source("jornal-usp", "Jornal da USP", "https://jornal.usp.br/feed/", "https://jornal.usp.br/", "pt", "instituicao"),
    Source("conversation-br", "The Conversation Brasil", "https://theconversation.com/br/articles.atom", "https://theconversation.com/br", "pt", "divulgacao"),
    Source("folha-ciencia", "Folha de S.Paulo: Ciência", "https://feeds.folha.uol.com.br/ciencia/rss091.xml", "https://www1.folha.uol.com.br/ciencia/", "pt", "jornal"),
    # ---- ciencia em geral (en)
    Source("conversation", "The Conversation (global)", "https://theconversation.com/global/articles.atom", "https://theconversation.com/global", "en", "divulgacao"),
    Source("nature", "Nature", "https://www.nature.com/nature.rss", "https://www.nature.com/nature/", "en", "revista", max_items=40),
    Source("plos-one", "PLOS ONE", "https://journals.plos.org/plosone/feed/atom", "https://journals.plos.org/plosone/", "en", "revista"),
    Source("elife", "eLife", "https://elifesciences.org/rss/recent.xml", "https://elifesciences.org/", "en", "revista", ("biologia", "medicina", "psicologia")),
    Source("biorxiv", "bioRxiv (preprints)", "https://connect.biorxiv.org/biorxiv_xml.php?subject=all", "https://www.biorxiv.org/", "en", "preprint", ("biologia",)),
    # ---- engenharia, computacao e exatas
    Source("mit-news", "MIT News", "https://news.mit.edu/rss/feed", "https://news.mit.edu/", "en", "instituicao", ("engenharia", "computacao", "exatas", "biologia")),
    Source("ieee-spectrum", "IEEE Spectrum", "https://spectrum.ieee.org/feeds/feed.rss", "https://spectrum.ieee.org/", "en", "revista", ("engenharia", "computacao")),
    Source("techxplore", "Tech Xplore", "https://techxplore.com/rss-feed/", "https://techxplore.com/", "en", "divulgacao", ("engenharia", "computacao")),
    Source("sciencedaily-computacao", "ScienceDaily: Computação e Matemática", "https://www.sciencedaily.com/rss/computers_math.xml", "https://www.sciencedaily.com/news/computers_math/", "en", "divulgacao", ("computacao", "exatas")),
    Source("sciencedaily-materia", "ScienceDaily: Matéria e Energia", "https://www.sciencedaily.com/rss/matter_energy.xml", "https://www.sciencedaily.com/news/matter_energy/", "en", "divulgacao", ("exatas", "engenharia")),
    Source("phys-org", "Phys.org", "https://phys.org/rss-feed/", "https://phys.org/", "en", "divulgacao", ("exatas", "engenharia")),
    Source("quanta", "Quanta Magazine", "https://api.quantamagazine.org/feed/", "https://www.quantamagazine.org/", "en", "divulgacao", ("exatas", "computacao")),
    # ---- ambiente e terra
    Source("sciencedaily-ambiente", "ScienceDaily: Meio ambiente", "https://www.sciencedaily.com/rss/earth_climate.xml", "https://www.sciencedaily.com/news/earth_climate/", "en", "divulgacao", ("ambiente", "agrarias")),
    Source("eos", "Eos (AGU)", "https://eos.org/feed", "https://eos.org/", "en", "divulgacao", ("ambiente",)),
    Source("carbon-brief", "Carbon Brief", "https://www.carbonbrief.org/feed/", "https://www.carbonbrief.org/", "en", "divulgacao", ("ambiente",)),
    # ---- mente, sociedade e educacao
    Source("sciencedaily-mente", "ScienceDaily: Mente e cérebro", "https://www.sciencedaily.com/rss/mind_brain.xml", "https://www.sciencedaily.com/news/mind_brain/", "en", "divulgacao", ("psicologia",)),
    Source("sciencedaily-sociedade", "ScienceDaily: Sociedade", "https://www.sciencedaily.com/rss/science_society.xml", "https://www.sciencedaily.com/news/science_society/", "en", "divulgacao", ("sociais", "educacao")),
    Source("agencia-brasil-educacao", "Agência Brasil: Educação", "https://agenciabrasil.ebc.com.br/rss/educacao/feed.xml", "https://agenciabrasil.ebc.com.br/educacao", "pt", "jornal", ("educacao",)),
    Source("g1-educacao", "G1: Educação", "https://g1.globo.com/rss/g1/educacao/", "https://g1.globo.com/educacao/", "pt", "jornal", ("educacao",)),
    # ---- ciencias agrarias
    Source("sciencedaily-agricultura", "ScienceDaily: Agricultura e alimentos", "https://www.sciencedaily.com/rss/plants_animals/agriculture_and_food.xml", "https://www.sciencedaily.com/news/plants_animals/agriculture_and_food/", "en", "divulgacao", ("agrarias",)),
    Source("sciencedaily-plantas", "ScienceDaily: Plantas e animais", "https://www.sciencedaily.com/rss/plants_animals.xml", "https://www.sciencedaily.com/news/plants_animals/", "en", "divulgacao", ("agrarias", "biologia", "ambiente")),
    Source("phys-plantas", "Phys.org: Plantas e animais", "https://phys.org/rss-feed/biology-news/plants-animals/", "https://phys.org/biology-news/plants-animals/", "en", "divulgacao", ("agrarias", "biologia")),
    Source("mongabay", "Mongabay", "https://news.mongabay.com/feed/", "https://news.mongabay.com/", "en", "jornal", ("ambiente", "agrarias")),
    Source("agencia-brasil-ambiente", "Agência Brasil: Meio ambiente", "https://agenciabrasil.ebc.com.br/rss/meio-ambiente/feed.xml", "https://agenciabrasil.ebc.com.br/meio-ambiente", "pt", "jornal", ("ambiente", "agrarias")),
    # ---- direito (area "sociais")
    Source("verfassungsblog", "Verfassungsblog", "https://verfassungsblog.de/feed/", "https://verfassungsblog.de/", "en", "blog", ("sociais",)),
    Source("ejil-talk", "EJIL: Talk!", "https://www.ejiltalk.org/feed/", "https://www.ejiltalk.org/", "en", "blog", ("sociais",)),
    Source("ohrh", "Oxford Human Rights Hub", "https://ohrh.law.ox.ac.uk/feed/", "https://ohrh.law.ox.ac.uk/", "en", "blog", ("sociais",)),
    # ---- economia (area "sociais")
    Source("voxeu", "VoxEU (CEPR)", "https://cepr.org/rss/vox-content", "https://cepr.org/voxeu", "en", "blog", ("sociais",)),
    Source("nber", "NBER: novos working papers", "https://www.nber.org/rss/new.xml", "https://www.nber.org/papers", "en", "preprint", ("sociais",), undated=True),
    Source("ipea", "Ipea", "https://www.ipea.gov.br/portal/index.php?option=com_content&view=category&layout=blog&id=2&Itemid=3&format=feed&type=rss", "https://www.ipea.gov.br/portal/", "pt", "instituicao", ("sociais",)),
    Source("owid", "Our World in Data", "https://ourworldindata.org/atom.xml", "https://ourworldindata.org/", "en", "instituicao"),
    Source("agencia-brasil-economia", "Agência Brasil: Economia", "https://agenciabrasil.ebc.com.br/rss/economia/feed.xml", "https://agenciabrasil.ebc.com.br/economia", "pt", "jornal", ("sociais",)),
    # ---- comunicacao cientifica e universidades (qualquer area)
    Source("scielo", "SciELO em Perspectiva", "https://blog.scielo.org/feed/", "https://blog.scielo.org/", "pt", "blog"),
    Source("jornal-unesp", "Jornal da Unesp", "https://jornal.unesp.br/feed/", "https://jornal.unesp.br/", "pt", "instituicao"),
)

SOURCE_BY_ID: dict[str, Source] = {source.id: source for source in SOURCES}
# tiers cujo conteudo tende a ser pesquisa (artigo ou preprint); os demais sao noticias
ARTICLE_TIERS = frozenset({"revista", "preprint"})
