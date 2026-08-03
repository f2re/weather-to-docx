from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from weather_to_docx.domain.models import Location


class LocationRepository:
    """Справочник координат в общей SQLite-базе приложения."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)

    def initialise(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                PRAGMA journal_mode=WAL;
                PRAGMA synchronous=NORMAL;
                CREATE TABLE IF NOT EXISTS locations (
                    id TEXT PRIMARY KEY,
                    location_json TEXT NOT NULL,
                    group_name TEXT,
                    created_at_utc TEXT NOT NULL,
                    updated_at_utc TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_locations_group_name
                    ON locations(group_name, id);
                """
            )

    def create(self, location: Location) -> Location:
        self.initialise()
        now = datetime.now(UTC).isoformat()
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO locations(
                        id, location_json, group_name, created_at_utc, updated_at_utc
                    )
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        location.id,
                        location.model_dump_json(),
                        location.group,
                        now,
                        now,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"Координата {location.id!r} уже существует") from exc
        return self.get(location.id)

    def upsert(self, location: Location) -> Location:
        self.initialise()
        now = datetime.now(UTC).isoformat()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO locations(
                    id, location_json, group_name, created_at_utc, updated_at_utc
                )
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    location_json = excluded.location_json,
                    group_name = excluded.group_name,
                    updated_at_utc = excluded.updated_at_utc
                """,
                (
                    location.id,
                    location.model_dump_json(),
                    location.group,
                    now,
                    now,
                ),
            )
        return self.get(location.id)

    def replace(self, location_id: str, location: Location) -> Location:
        if location.id != location_id:
            raise ValueError("Идентификатор координаты в адресе и теле запроса должен совпадать")
        self.initialise()
        now = datetime.now(UTC).isoformat()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE locations
                SET location_json = ?, group_name = ?, updated_at_utc = ?
                WHERE id = ?
                """,
                (
                    location.model_dump_json(),
                    location.group,
                    now,
                    location_id,
                ),
            )
            if cursor.rowcount == 0:
                raise KeyError(f"Координата {location_id!r} не найдена")
        return self.get(location_id)

    def get(self, location_id: str) -> Location:
        self.initialise()
        with self._connect() as connection:
            row = connection.execute(
                "SELECT location_json FROM locations WHERE id = ?",
                (location_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"Координата {location_id!r} не найдена")
        return Location.model_validate_json(row["location_json"])

    def list(
        self,
        *,
        group: str | None = None,
        limit: int = 1000,
    ) -> list[Location]:
        self.initialise()
        limit = max(1, min(limit, 10000))
        with self._connect() as connection:
            if group is None:
                rows = connection.execute(
                    """
                    SELECT location_json
                    FROM locations
                    ORDER BY COALESCE(group_name, ''), id
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT location_json
                    FROM locations
                    WHERE group_name = ?
                    ORDER BY id
                    LIMIT ?
                    """,
                    (group, limit),
                ).fetchall()
        return [
            Location.model_validate_json(row["location_json"])
            for row in rows
        ]

    def import_many(
        self,
        locations: list[Location],
        *,
        replace_existing: bool = False,
    ) -> list[Location]:
        self.initialise()
        ids = [location.id for location in locations]
        if len(ids) != len(set(ids)):
            raise ValueError("В импортируемом наборе повторяются идентификаторы координат")

        now = datetime.now(UTC).isoformat()
        with self._connect() as connection:
            try:
                for location in locations:
                    if replace_existing:
                        connection.execute(
                            """
                            INSERT INTO locations(
                                id, location_json, group_name, created_at_utc, updated_at_utc
                            )
                            VALUES (?, ?, ?, ?, ?)
                            ON CONFLICT(id) DO UPDATE SET
                                location_json = excluded.location_json,
                                group_name = excluded.group_name,
                                updated_at_utc = excluded.updated_at_utc
                            """,
                            (
                                location.id,
                                location.model_dump_json(),
                                location.group,
                                now,
                                now,
                            ),
                        )
                    else:
                        connection.execute(
                            """
                            INSERT INTO locations(
                                id, location_json, group_name, created_at_utc, updated_at_utc
                            )
                            VALUES (?, ?, ?, ?, ?)
                            """,
                            (
                                location.id,
                                location.model_dump_json(),
                                location.group,
                                now,
                                now,
                            ),
                        )
            except sqlite3.IntegrityError as exc:
                raise ValueError(
                    "Импорт остановлен: один из идентификаторов уже существует"
                ) from exc
        return [self.get(location_id) for location_id in ids]

    def delete(self, location_id: str) -> bool:
        self.initialise()
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM locations WHERE id = ?",
                (location_id,),
            )
        return cursor.rowcount > 0

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=30000")
        return connection
