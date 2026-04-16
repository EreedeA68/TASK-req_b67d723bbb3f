"""Search log and trend models."""
from datetime import datetime

from app.db import db


class SearchLog(db.Model):
    __tablename__ = "search_logs"

    id = db.Column(db.Integer, primary_key=True)
    term = db.Column(db.String(256), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    device_id = db.Column(db.String(128), nullable=True, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "query": self.term,
            "user_id": self.user_id,
            "device_id": self.device_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class SearchTrend(db.Model):
    __tablename__ = "search_trends"

    id = db.Column(db.Integer, primary_key=True)
    term = db.Column(db.String(256), unique=True, nullable=False, index=True)
    count = db.Column(db.Integer, nullable=False, default=0)

    def to_dict(self) -> dict:
        return {
            "query": self.term,
            "count": self.count,
        }
