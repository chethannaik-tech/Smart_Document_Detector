
import sqlite3
import os
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash


# ==========================================
# DATABASE CONFIGURATION
# ==========================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

INSTANCE_FOLDER = os.path.join(BASE_DIR, "instance")

os.makedirs(INSTANCE_FOLDER, exist_ok=True)

DB_PATH = os.path.join(INSTANCE_FOLDER, "database.db")

print("DATABASE CONNECTED:", DB_PATH)


# ==========================================
# DATABASE CONNECTION
# ==========================================

def get_connection():

    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")

    return connection


# ==========================================
# SAFE COLUMN MIGRATION
# ==========================================

def add_column_if_missing(connection, table, column, definition):

    columns = [
        row["name"]
        for row in connection.execute(
            f"PRAGMA table_info({table})"
        ).fetchall()
    ]

    if column not in columns:

        connection.execute(
            f"ALTER TABLE {table} ADD COLUMN {column} {definition}"
        )


# ==========================================
# INITIALIZE DATABASE
# ==========================================

def init_db():

    connection = get_connection()

    try:

        connection.execute("""
            CREATE TABLE IF NOT EXISTS students (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                register_number TEXT UNIQUE NOT NULL,
                department TEXT
            )
        """)

        connection.execute("""
            CREATE TABLE IF NOT EXISTS assignments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT,
                start_date TEXT,
                end_date TEXT,
                max_pages INTEGER DEFAULT 30,
                similarity_threshold REAL DEFAULT 40
            )
        """)

        connection.execute("""
            CREATE TABLE IF NOT EXISTS submissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER,
                assignment_id INTEGER,
                file_name TEXT NOT NULL,
                original_name TEXT,
                submitted_at TEXT,
                resubmission_allowed INTEGER DEFAULT 0,
                FOREIGN KEY(student_id) REFERENCES students(id),
                FOREIGN KEY(assignment_id) REFERENCES assignments(id)
            )
        """)

        connection.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL,
                student_id INTEGER
            )
        """)

        connection.execute("""
            CREATE TABLE IF NOT EXISTS similarity_report_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                assignment_id INTEGER UNIQUE,
                generated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        connection.execute("""
            CREATE TABLE IF NOT EXISTS similarity_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                assignment_id INTEGER NOT NULL,
                student1_id INTEGER NOT NULL,
                student2_id INTEGER NOT NULL,
                similarity_percent REAL NOT NULL,
                generated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Safe migrations for existing database

        add_column_if_missing(
            connection, "assignments", "max_pages",
            "INTEGER DEFAULT 30"
        )

        add_column_if_missing(
            connection, "assignments", "similarity_threshold",
            "REAL DEFAULT 40"
        )

        add_column_if_missing(
            connection, "submissions", "original_name", "TEXT"
        )

        add_column_if_missing(
            connection, "submissions", "submitted_at", "TEXT"
        )

        add_column_if_missing(
            connection, "submissions", "resubmission_allowed",
            "INTEGER DEFAULT 0"
        )

        add_column_if_missing(
            connection, "users", "student_id", "INTEGER"
        )

        connection.commit()

        print("Database initialized successfully!")

    except Exception:

        connection.rollback()
        raise

    finally:

        connection.close()


# ==========================================
# STUDENT FUNCTIONS
# ==========================================

def add_student(name, register_number, department):

    connection = get_connection()

    try:

        connection.execute("""
            INSERT INTO students
            (name, register_number, department)
            VALUES (?, ?, ?)
        """, (name, register_number, department))

        connection.commit()

        return True

    except sqlite3.IntegrityError:

        connection.rollback()
        return False

    finally:

        connection.close()


def get_all_students():

    connection = get_connection()

    students = connection.execute("""
        SELECT *
        FROM students
        ORDER BY id DESC
    """).fetchall()

    connection.close()

    return students


def get_student_by_register_number(register_number):

    connection = get_connection()

    student = connection.execute("""
        SELECT *
        FROM students
        WHERE register_number = ?
    """, (register_number,)).fetchone()

    connection.close()

    return student


# ==========================================
# ASSIGNMENT FUNCTIONS
# ==========================================

def get_all_assignments():

    connection = get_connection()

    assignments = connection.execute("""
        SELECT *
        FROM assignments
        ORDER BY id DESC
    """).fetchall()

    connection.close()

    return assignments


# ==========================================
# USER LOGIN AND REGISTRATION
# ==========================================

def create_user(username, password, role, student_id=None):

    connection = get_connection()

    try:

        password_hash = generate_password_hash(password)

        connection.execute("""
            INSERT INTO users
            (username, password_hash, role, student_id)
            VALUES (?, ?, ?, ?)
        """, (username, password_hash, role, student_id))

        connection.commit()

        return True

    except sqlite3.IntegrityError:

        connection.rollback()
        return False

    finally:

        connection.close()


def verify_user(username, password):

    connection = get_connection()

    columns = [
        row["name"]
        for row in connection.execute(
            "PRAGMA table_info(users)"
        ).fetchall()
    ]

    password_column = (
        "password_hash" if "password_hash" in columns
        else "password"
    )

    user = connection.execute(f"""
        SELECT
            id,
            username,
            {password_column} AS password,
            role,
            student_id
        FROM users
        WHERE username = ?
    """, (username,)).fetchone()

    connection.close()

    if user:

        try:

            if check_password_hash(user["password"], password):
                return user

        except (ValueError, TypeError):

            return None

    return None


# ==========================================
# SIMILARITY REPORT INVALIDATION
# ==========================================

def invalidate_similarity_report(connection, assignment_id):

    connection.execute("""
        DELETE FROM similarity_results
        WHERE assignment_id = ?
    """, (assignment_id,))

    connection.execute("""
        DELETE FROM similarity_report_runs
        WHERE assignment_id = ?
    """, (assignment_id,))


# ==========================================
# SUBMISSION FUNCTIONS
# ==========================================

def add_submission(
    student_id,
    assignment_id,
    file_name,
    original_name=None
):

    connection = get_connection()

    try:

        invalidate_similarity_report(connection, assignment_id)

        connection.execute("""
            INSERT INTO submissions
            (
                student_id,
                assignment_id,
                file_name,
                original_name,
                submitted_at,
                resubmission_allowed
            )
            VALUES (?, ?, ?, ?, ?, 0)
        """, (
            student_id,
            assignment_id,
            file_name,
            original_name,
            datetime.now().isoformat()
        ))

        connection.commit()

        return True

    except Exception:

        connection.rollback()
        raise

    finally:

        connection.close()


def get_submission_for_student_assignment(student_id, assignment_id):

    connection = get_connection()

    submission = connection.execute("""
        SELECT *
        FROM submissions
        WHERE student_id = ?
        AND assignment_id = ?
    """, (student_id, assignment_id)).fetchone()

    connection.close()

    return submission


def get_student_submissions(student_id):

    connection = get_connection()

    submissions = connection.execute("""
        SELECT
            submissions.*,
            assignments.title AS assignment_title
        FROM submissions
        JOIN assignments
        ON submissions.assignment_id = assignments.id
        WHERE submissions.student_id = ?
        ORDER BY submissions.id DESC
    """, (student_id,)).fetchall()

    connection.close()

    return submissions


def get_all_submissions():

    connection = get_connection()

    submissions = connection.execute("""
        SELECT
            submissions.*,
            students.name AS student_name,
            students.register_number,
            assignments.title AS assignment_title
        FROM submissions
        JOIN students
        ON submissions.student_id = students.id
        JOIN assignments
        ON submissions.assignment_id = assignments.id
        ORDER BY submissions.id DESC
    """).fetchall()

    connection.close()

    return submissions


def get_submission_by_id(submission_id):

    connection = get_connection()

    submission = connection.execute("""
        SELECT
            submissions.*,
            students.name AS student_name,
            students.register_number,
            assignments.title AS assignment_title
        FROM submissions
        JOIN students
        ON submissions.student_id = students.id
        JOIN assignments
        ON submissions.assignment_id = assignments.id
        WHERE submissions.id = ?
    """, (submission_id,)).fetchone()

    connection.close()

    return submission


def get_submissions_for_assignment(assignment_id):

    connection = get_connection()

    submissions = connection.execute("""
        SELECT
            submissions.*,
            students.name AS student_name,
            students.register_number
        FROM submissions
        JOIN students
        ON submissions.student_id = students.id
        WHERE submissions.assignment_id = ?
        ORDER BY submissions.id
    """, (assignment_id,)).fetchall()

    connection.close()

    return submissions


# ==========================================
# RESUBMISSION FUNCTIONS
# ==========================================

def allow_resubmission(submission_id):

    connection = get_connection()

    try:

        cursor = connection.execute("""
            UPDATE submissions
            SET resubmission_allowed = 1
            WHERE id = ?
        """, (submission_id,))

        connection.commit()

        return cursor.rowcount > 0

    finally:

        connection.close()


def update_submission_file(
    submission_id,
    file_name,
    original_name=None
):

    connection = get_connection()

    try:

        submission = connection.execute("""
            SELECT assignment_id
            FROM submissions
            WHERE id = ?
        """, (submission_id,)).fetchone()

        if submission is None:
            return False

        invalidate_similarity_report(
            connection,
            submission["assignment_id"]
        )

        cursor = connection.execute("""
            UPDATE submissions
            SET
                file_name = ?,
                original_name = ?,
                submitted_at = ?,
                resubmission_allowed = 0
            WHERE id = ?
            AND resubmission_allowed = 1
        """, (
            file_name,
            original_name,
            datetime.now().isoformat(),
            submission_id
        ))

        connection.commit()

        return cursor.rowcount > 0

    except Exception:

        connection.rollback()
        raise

    finally:

        connection.close()


# ==========================================
# SIMILARITY DETECTION FUNCTIONS
# ==========================================

def get_assignments_due_for_similarity():

    connection = get_connection()

    assignments = connection.execute("""
        SELECT *
        FROM assignments
        WHERE end_date IS NOT NULL
        AND date(end_date) <= date('now', 'localtime')
    """).fetchall()

    connection.close()

    return assignments


def save_similarity_report(assignment_id, comparisons):

    connection = get_connection()

    try:

        invalidate_similarity_report(connection, assignment_id)

        for item in comparisons:

            connection.execute("""
                INSERT INTO similarity_results
                (
                    assignment_id,
                    student1_id,
                    student2_id,
                    similarity_percent
                )
                VALUES (?, ?, ?, ?)
            """, (
                assignment_id,
                item["student1_id"],
                item["student2_id"],
                item.get(
                    "similarity_percent",
                    item.get("similarity", 0)
                )
            ))

        connection.execute("""
            INSERT INTO similarity_report_runs
            (assignment_id, generated_at)
            VALUES (?, ?)
        """, (
            assignment_id,
            datetime.now().isoformat()
        ))

        connection.commit()

    except Exception:

        connection.rollback()
        raise

    finally:

        connection.close()


def get_similarity_report(assignment_id):

    connection = get_connection()

    results = connection.execute("""
        SELECT
            sr.id,
            sr.assignment_id,
            sr.student1_id,
            s1.name AS student1_name,
            s1.register_number AS student1_register_number,
            sr.student2_id,
            s2.name AS student2_name,
            s2.register_number AS student2_register_number,
            sr.similarity_percent AS similarity,
            sr.similarity_percent,
            sr.generated_at
        FROM similarity_results sr
        LEFT JOIN students s1
            ON sr.student1_id = s1.id
        LEFT JOIN students s2
            ON sr.student2_id = s2.id
        WHERE sr.assignment_id = ?
        ORDER BY sr.similarity_percent DESC
    """, (assignment_id,)).fetchall()

    connection.close()

    return results


def get_similarity_report_run(assignment_id):

    connection = get_connection()

    result = connection.execute("""
        SELECT
            id,
            assignment_id,
            generated_at AS checked_at
        FROM similarity_report_runs
        WHERE assignment_id = ?
    """, (assignment_id,)).fetchone()

    connection.close()

    return result


# ==========================================
# TEACHER DASHBOARD
# ==========================================

def get_dashboard_data():

    connection = get_connection()

    total_students = connection.execute("""
        SELECT COUNT(*) FROM students
    """).fetchone()[0]

    total_assignments = connection.execute("""
        SELECT COUNT(*) FROM assignments
    """).fetchone()[0]

    total_submissions = connection.execute("""
        SELECT COUNT(*) FROM submissions
    """).fetchone()[0]

    recent_assignments = connection.execute("""
        SELECT *
        FROM assignments
        ORDER BY id DESC
        LIMIT 10
    """).fetchall()

    connection.close()

    return {
        "total_students": total_students,
        "total_assignments": total_assignments,
        "total_submissions": total_submissions,
        "recent_assignments": recent_assignments
    }


# ==========================================
# RUN DATABASE
# ==========================================

if __name__ == "__main__":

    init_db()

    print("Database initialized successfully!")
