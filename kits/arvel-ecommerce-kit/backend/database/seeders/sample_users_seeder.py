"""Seed sample users for each role level.

All passwords are "password" — dev/test only.
"""

from __future__ import annotations

from app.support.seeder import EcommerceSeeder


class SampleUsersSeeder(EcommerceSeeder):
    async def run(self) -> None:
        users = [
            {
                "name": "Sandra Super",
                "email": "superadmin@example.com",
                "role_name": "super_admin",
            },
            {
                "name": "Carol Catalog",
                "email": "catalog@example.com",
                "role_name": "catalog_manager",
            },
            {"name": "Sam Support", "email": "support@example.com", "role_name": "support_agent"},
            {"name": "Chris Customer", "email": "customer@example.com", "role_name": "customer"},
            {"name": "Casey Customer", "email": "customer2@example.com", "role_name": "customer"},
        ]

        for user_data in users:
            role_name = user_data.pop("role_name")
            user = await self.db.upsert(
                "users",
                match_on=["email"],
                data={
                    **user_data,
                    "password": self.hash_password("password"),
                    "email_verified_at": self.now(),
                    "locale": "en",
                    "theme": "system",
                },
                cast_map={"theme": "users_theme"},
            )
            role = await self.db.table("roles").where("name", role_name).first()
            if not role or not user:
                continue
            await self.db.upsert(
                "model_has_roles",
                match_on=["role_id", "model_id", "model_type"],
                data={
                    "role_id": role["id"],
                    "model_id": str(user["id"]),
                    "model_type": "User",
                    "guard_name": "api",
                },
            )
