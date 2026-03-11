from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from onx.db.models.access_rule import AccessRule
from onx.schemas.access_rules import AccessRuleUpsert


class AccessRuleService:
    def list_rules(self, db: Session) -> list[AccessRule]:
        return list(
            db.scalars(
                select(AccessRule).order_by(AccessRule.permission_key.asc())
            ).all()
        )

    def get_rule_by_permission_key(self, db: Session, permission_key: str) -> AccessRule | None:
        return db.scalar(
            select(AccessRule).where(AccessRule.permission_key == permission_key)
        )

    def upsert_rule(self, db: Session, permission_key: str, payload: AccessRuleUpsert) -> AccessRule:
        rule = self.get_rule_by_permission_key(db, permission_key)
        normalized_roles = self._normalize_roles(payload.allowed_roles)
        if rule is None:
            rule = AccessRule(
                permission_key=permission_key,
                description=payload.description,
                allowed_roles_json=normalized_roles,
                enabled=payload.enabled,
            )
            db.add(rule)
        else:
            rule.description = payload.description
            rule.allowed_roles_json = normalized_roles
            rule.enabled = payload.enabled
            db.add(rule)
        db.commit()
        db.refresh(rule)
        return rule

    def delete_rule(self, db: Session, rule: AccessRule) -> None:
        db.delete(rule)
        db.commit()

    @staticmethod
    def _normalize_roles(roles: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for role in roles:
            value = role.strip().lower()
            if not value:
                continue
            if value not in seen:
                normalized.append(value)
                seen.add(value)
        if not normalized:
            raise ValueError("allowed_roles must not be empty.")
        return normalized
