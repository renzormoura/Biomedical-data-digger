"""Areas do conhecimento, subtemas e idiomas que o usuario pode acompanhar, e a validacao das preferencias.

Cada tema carrega a consulta usada para procurar artigos novos: termos em ingles (a maioria dos indices bibliograficos
indexa titulo e resumo em ingles) e, quando o usuario pede artigos em portugues, termos em portugues. A escolha de um
subtema usa so a consulta do subtema; uma area sem subtemas usa a consulta da area.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache

from domain import DiggerError

MAX_TOPICS = 15  # areas sem subtema + subtemas escolhidos
MAX_LANGUAGES = 4
MAX_TERMS = 5
MAX_TERM_CHARS = 60

LANGUAGES = (
    ("pt", "Português"), ("en", "Inglês"), ("es", "Espanhol"), ("fr", "Francês"),
    ("de", "Alemão"), ("it", "Italiano"), ("zh", "Chinês"), ("ja", "Japonês"),
)

# (chave, rotulo, termos em ingles, termos em portugues): alternativas separadas por "|"; a primeira e a busca nas fontes
_Sub = tuple[str, str, str, str]
_AREAS: tuple[tuple[str, str, str, str, tuple[_Sub, ...]], ...] = (
    ("medicina", "Medicina", "medicine|medical|clinical", "medicina|médico|clínico", (
        ("pediatria", "Pediatria", "pediatrics|pediatric|paediatric|children", "pediatria|pediátrico|crianças"),
        ("oncologia", "Oncologia", "oncology|oncologic|cancer|tumor|neoplasm", "oncologia|oncológico|câncer|tumor|neoplasia"),
        ("cardiologia", "Cardiologia", "cardiology|cardiac|cardiovascular|heart", "cardiologia|cardíaco|cardiovascular|coração"),
        ("neurologia", "Neurologia", "neurology|neurologic|stroke|epilepsy", "neurologia|neurológico|avc|epilepsia"),
        ("psiquiatria", "Psiquiatria", "psychiatry|psychiatric|mental disorder|depression", "psiquiatria|psiquiátrico|transtorno mental|depressão"),
        ("infectologia", "Infectologia", "infectious disease|infection|infectious|antimicrobial", "doenças infecciosas|infecção|infeccioso|antimicrobiano"),
        ("endocrinologia", "Endocrinologia e diabetes", "endocrinology|diabetes|thyroid|endocrine", "endocrinologia|diabetes|tireoide|endócrino"),
        ("ginecologia", "Ginecologia e obstetrícia", "obstetrics|gynecology|gynaecology|pregnancy", "obstetrícia|ginecologia|gestação|gravidez"),
        ("geriatria", "Geriatria", "geriatrics|older adults|elderly|ageing", "geriatria|idosos|idoso|envelhecimento"),
        ("ortopedia", "Ortopedia", "orthopedics|orthopaedic|fracture|arthroplasty", "ortopedia|ortopédico|fratura|artroplastia"),
        ("dermatologia", "Dermatologia", "dermatology|dermatologic|skin|psoriasis", "dermatologia|dermatológico|pele|psoríase"),
        ("saude-publica", "Saúde pública", "public health|epidemiology|health policy", "saúde pública|epidemiologia|política de saúde"),
        ("emergencia", "Emergência e terapia intensiva", "critical care|intensive care|emergency medicine|emergency department", "terapia intensiva|cuidados intensivos|medicina de emergência|pronto-socorro"),
        ("anestesia", "Anestesiologia", "anesthesiology|anesthesia|anaesthesia|analgesia", "anestesiologia|anestesia|analgesia"),
    )),
    ("farmacia", "Farmácia e farmacologia", "pharmacology|pharmacy|pharmaceutical|drug", "farmacologia|farmácia|farmacêutico|medicamento", (
        ("farmacologia-clinica", "Farmacologia clínica", "clinical pharmacology|pharmacokinetics|drug interaction", "farmacologia clínica|farmacocinética|interação medicamentosa"),
        ("farmacovigilancia", "Farmacovigilância", "pharmacovigilance|adverse drug reaction|drug safety", "farmacovigilância|reação adversa|segurança de medicamentos"),
        ("farmacia-hospitalar", "Farmácia hospitalar", "hospital pharmacy|clinical pharmacy|pharmaceutical care", "farmácia hospitalar|farmácia clínica|atenção farmacêutica"),
        ("fitoterapia", "Fitoterapia", "herbal medicine|phytotherapy|medicinal plants", "fitoterapia|fitoterápico|plantas medicinais"),
        ("medicamentos-biologicos", "Medicamentos biológicos", "biologic drugs|biosimilar|monoclonal antibody", "medicamentos biológicos|biossimilar|anticorpo monoclonal"),
    )),
    ("enfermagem", "Enfermagem", "nursing|nurses|nurse", "enfermagem|enfermeiro|enfermeira", (
        ("cuidado-critico", "Cuidado crítico", "critical care nursing|intensive care nursing|critically ill", "enfermagem intensiva|cuidado crítico|paciente crítico"),
        ("saude-mulher", "Saúde da mulher e da criança", "maternal health|neonatal nursing|child health nursing|women's health", "saúde materna|enfermagem neonatal|saúde da criança|saúde da mulher"),
        ("seguranca-paciente", "Segurança do paciente", "patient safety|adverse event|medication error", "segurança do paciente|evento adverso|erro de medicação"),
    )),
    ("odontologia", "Odontologia", "dentistry|dental|oral health|dentist", "odontologia|odontológico|saúde bucal|dentista", (
        ("endodontia", "Endodontia", "endodontics|root canal|pulpitis", "endodontia|canal radicular|pulpite"),
        ("ortodontia", "Ortodontia", "orthodontics|orthodontic|malocclusion", "ortodontia|ortodôntico|má oclusão"),
        ("periodontia", "Periodontia", "periodontology|periodontitis|periodontal", "periodontia|periodontite|periodontal"),
    )),
    ("nutricao", "Nutrição e educação física", "nutrition|exercise|physical activity|diet", "nutrição|exercício físico|atividade física|dieta", (
        ("nutricao-clinica", "Nutrição clínica", "clinical nutrition|malnutrition|enteral nutrition|parenteral nutrition", "nutrição clínica|desnutrição|nutrição enteral|nutrição parenteral"),
        ("esporte", "Ciências do esporte", "sports science|athletes|sports performance|exercise physiology", "ciências do esporte|atletas|desempenho esportivo|fisiologia do exercício"),
        ("obesidade", "Obesidade", "obesity|overweight|bariatric", "obesidade|sobrepeso|bariátrica"),
    )),
    ("biologia", "Biologia e biotecnologia", "biology|biotechnology|molecular biology", "biologia|biotecnologia|biologia molecular", (
        ("genetica", "Genética e genômica", "genetics|genomics|genetic variant|gene expression", "genética|genômica|variante genética|expressão gênica"),
        ("microbiologia", "Microbiologia", "microbiology|bacteria|microbiome|microbial", "microbiologia|bactéria|microbioma|microbiano"),
        ("imunologia", "Imunologia", "immunology|immune response|vaccine|antibody", "imunologia|resposta imune|vacina|anticorpo"),
        ("bioinformatica", "Bioinformática", "bioinformatics|computational biology|sequencing", "bioinformática|biologia computacional|sequenciamento"),
        ("ecologia", "Ecologia", "ecology|ecosystem|species", "ecologia|ecossistema|espécies"),
    )),
    ("psicologia", "Psicologia e neurociência", "psychology|neuroscience|psychological|cognitive", "psicologia|neurociência|psicológico|cognitivo", (
        ("psicologia-clinica", "Psicologia clínica", "clinical psychology|psychotherapy|cognitive behavioral therapy", "psicologia clínica|psicoterapia|terapia cognitivo-comportamental"),
        ("neurociencia-cognitiva", "Neurociência cognitiva", "cognitive neuroscience|cognition|neuroimaging", "neurociência cognitiva|cognição|neuroimagem"),
        ("desenvolvimento", "Desenvolvimento humano", "developmental psychology|child development|adolescent development", "psicologia do desenvolvimento|desenvolvimento infantil|adolescência"),
    )),
    ("computacao", "Computação e IA", "artificial intelligence|computer science|machine learning|algorithm", "inteligência artificial|ciência da computação|aprendizado de máquina|algoritmo", (
        ("aprendizado-maquina", "Aprendizado de máquina", "machine learning|deep learning|neural network", "aprendizado de máquina|aprendizagem de máquina|aprendizado profundo|rede neural"),
        ("llm", "Modelos de linguagem", "large language model|LLM|ChatGPT|generative AI", "modelo de linguagem|grandes modelos de linguagem|IA generativa|ChatGPT"),
        ("seguranca-informacao", "Segurança da informação", "cybersecurity|information security|malware|cyberattack", "cibersegurança|segurança da informação|malware|ataque cibernético"),
        ("saude-digital", "Saúde digital", "digital health|telemedicine|telehealth|mHealth", "saúde digital|telemedicina|telessaúde|saúde móvel"),
        ("engenharia-software", "Engenharia de software", "software engineering|software development|software testing", "engenharia de software|desenvolvimento de software|teste de software"),
    )),
    ("engenharia", "Engenharias e tecnologia", "engineering|engineer|technological innovation", "engenharia|engenheiro|inovação tecnológica", (
        ("materiais", "Ciência dos materiais", "materials science|nanomaterials|polymer|alloy", "ciência dos materiais|nanomateriais|polímero|liga metálica"),
        ("energia", "Energia", "renewable energy|solar energy|wind power|energy storage", "energia renovável|energia solar|energia eólica|armazenamento de energia"),
        ("civil", "Engenharia civil", "civil engineering|concrete|structural engineering", "engenharia civil|concreto|engenharia estrutural"),
        ("eletrica", "Engenharia elétrica e eletrônica", "electrical engineering|electronics|power systems", "engenharia elétrica|eletrônica|sistemas de potência"),
        ("biomedica", "Engenharia biomédica", "biomedical engineering|biomedical device|biosensor", "engenharia biomédica|dispositivo biomédico|biossensor"),
    )),
    ("exatas", "Física, química e matemática", "physics|chemistry|mathematics", "física|química|matemática", (
        ("fisica", "Física", "physics|quantum|particle", "física|quântico|partícula"),
        ("quimica", "Química", "chemistry|chemical|synthesis", "química|químico|síntese"),
        ("matematica", "Matemática e estatística", "mathematics|statistics|theorem", "matemática|estatística|teorema"),
        ("astronomia", "Astronomia", "astronomy|astrophysics|galaxy|telescope", "astronomia|astrofísica|galáxia|telescópio"),
    )),
    ("ambiente", "Meio ambiente e ciências da Terra", "environmental science|environment|ecosystem|pollution", "ciência ambiental|meio ambiente|ecossistema|poluição", (
        ("clima", "Mudanças climáticas", "climate change|global warming|greenhouse gas", "mudanças climáticas|mudança climática|aquecimento global|gases de efeito estufa"),
        ("geologia", "Geologia", "geology|geological|mineral", "geologia|geológico|mineral"),
        ("biodiversidade", "Biodiversidade", "biodiversity|conservation|endangered species", "biodiversidade|conservação|espécies ameaçadas"),
        ("recursos-hidricos", "Recursos hídricos", "water resources|hydrology|groundwater", "recursos hídricos|hidrologia|águas subterrâneas"),
    )),
    ("agrarias", "Ciências agrárias e veterinária", "agriculture|agronomy|veterinary", "agricultura|agronomia|veterinária", (
        ("agronomia", "Agronomia", "agronomy|crop yield|crops|soil", "agronomia|produtividade agrícola|cultivo|solo"),
        ("veterinaria", "Medicina veterinária", "veterinary medicine|veterinary|animal health", "medicina veterinária|veterinário|saúde animal"),
        ("zootecnia", "Zootecnia", "animal science|livestock|cattle", "zootecnia|pecuária|bovinos|rebanho"),
        ("alimentos", "Ciência de alimentos", "food science|food technology|food safety", "ciência de alimentos|tecnologia de alimentos|segurança alimentar"),
    )),
    ("sociais", "Ciências sociais e humanas", "social sciences|humanities|sociology", "ciências sociais|humanidades|sociologia", (
        ("sociologia", "Sociologia", "sociology|social inequality|social movement", "sociologia|desigualdade social|movimento social"),
        ("economia", "Economia", "economics|economic growth|labor market", "economia|crescimento econômico|mercado de trabalho"),
        ("direito", "Direito", "legal studies|jurisprudence|legislation|court", "estudos jurídicos|jurisprudência|legislação|tribunal|direito penal|direito civil|direito constitucional"),
        ("politicas-publicas", "Políticas públicas", "public policy|policy making|government policy", "políticas públicas|política pública|formulação de políticas"),
        ("historia", "História", "history|historical|historiography", "história|histórico|historiografia"),
    )),
    ("educacao", "Educação", "education|teaching|pedagogy", "educação|ensino|pedagogia", (
        ("educacao-superior", "Ensino superior", "higher education|university students|undergraduate", "ensino superior|educação superior|universitários"),
        ("educacao-medica", "Educação em saúde", "medical education|health professions education|medical students", "educação médica|educação em saúde|estudantes de medicina"),
        ("tecnologia-educacional", "Tecnologia educacional", "educational technology|e-learning|digital learning", "tecnologia educacional|ensino a distância|educação digital"),
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

    def alternatives(self, language: str) -> tuple[str, ...]:
        """Termos que indicam o tema no titulo ou resumo. Em portugues, tambem os ingleses (muitos resumos vem em ingles);
        em outros idiomas ou sem idioma, ingles e portugues (o espanhol coincide com o portugues sem os acentos)."""
        if language == "en":
            raw = self.query_en
        elif language == "pt":
            raw = f"{self.query_pt}|{self.query_en}"
        else:
            raw = f"{self.query_en}|{self.query_pt}"
        return tuple(dict.fromkeys(a.strip() for a in raw.split("|") if a.strip()))

    def query(self, language: str) -> str:
        """Termo enviado as fontes: o primeiro da lista no idioma pedido."""
        return (self.query_pt if language == "pt" else self.query_en).split("|")[0].strip()


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


def _plain(text: str) -> str:
    base = unicodedata.normalize("NFKD", str(text).lower()).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", base).strip()


@lru_cache(maxsize=512)
def _needle(alternative: str) -> tuple[re.Pattern[str], ...]:
    return tuple(re.compile(rf"(?<![a-z0-9]){re.escape(word)}(?:s|es)?(?![a-z0-9])") for word in _plain(alternative).split() if word)


def mentions(text: str, alternatives: tuple[str, ...]) -> bool:
    """O texto trata do tema: alguma alternativa tem todas as palavras presentes (inteiras, com plural simples)."""
    plain = _plain(text)
    return any((needles := _needle(alt)) and all(p.search(plain) for p in needles) for alt in alternatives)


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
