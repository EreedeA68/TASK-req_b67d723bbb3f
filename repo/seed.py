"""Seed the database with one user per role for development and Docker demos.

Run standalone:
    python seed.py

Or call from an existing app context:
    from seed import seed_users
    seed_users(app)

The script is idempotent — re-running it skips users that already exist.
"""

SEED_USERS = [
    # (username,        password,         roles)
    ("admin",           "Admin1234!",     ["admin"]),
    ("staff",           "Staff1234!",     ["staff"]),
    ("photographer",    "Photo1234!",     ["photographer"]),
    ("kitchen",         "Kitchen1234!",   ["kitchen"]),
    ("member",          "Member1234!",    ["member"]),
]


def seed_users(app) -> list[str]:
    """Create seed users inside *app*'s context. Returns list of created usernames."""
    from app.services.auth_service import register, AuthError

    created = []
    with app.app_context():
        for username, password, roles in SEED_USERS:
            try:
                register(username, password, roles=roles)
                created.append(username)
                print(f"  [seed] created  {username!r:20s} roles={roles}")
            except AuthError:
                print(f"  [seed] skipped  {username!r:20s} (already exists)")
    return created


if __name__ == "__main__":
    import os
    import sys

    # Ensure project root is importable
    sys.path.insert(0, os.path.dirname(__file__))

    from app import create_app
    from config import Config

    app = create_app(Config)
    seed_users(app)
    print("Seed complete.")
