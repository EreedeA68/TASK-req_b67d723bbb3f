"""User model with bcrypt password hashing."""
from datetime import datetime

from app.db import db
from app.models.role import user_roles


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    roles = db.relationship(
        "Role",
        secondary=user_roles,
        backref=db.backref("users", lazy="dynamic"),
        lazy="joined",
    )

    def role_names(self) -> list:
        return [r.name for r in self.roles]

    def has_role(self, name: str) -> bool:
        return name in self.role_names()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "username": self.username,
            "roles": self.role_names(),
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
