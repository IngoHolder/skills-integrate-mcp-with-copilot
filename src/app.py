"""
High School Management System API

A super simple FastAPI application that allows students to view and sign up
for extracurricular activities at Mergington High School.
"""

from contextlib import asynccontextmanager, closing
import os
from pathlib import Path
import sqlite3

from fastapi import FastAPI, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles


INITIAL_ACTIVITIES = {
    "Chess Club": {
        "description": "Learn strategies and compete in chess tournaments",
        "schedule": "Fridays, 3:30 PM - 5:00 PM",
        "max_participants": 12,
        "participants": ["michael@mergington.edu", "daniel@mergington.edu"],
    },
    "Programming Class": {
        "description": "Learn programming fundamentals and build software projects",
        "schedule": "Tuesdays and Thursdays, 3:30 PM - 4:30 PM",
        "max_participants": 20,
        "participants": ["emma@mergington.edu", "sophia@mergington.edu"],
    },
    "Gym Class": {
        "description": "Physical education and sports activities",
        "schedule": "Mondays, Wednesdays, Fridays, 2:00 PM - 3:00 PM",
        "max_participants": 30,
        "participants": ["john@mergington.edu", "olivia@mergington.edu"],
    },
    "Soccer Team": {
        "description": "Join the school soccer team and compete in matches",
        "schedule": "Tuesdays and Thursdays, 4:00 PM - 5:30 PM",
        "max_participants": 22,
        "participants": ["liam@mergington.edu", "noah@mergington.edu"],
    },
    "Basketball Team": {
        "description": "Practice and play basketball with the school team",
        "schedule": "Wednesdays and Fridays, 3:30 PM - 5:00 PM",
        "max_participants": 15,
        "participants": ["ava@mergington.edu", "mia@mergington.edu"],
    },
    "Art Club": {
        "description": "Explore your creativity through painting and drawing",
        "schedule": "Thursdays, 3:30 PM - 5:00 PM",
        "max_participants": 15,
        "participants": ["amelia@mergington.edu", "harper@mergington.edu"],
    },
    "Drama Club": {
        "description": "Act, direct, and produce plays and performances",
        "schedule": "Mondays and Wednesdays, 4:00 PM - 5:30 PM",
        "max_participants": 20,
        "participants": ["ella@mergington.edu", "scarlett@mergington.edu"],
    },
    "Math Club": {
        "description": "Solve challenging problems and participate in math competitions",
        "schedule": "Tuesdays, 3:30 PM - 4:30 PM",
        "max_participants": 10,
        "participants": ["james@mergington.edu", "benjamin@mergington.edu"],
    },
    "Debate Team": {
        "description": "Develop public speaking and argumentation skills",
        "schedule": "Fridays, 4:00 PM - 5:30 PM",
        "max_participants": 12,
        "participants": ["charlotte@mergington.edu", "henry@mergington.edu"],
    },
}

current_dir = Path(__file__).parent
DATABASE_PATH = Path(
    os.environ.get("ACTIVITIES_DB_PATH", str(current_dir / "activities.sqlite"))
)


def _connect() -> sqlite3.Connection:
    connection = sqlite3.connect(DATABASE_PATH, timeout=30)
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize_database() -> None:
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with closing(_connect()) as connection, connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS activities (
                name TEXT PRIMARY KEY,
                description TEXT NOT NULL,
                schedule TEXT NOT NULL,
                max_participants INTEGER NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS registrations (
                activity_name TEXT NOT NULL,
                email TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (activity_name, email),
                FOREIGN KEY (activity_name) REFERENCES activities(name)
                    ON DELETE CASCADE
            )
            """
        )

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS app_metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        seeded = connection.execute(
            "SELECT 1 FROM app_metadata WHERE key = 'initial_data_seeded'"
        ).fetchone()
        if seeded is None:
            for name, details in INITIAL_ACTIVITIES.items():
                connection.execute(
                    """
                    INSERT OR IGNORE INTO activities
                        (name, description, schedule, max_participants)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        name,
                        details["description"],
                        details["schedule"],
                        details["max_participants"],
                    ),
                )
                connection.executemany(
                    """
                    INSERT OR IGNORE INTO registrations (activity_name, email)
                    VALUES (?, ?)
                    """,
                    [(name, email) for email in details["participants"]],
                )
            connection.execute(
                "INSERT INTO app_metadata (key, value) VALUES (?, ?)",
                ("initial_data_seeded", "true"),
            )


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_database()
    yield


app = FastAPI(
    title="Mergington High School API",
    description="API for viewing and signing up for extracurricular activities",
    lifespan=lifespan,
)

app.mount(
    "/static",
    StaticFiles(directory=os.path.join(Path(__file__).parent, "static")),
    name="static",
)


@app.get("/")
def root():
    return RedirectResponse(url="/static/index.html")


@app.get("/activities")
def get_activities():
    with closing(_connect()) as connection:
        rows = connection.execute(
            """
            SELECT activities.name, activities.description, activities.schedule,
                   activities.max_participants, registrations.email
            FROM activities
            LEFT JOIN registrations
                ON registrations.activity_name = activities.name
            ORDER BY activities.rowid, registrations.rowid
            """
        ).fetchall()

    result = {}
    for name, description, schedule, max_participants, email in rows:
        activity = result.setdefault(
            name,
            {
                "description": description,
                "schedule": schedule,
                "max_participants": max_participants,
                "participants": [],
            },
        )
        if email is not None:
            activity["participants"].append(email)

    return result


@app.post("/activities/{activity_name}/signup")
def signup_for_activity(activity_name: str, email: str):
    """Sign up a student for an activity."""
    with closing(_connect()) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        activity = connection.execute(
            "SELECT max_participants FROM activities WHERE name = ?",
            (activity_name,),
        ).fetchone()
        if activity is None:
            raise HTTPException(status_code=404, detail="Activity not found")

        if connection.execute(
            """
            SELECT 1 FROM registrations
            WHERE activity_name = ? AND email = ?
            """,
            (activity_name, email),
        ).fetchone():
            raise HTTPException(status_code=400, detail="Student is already signed up")

        participant_count = connection.execute(
            "SELECT COUNT(*) FROM registrations WHERE activity_name = ?",
            (activity_name,),
        ).fetchone()[0]
        if participant_count >= activity[0]:
            raise HTTPException(status_code=400, detail="Activity is full")

        connection.execute(
            "INSERT INTO registrations (activity_name, email) VALUES (?, ?)",
            (activity_name, email),
        )

    return {"message": f"Signed up {email} for {activity_name}"}


@app.delete("/activities/{activity_name}/unregister")
def unregister_from_activity(activity_name: str, email: str):
    """Unregister a student from an activity."""
    with closing(_connect()) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        if connection.execute(
            "SELECT 1 FROM activities WHERE name = ?", (activity_name,)
        ).fetchone() is None:
            raise HTTPException(status_code=404, detail="Activity not found")

        deleted = connection.execute(
            """
            DELETE FROM registrations
            WHERE activity_name = ? AND email = ?
            """,
            (activity_name, email),
        ).rowcount
        if not deleted:
            raise HTTPException(
                status_code=400,
                detail="Student is not signed up for this activity",
            )

    return {"message": f"Unregistered {email} from {activity_name}"}
