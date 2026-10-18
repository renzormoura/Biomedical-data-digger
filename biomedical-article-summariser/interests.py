"""Areas do conhecimento, subtemas e idiomas que o usuario pode acompanhar, e a validacao das preferencias.

Cada tema carrega a consulta usada para procurar artigos novos: termos em ingles (a maioria dos indices bibliograficos
indexa titulo e resumo em ingles) e, quando o usuario pede artigos em portugues, termos em portugues. A escolha de um
subtema usa so a consulta do subtema; uma area sem subtemas usa a consulta da area.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from domain import DiggerError

MAX_TOPICS = 15  # areas sem subtema + subtemas escolhidos
MAX_LANGUAGES = 4
MAX_TERMS = 5
MAX_TERM_CHARS = 60

LANGUAGES = (
    ("pt", "Português"), ("en", "Inglês"), ("es", "Espanhol"), ("fr", "Francês"),
    ("de", "Alemão"), ("it", "Italiano"), ("zh", "Chinês"), ("ja", "Japonês"),
)

# (chave, rotulo, consulta em ingles, consulta em portugues)
_Sub = tuple[str, str, str, str]
_AREAS: tuple[tuple[str, str, str, str, tuple[_Sub, ...]], ...] = (
    ("medicina", "Medicina", "medicine clinical", "medicina clínica", (
        ("pediatria", "Pediatria", "pediatrics", "pediatria"),
        ("oncologia", "Oncologia", "oncology cancer", "oncologia câncer"),
        ("cardiologia", "Cardiologia", "cardiology", "cardiologia"),
        ("neurologia", "Neurologia", "neurology", "neurologia"),
        ("psiquiatria", "Psiquiatria", "psychiatry", "psiquiatria"),
        ("infectologia", "Infectologia", "infectious disease", "doenças infecciosas"),
        ("endocrinologia", "Endocrinologia e diabetes", "endocrinology diabetes", "endocrinologia diabetes"),
        ("ginecologia", "Ginecologia e obstetrícia", "obstetrics gynecology", "obstetrícia ginecologia"),
        ("geriatria", "Geriatria", "geriatrics older adults", "geriatria idosos"),
        ("ortopedia", "Ortopedia", "orthopedics", "ortopedia"),
        ("dermatologia", "Dermatologia", "dermatology", "dermatologia"),
        ("saude-publica", "Saúde pública", "public health", "saúde pública"),
        ("emergencia", "Emergência e terapia intensiva", "critical care emergency", "terapia intensiva emergência"),
        ("anestesia", "Anestesiologia", "anesthesiology", "anestesiologia"),
    )),
    ("farmacia", "Farmácia e farmacologia", "pharmacology pharmacy", "farmacologia farmácia", (
        ("farmacologia-clinica", "Farmacologia clínica", "clinical pharmacology", "farmacologia clínica"),
        ("farmacovigilancia", "Farmacovigilância", "pharmacovigilance adverse drug reactions", "farmacovigilância"),
        ("farmacia-hospitalar", "Farmácia hospitalar", "hospital pharmacy", "farmácia hospitalar"),
        ("fitoterapia", "Fitoterapia", "herbal medicine phytotherapy", "fitoterapia"),
        ("medicamentos-biologicos", "Medicamentos biológicos", "biologic drugs biosimilars", "medicamentos biológicos"),
    )),
    ("enfermagem", "Enfermagem", "nursing", "enfermagem", (
        ("cuidado-critico", "Cuidado crítico", "critical care nursing", "enfermagem intensiva"),
        ("saude-mulher", "Saúde da mulher e da criança", "maternal child nursing", "enfermagem materno-infantil"),
        ("seguranca-paciente", "Segurança do paciente", "patient safety", "segurança do paciente"),
    )),
    ("odontologia", "Odontologia", "dentistry oral health", "odontologia saúde bucal", (
        ("endodontia", "Endodontia", "endodontics", "endodontia"),
        ("ortodontia", "Ortodontia", "orthodontics", "ortodontia"),
        ("periodontia", "Periodontia", "periodontology", "periodontia"),
    )),
    ("nutricao", "Nutrição e educação física", "nutrition exercise", "nutrição exercício físico", (
        ("nutricao-clinica", "Nutrição clínica", "clinical nutrition", "nutrição clínica"),
        ("esporte", "Ciências do esporte", "sports science", "ciências do esporte"),
        ("obesidade", "Obesidade", "obesity", "obesidade"),
    )),
    ("biologia", "Biologia e biotecnologia", "biology biotechnology", "biologia biotecnologia", (
        ("genetica", "Genética e genômica", "genetics genomics", "genética genômica"),
        ("microbiologia", "Microbiologia", "microbiology", "microbiologia"),
        ("imunologia", "Imunologia", "immunology", "imunologia"),
        ("bioinformatica", "Bioinformática", "bioinformatics", "bioinformática"),
        ("ecologia", "Ecologia", "ecology", "ecologia"),
    )),
    ("psicologia", "Psicologia e neurociência", "psychology neuroscience", "psicologia neurociência", (
        ("psicologia-clinica", "Psicologia clínica", "clinical psychology", "psicologia clínica"),
        ("neurociencia-cognitiva", "Neurociência cognitiva", "cognitive neuroscience", "neurociência cognitiva"),
        ("desenvolvimento", "Desenvolvimento humano", "developmental psychology", "psicologia do desenvolvimento"),
    )),
    ("computacao", "Computação e IA", "computer science artificial intelligence", "ciência da computação inteligência artificial", (
        ("aprendizado-maquina", "Aprendizado de máquina", "machine learning", "aprendizado de máquina"),
        ("llm", "Modelos de linguagem", "large language models", "modelos de linguagem"),
        ("seguranca-informacao", "Segurança da informação", "cybersecurity", "segurança da informação"),
        ("saude-digital", "Saúde digital", "digital health artificial intelligence medicine", "saúde digital"),
        ("engenharia-software", "Engenharia de software", "software engineering", "engenharia de software"),
    )),
    ("engenharia", "Engenharias e tecnologia", "engineering technology", "engenharia tecnologia", (
        ("materiais", "Ciência dos materiais", "materials science", "ciência dos materiais"),
        ("energia", "Energia", "energy renewable", "energia renovável"),
        ("civil", "Engenharia civil", "civil engineering", "engenharia civil"),
        ("eletrica", "Engenharia elétrica e eletrônica", "electrical engineering electronics", "engenharia elétrica"),
        ("biomedica", "Engenharia biomédica", "biomedical engineering", "engenharia biomédica"),
    )),
    ("exatas", "Física, química e matemática", "physics chemistry mathematics", "física química matemática", (
        ("fisica", "Física", "physics", "física"),
        ("quimica", "Química", "chemistry", "química"),
        ("matematica", "Matemática e estatística", "mathematics statistics", "matemática estatística"),
        ("astronomia", "Astronomia", "astronomy astrophysics", "astronomia"),
    )),
    ("ambiente", "Meio ambiente e ciências da Terra", "environmental science earth", "meio ambiente ciências da Terra", (
        ("clima", "Mudanças climáticas", "climate change", "mudanças climáticas"),
        ("geologia", "Geologia", "geology", "geologia"),
        ("biodiversidade", "Biodiversidade", "biodiversity conservation", "biodiversidade conservação"),
        ("recursos-hidricos", "Recursos hídricos", "water resources", "recursos hídricos"),
    )),
    ("agrarias", "Ciências agrárias e veterinária", "agriculture veterinary", "agronomia veterinária", (
        ("agronomia", "Agronomia", "agronomy crops", "agronomia"),
        ("veterinaria", "Medicina veterinária", "veterinary medicine", "medicina veterinária"),
        ("zootecnia", "Zootecnia", "animal science livestock", "zootecnia"),
        ("alimentos", "Ciência de alimentos", "food science", "ciência de alimentos"),
    )),
    ("sociais", "Ciências sociais e humanas", "social sciences humanities", "ciências sociais humanas", (
        ("sociologia", "Sociologia", "sociology", "sociologia"),
        ("economia", "Economia", "economics", "economia"),
        ("direito", "Direito", "law legal studies", "direito"),
        ("politicas-publicas", "Políticas públicas", "public policy", "políticas públicas"),
        ("historia", "História", "history", "história"),
    )),
    ("educacao", "Educação", "education", "educação", (
        ("educacao-superior", "Ensino superior", "higher education", "ensino superior"),
        ("educacao-medica", "Educação em saúde", "medical education health professions education", "educação em saúde"),
        ("tecnologia-educacional", "Tecnologia educacional", "educational technology", "tecnologia educacional"),
    )),
)


@dataclass(frozen=True)
class Topic:
    area: str
    sub: str  # "" = a area inteira
    label: str
    query_en: str
    query_pt: str

    @property
    def key(self) -> str:
        return f"{self.area}/{self.sub}" if self.sub else self.area

    def query(self, language: str) -> str:
        return self.query_pt if language == "pt" else self.query_en


class InterestsError(DiggerError):
    """Preferencias invalidas; a mensagem e segura para o usuario."""


def _build() -> tuple[dict[str, tuple[str, str, str]], dict[tuple[str, str], Topic]]:
    areas: dict[str, tuple[str, str, str]] = {}
    topics: dict[tuple[str, str], Topic] = {}
    for key, label, en, pt, subs in _AREAS:
        areas[key] = (label, en, pt)
        topics[(key, "")] = Topic(key, "", label, en, pt)
        for sub_key, sub_label, sub_en, sub_pt in subs:
            topics[(key, sub_key)] = Topic(key, sub_key, f"{label}: {sub_label}", sub_en, sub_pt)
    return areas, topics


_AREA_INDEX, _TOPIC_INDEX = _build()
_LANGUAGE_CODES = {code for code, _ in LANGUAGES}


@dataclass(frozen=True)
class Preferences:
    topics: tuple[tuple[str, tuple[str, ...]], ...] = field(default_factory=tuple)  # (area, subtemas)
    languages: tuple[str, ...] = ()
    terms: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {"topics": [{"area": a, "subtopics": list(s)} for a, s in self.topics], "languages": list(self.languages), "terms": list(self.terms)}

    def selected(self) -> list[Topic]:
        """Temas a acompanhar: cada subtema escolhido, ou a area inteira quando nao ha subtema."""
        chosen: list[Topic] = []
        for area, subs in self.topics:
            if subs:
                chosen.extend(_TOPIC_INDEX[(area, sub)] for sub in subs)
            else:
                chosen.append(_TOPIC_INDEX[(area, "")])
        return chosen

    @property
    def empty(self) -> bool:
        return not self.topics and not self.terms


def catalogo() -> dict[str, object]:
    """Opcoes para a tela de interesses."""
    return {
        "areas": [
            {"key": key, "label": label, "subtopics": [{"key": s[0], "label": s[1]} for s in subs]}
            for key, label, _en, _pt, subs in _AREAS
        ],
        "languages": [{"code": code, "label": label} for code, label in LANGUAGES],
        "limits": {"topics": MAX_TOPICS, "languages": MAX_LANGUAGES, "terms": MAX_TERMS, "termChars": MAX_TERM_CHARS},
    }


def clean_term(text: str) -> str:
    return " ".join("".join(ch if ch.isprintable() else " " for ch in str(text)).split())[:MAX_TERM_CHARS]


def validar(topics: list[dict[str, object]], languages: list[str], terms: list[str]) -> Preferences:
    """Confere areas, subtemas, idiomas e termos livres; remove repeticoes e rejeita valores desconhecidos."""
    chosen: dict[str, list[str]] = {}
    for item in topics:
        area = str(item.get("area", ""))
        if area not in _AREA_INDEX:
            raise InterestsError("Área desconhecida.")
        raw_subs = item.get("subtopics", [])
        subs = [str(s) for s in raw_subs] if isinstance(raw_subs, list) else []
        for sub in subs:
            if (area, sub) not in _TOPIC_INDEX:
                raise InterestsError("Subtema desconhecido.")
        merged = chosen.setdefault(area, [])
        merged.extend(s for s in subs if s not in merged)
    count = sum(len(subs) or 1 for subs in chosen.values())
    if count > MAX_TOPICS:
        raise InterestsError(f"Escolha no máximo {MAX_TOPICS} temas.")
    langs = list(dict.fromkeys(str(code).lower() for code in languages))
    if any(code not in _LANGUAGE_CODES for code in langs):
        raise InterestsError("Idioma desconhecido.")
    if len(langs) > MAX_LANGUAGES:
        raise InterestsError(f"Escolha no máximo {MAX_LANGUAGES} idiomas.")
    cleaned: list[str] = []
    for term in terms:
        text = clean_term(term)
        if text and text.lower() not in {t.lower() for t in cleaned}:
            cleaned.append(text)
    if len(cleaned) > MAX_TERMS:
        raise InterestsError(f"Use no máximo {MAX_TERMS} palavras-chave.")
    return Preferences(topics=tuple((a, tuple(s)) for a, s in chosen.items()), languages=tuple(langs), terms=tuple(cleaned))


def carregar(raw: dict[str, object]) -> Preferences:
    """Preferencias salvas (tolera dados antigos ou invalidos descartando o que nao existe mais)."""
    topics_raw = raw.get("topics")
    topics: list[dict[str, object]] = []
    for item in topics_raw if isinstance(topics_raw, list) else []:
        if isinstance(item, dict) and item.get("area") in _AREA_INDEX:
            subs = item.get("subtopics")
            valid = [s for s in subs if (item["area"], s) in _TOPIC_INDEX] if isinstance(subs, list) else []
            topics.append({"area": item["area"], "subtopics": valid})
    langs = raw.get("languages")
    terms = raw.get("terms")
    try:
        return validar(
            topics,
            [c for c in langs if c in _LANGUAGE_CODES] if isinstance(langs, list) else [],
            [str(t) for t in terms] if isinstance(terms, list) else [],
        )
    except InterestsError:
        return Preferences()
