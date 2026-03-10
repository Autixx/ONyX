from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from onx.db.models.geo_policy import GeoPolicy, GeoPolicyMode
from onx.db.models.route_policy import RoutePolicy
from onx.schemas.geo_policies import GeoPolicyCreate, GeoPolicyUpdate


class GeoPolicyConflictError(ValueError):
    pass


class GeoPolicyService:
    _COUNTRY_CODE_PATTERN = re.compile(r"^[A-Za-z]{2}$")

    def list_policies(
        self,
        db: Session,
        *,
        route_policy_id: str | None = None,
    ) -> list[GeoPolicy]:
        query = select(GeoPolicy)
        if route_policy_id is not None:
            query = query.where(GeoPolicy.route_policy_id == route_policy_id)
        return list(
            db.scalars(
                query.order_by(GeoPolicy.created_at.desc(), GeoPolicy.country_code.asc())
            ).all()
        )

    def list_for_route_policy(
        self,
        db: Session,
        route_policy_id: str,
        *,
        only_enabled: bool = False,
    ) -> list[GeoPolicy]:
        query = select(GeoPolicy).where(GeoPolicy.route_policy_id == route_policy_id)
        if only_enabled:
            query = query.where(GeoPolicy.enabled.is_(True))
        return list(
            db.scalars(
                query.order_by(GeoPolicy.country_code.asc(), GeoPolicy.created_at.asc())
            ).all()
        )

    def get_policy(self, db: Session, policy_id: str) -> GeoPolicy | None:
        return db.get(GeoPolicy, policy_id)

    def create_policy(self, db: Session, payload: GeoPolicyCreate) -> GeoPolicy:
        route_policy = db.get(RoutePolicy, payload.route_policy_id)
        if route_policy is None:
            raise ValueError("Route policy not found.")

        country_code = self._normalize_country_code(payload.country_code)
        source_url_template = self._normalize_source_url_template(payload.source_url_template)

        existing = db.scalar(
            select(GeoPolicy).where(
                GeoPolicy.route_policy_id == payload.route_policy_id,
                GeoPolicy.country_code == country_code,
            )
        )
        if existing is not None:
            raise GeoPolicyConflictError(
                f"Geo policy for country '{country_code.upper()}' already exists for this route policy."
            )

        policy = GeoPolicy(
            route_policy_id=payload.route_policy_id,
            country_code=country_code,
            mode=GeoPolicyMode(payload.mode),
            source_url_template=source_url_template,
            enabled=payload.enabled,
        )
        db.add(policy)
        db.commit()
        db.refresh(policy)
        return policy

    def update_policy(self, db: Session, policy: GeoPolicy, payload: GeoPolicyUpdate) -> GeoPolicy:
        updates = payload.model_dump(exclude_unset=True)
        if not updates:
            return policy

        if "country_code" in updates:
            updates["country_code"] = self._normalize_country_code(updates["country_code"])
        if "source_url_template" in updates:
            updates["source_url_template"] = self._normalize_source_url_template(updates["source_url_template"])
        if "mode" in updates and updates["mode"] is not None:
            updates["mode"] = GeoPolicyMode(updates["mode"])

        candidate_country = updates.get("country_code", policy.country_code)
        if candidate_country != policy.country_code:
            existing = db.scalar(
                select(GeoPolicy).where(
                    GeoPolicy.route_policy_id == policy.route_policy_id,
                    GeoPolicy.country_code == candidate_country,
                    GeoPolicy.id != policy.id,
                )
            )
            if existing is not None:
                raise GeoPolicyConflictError(
                    f"Geo policy for country '{candidate_country.upper()}' already exists for this route policy."
                )

        for key, value in updates.items():
            setattr(policy, key, value)
        db.add(policy)
        db.commit()
        db.refresh(policy)
        return policy

    def delete_policy(self, db: Session, policy: GeoPolicy) -> None:
        db.delete(policy)
        db.commit()

    @classmethod
    def _normalize_country_code(cls, value: str) -> str:
        text = value.strip()
        if not cls._COUNTRY_CODE_PATTERN.fullmatch(text):
            raise ValueError("country_code must contain exactly 2 letters (ISO 3166-1 alpha-2).")
        return text.lower()

    @staticmethod
    def _normalize_source_url_template(value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("source_url_template must not be empty.")
        if "{country}" not in text:
            raise ValueError("source_url_template must contain '{country}' placeholder.")
        if not text.startswith("https://") and not text.startswith("http://"):
            raise ValueError("source_url_template must start with http:// or https://")
        return text
