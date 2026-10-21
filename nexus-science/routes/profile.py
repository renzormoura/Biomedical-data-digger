"""Rotas: Perfil de uso."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request

from profiles import Profile
from profiles import options as profile_options_list
from routes.context import ApiContext
from routes.schemas import (
    ProfileIn,
)


def register_profile_routes(app: FastAPI, ctx: ApiContext) -> None:
    profiles = ctx.profiles
    require_user = ctx.require_user

    # -- perfil de uso -------------------------------------------------------------
    if profiles is not None:
        profile_store = profiles

        def profile_payload(profile: Profile) -> dict[str, Any]:
            return {"profile": profile.key, "healthPack": profile.health_pack, "configured": profile.configured}

        @app.get("/api/profile/options")
        def profile_options() -> dict[str, Any]:
            return {"profiles": profile_options_list()}

        @app.get("/api/profile")
        def get_profile(request: Request) -> dict[str, Any]:
            return profile_payload(profile_store.get(require_user(request)))

        @app.put("/api/profile")
        def put_profile(body: ProfileIn, request: Request) -> dict[str, Any]:
            return profile_payload(profile_store.set(require_user(request), body.profile, body.health_pack))
