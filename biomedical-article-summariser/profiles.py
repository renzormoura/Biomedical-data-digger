"""Perfil de uso por conta: o que a pessoa faz e se quer ver o pacote "Saude no Brasil" (ANVISA, Conitec e Rename).

O produto e um so, com um nucleo para qualquer area. O perfil so escolhe o que fica em destaque e liga ou desliga o pacote
de saude; ele nunca tira uma funcao do nucleo. Sem perfil escolhido (e para quem nao tem conta) o pacote fica visivel,
para nao esconder o diferencial de quem ainda nao disse o que faz.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from db import Database
from domain import DiggerError

# (chave, rotulo, descricao, pacote de saude ligado por padrao)
PROFILES: tuple[tuple[str, str, str, bool], ...] = (
    ("estudante", "Estudante", "Graduação, TCC, dissertação ou tese.", False),
    ("pesquisador", "Pesquisador", "Pesquisa acadêmica em qualquer área.", False),
    ("saude", "Profissional de saúde ou farmácia", "Clínica, farmácia hospitalar, saúde pública ou gestão em saúde.", True),
    ("consultoria", "Consultoria ou assessoria", "Panoramas e relatórios de evidência para clientes.", False),
    ("outro", "Outro uso", "Leitura e acompanhamento de artigos.", False),
)
_KEYS = {key: default for key, _label, _desc, default in PROFILES}

_SCHEMA = (
    """CREATE TABLE IF NOT EXISTS user_profiles (
        user_email TEXT PRIMARY KEY, profile TEXT NOT NULL, health_pack INTEGER NOT NULL, updated_at TEXT NOT NULL)""",
)


class ProfileError(DiggerError):
    """Perfil invalido; a mensagem e segura para o usuario."""


@dataclass(frozen=True)
class Profile:
    key: str | None  # None = a pessoa ainda nao escolheu
    health_pack: bool

    @property
    def configured(self) -> bool:
        return self.key is not None


DEFAULT = Profile(None, True)


def options() -> list[dict[str, object]]:
    return [{"key": key, "label": label, "description": description, "healthPack": default} for key, label, description, default in PROFILES]


class ProfileStore:
    def __init__(self, database: Database | None = None) -> None:
        self._db = database or Database()

    def initialize(self) -> None:
        with self._db.transaction() as tx:
            for statement in _SCHEMA:
                tx.execute(statement)

    def get(self, user: str | None) -> Profile:
        if not user:
            return DEFAULT
        rows = self._db.query("SELECT profile, health_pack FROM user_profiles WHERE user_email = ?", (user,))
        if not rows or rows[0][0] not in _KEYS:
            return DEFAULT
        return Profile(str(rows[0][0]), bool(rows[0][1]))

    def delete(self, user: str) -> None:
        self._db.execute("DELETE FROM user_profiles WHERE user_email = ?", (user,))

    def set(self, user: str, key: str, health_pack: bool | None = None) -> Profile:
        if key not in _KEYS:
            raise ProfileError("Perfil desconhecido.")
        pack = _KEYS[key] if health_pack is None else bool(health_pack)
        self._db.execute(
            """INSERT INTO user_profiles (user_email, profile, health_pack, updated_at) VALUES (?, ?, ?, ?)
               ON CONFLICT (user_email) DO UPDATE SET profile = excluded.profile, health_pack = excluded.health_pack,
               updated_at = excluded.updated_at""",
            (user, key, 1 if pack else 0, datetime.now(timezone.utc).isoformat(timespec="seconds")),
        )
        return Profile(key, pack)
