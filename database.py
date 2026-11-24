
import sqlite3
import os
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INSTANCE_FOLDER = os.path.join(BASE_DIR, "instance")
os.makedirs(INSTANCE_FOLDER, exist_ok=True)
DB_PATH = os.path.join(INSTANCE_FOLDER, "database.db")


def get_connection():
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


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


def init_db():
    connection = get_connection()
    try:
        connection.executescript("""
            CREATE TABLE IF NOT EXISTS students (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                register_number TEXT UNIQUE NOT NULL,
                department TEXT,
                email TEXT,
                semester INTEGER
            );

            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL,
                student_id INTEGER
            );

            CREATE TABLE IF NOT EXISTS assignments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT,
                start_date TEXT,
                end_date TEXT,
                max_pages INTEGER DEFAULT 30,
                similarity_threshold REAL DEFAULT 40,
                semester INTEGER
            );

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
            );

            CREATE TABLE IF NOT EXISTS similarity_report_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                assignment_id INTEGER UNIQUE,
                generated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS similarity_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                assignment_id INTEGER NOT NULL,
                student1_id INTEGER NOT NULL,
                student2_id INTEGER NOT NULL,
                similarity_percent REAL NOT NULL,
                generated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS teachers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER UNIQUE,
                name TEXT NOT NULL,
                email TEXT,
                department TEXT,
                FOREIGN KEY(user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS subjects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                subject_name TEXT NOT NULL,
                subject_code TEXT UNIQUE,
                department TEXT,
                semester INTEGER
            );

            CREATE TABLE IF NOT EXISTS marks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                submission_id INTEGER UNIQUE NOT NULL,
                marks_obtained REAL NOT NULL,
                max_marks REAL NOT NULL,
                feedback TEXT,
                evaluated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(submission_id) REFERENCES submissions(id)
            );

            CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                message TEXT NOT NULL,
                is_read INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id)
            );
        """)

        migrations = [
            ("assignments", "max_pages", "INTEGER DEFAULT 30"),
            ("assignments", "similarity_threshold", "REAL DEFAULT 40"),
            ("assignments", "semester", "INTEGER"),
            ("assignments", "subject", "TEXT"),
            ("assignments", "department", "TEXT"),
            ("assignments", "reference_file", "TEXT"),
            ("assignments", "max_marks", "REAL DEFAULT 100"),
            ("assignments", "accepted_format", "TEXT DEFAULT 'pdf'"),
            ("assignments", "created_by", "INTEGER"),
            ("assignments", "created_at", "TEXT"),
            ("students", "email", "TEXT"),
            ("students", "semester", "INTEGER"),
            ("submissions", "original_name", "TEXT"),
            ("submissions", "submitted_at", "TEXT"),
            ("submissions", "resubmission_allowed", "INTEGER DEFAULT 0"),
            ("users", "student_id", "INTEGER"),
        ]

        for table, column, definition in migrations:
            add_column_if_missing(
                connection, table, column, definition
            )

        connection.commit()
        print("Database initialized successfully.")

    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


# ---------------- STUDENTS AND USERS ----------------

def create_student_account(
    name, register_number, email, department, semester, password
):
    connection = get_connection()
    try:
        password_hash = generate_password_hash(password)

        cursor = connection.execute("""
            INSERT INTO students
            (name, register_number, email, department, semester)
            VALUES (?, ?, ?, ?, ?)
        """, (name, register_number, email, department, semester))

        student_id = cursor.lastrowid

        connection.execute("""
            INSERT INTO users
            (username, password_hash, role, student_id)
            VALUES (?, ?, 'student', ?)
        """, (register_number, password_hash, student_id))

        connection.commit()
        return True
    except sqlite3.IntegrityError:
        connection.rollback()
        return False
    finally:
        connection.close()


def create_user(username, password, role, student_id=None):
    connection = get_connection()
    try:
        connection.execute("""
            INSERT INTO users (username, password_hash, role, student_id)
            VALUES (?, ?, ?, ?)
        """, (
            username,
            generate_password_hash(password),
            role,
            student_id
        ))
        connection.commit()
        return True
    except sqlite3.IntegrityError:
        connection.rollback()
        return False
    finally:
        connection.close()


def authenticate_user(username, password):
    connection = get_connection()
    try:
        user = connection.execute("""
            SELECT id, username, password_hash, role, student_id
            FROM users WHERE username = ?
        """, (username,)).fetchone()

        if not user:
            return None

        try:
            valid = check_password_hash(user["password_hash"], password)
        except (ValueError, TypeError):
            valid = False

        if valid:
            return dict(user)

        # Compatibility with legacy plain-text passwords.
        if user["password_hash"] == password:
            return dict(user)

        return None
    finally:
        connection.close()


def get_student_by_user_id(user_id):
    connection = get_connection()
    try:
        row = connection.execute("""
            SELECT s.*
            FROM students s
            JOIN users u ON u.student_id = s.id
            WHERE u.id = ?
        """, (user_id,)).fetchone()

        if row:
            return dict(row)

        user = connection.execute(
            "SELECT username FROM users WHERE id = ?", (user_id,)
        ).fetchone()

        if user:
            row = connection.execute("""
                SELECT * FROM students WHERE register_number = ?
            """, (user["username"],)).fetchone()
            return dict(row) if row else None

        return None
    finally:
        connection.close()


def get_all_students():
    connection = get_connection()
    try:
        return [
            dict(row) for row in connection.execute(
                "SELECT * FROM students ORDER BY id DESC"
            ).fetchall()
        ]
    finally:
        connection.close()


def get_students_by_semester(semester):
    connection = get_connection()
    try:
        if semester == "all":
            rows = connection.execute(
                "SELECT * FROM students ORDER BY id DESC"
            ).fetchall()
        else:
            rows = connection.execute("""
                SELECT * FROM students
                WHERE semester = ? ORDER BY id DESC
            """, (int(semester),)).fetchall()
        return [dict(row) for row in rows]
    finally:
        connection.close()


# ---------------- ASSIGNMENTS ----------------

def create_assignment_record(
    title, description, semester, start_date, end_date,
    max_pages, threshold, subject=None, department=None,
    reference_file=None, max_marks=100, accepted_format="pdf",
    created_by=None
):
    connection = get_connection()
    try:
        cursor = connection.execute("""
            INSERT INTO assignments (
                title, description, semester, start_date, end_date,
                max_pages, similarity_threshold, subject, department,
                reference_file, max_marks, accepted_format,
                created_by, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            title, description, semester, start_date, end_date,
            max_pages, threshold, subject, department,
            reference_file, max_marks, accepted_format,
            created_by, datetime.now().isoformat()
        ))
        connection.commit()
        return cursor.lastrowid
    finally:
        connection.close()


def get_assignment_by_id(assignment_id):
    connection = get_connection()
    try:
        row = connection.execute(
            "SELECT * FROM assignments WHERE id = ?",
            (assignment_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        connection.close()


def get_all_assignments():
    connection = get_connection()
    try:
        return [
            dict(row) for row in connection.execute(
                "SELECT * FROM assignments ORDER BY id DESC"
            ).fetchall()
        ]
    finally:
        connection.close()


def get_assignments_by_semester(semester):
    connection = get_connection()
    try:
        if semester == "all":
            rows = connection.execute(
                "SELECT * FROM assignments ORDER BY id DESC"
            ).fetchall()
        else:
            rows = connection.execute("""
                SELECT * FROM assignments
                WHERE semester = ? ORDER BY id DESC
            """, (int(semester),)).fetchall()
        return [dict(row) for row in rows]
    finally:
        connection.close()


def get_student_semester_assignments(semester):
    connection = get_connection()
    try:
        rows = connection.execute("""
            SELECT * FROM assignments
            WHERE semester = ?
            ORDER BY id DESC
        """, (int(semester),)).fetchall()
        return [dict(row) for row in rows]
    finally:
        connection.close()


# ---------------- SUBMISSIONS ----------------

def invalidate_similarity_report(connection, assignment_id):
    connection.execute(
        "DELETE FROM similarity_results WHERE assignment_id = ?",
        (assignment_id,)
    )
    connection.execute(
        "DELETE FROM similarity_report_runs WHERE assignment_id = ?",
        (assignment_id,)
    )


def add_submission_record(
    student_id, assignment_id, file_name, original_name=None
):
    connection = get_connection()
    try:
        invalidate_similarity_report(connection, assignment_id)
        connection.execute("""
            INSERT INTO submissions (
                student_id, assignment_id, file_name,
                original_name, submitted_at, resubmission_allowed
            )
            VALUES (?, ?, ?, ?, ?, 0)
        """, (
            student_id, assignment_id, file_name, original_name,
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
    try:
        row = connection.execute("""
            SELECT * FROM submissions
            WHERE student_id = ? AND assignment_id = ?
            ORDER BY id DESC LIMIT 1
        """, (student_id, assignment_id)).fetchone()
        return dict(row) if row else None
    finally:
        connection.close()


def get_student_submissions_for_dashboard(student_id):
    connection = get_connection()
    try:
        rows = connection.execute("""
            SELECT
                sub.*,
                a.title AS assignment_title,
                a.semester,
                m.marks_obtained,
                m.max_marks,
                m.feedback
            FROM submissions sub
            JOIN assignments a ON a.id = sub.assignment_id
            LEFT JOIN marks m ON m.submission_id = sub.id
            WHERE sub.student_id = ?
            ORDER BY sub.id DESC
        """, (student_id,)).fetchall()
        return [dict(row) for row in rows]
    finally:
        connection.close()


def get_submissions_for_assignment_semester(assignment_id, semester):
    connection = get_connection()
    try:
        rows = connection.execute("""
            SELECT
                sub.*,
                s.name,
                s.name AS student_name,
                s.register_number,
                s.semester,
                a.semester AS assignment_semester
            FROM submissions sub
            JOIN students s ON s.id = sub.student_id
            JOIN assignments a ON a.id = sub.assignment_id
            WHERE sub.assignment_id = ?
              AND s.semester = ?
              AND a.semester = ?
            ORDER BY sub.id
        """, (assignment_id, semester, semester)).fetchall()
        return [dict(row) for row in rows]
    finally:
        connection.close()


def get_submissions_by_semester(semester):
    connection = get_connection()
    try:
        query = """
            SELECT
                sub.*,
                s.name,
                s.register_number,
                s.semester,
                a.title AS assignment_title,
                a.semester AS assignment_semester
            FROM submissions sub
            JOIN students s ON s.id = sub.student_id
            JOIN assignments a ON a.id = sub.assignment_id
        """
        if semester == "all":
            rows = connection.execute(
                query + " ORDER BY sub.submitted_at DESC"
            ).fetchall()
        else:
            rows = connection.execute(query + """
                WHERE s.semester = ? AND a.semester = ?
                ORDER BY sub.submitted_at DESC
            """, (int(semester), int(semester))).fetchall()
        return [dict(row) for row in rows]
    finally:
        connection.close()


def get_submissions_for_assignment(assignment_id):
    connection = get_connection()
    try:
        rows = connection.execute("""
            SELECT
                sub.*,
                s.name AS student_name,
                s.register_number,
                s.semester,
                m.marks_obtained,
                m.max_marks,
                m.feedback
            FROM submissions sub
            JOIN students s ON s.id = sub.student_id
            LEFT JOIN marks m ON m.submission_id = sub.id
            WHERE sub.assignment_id = ?
            ORDER BY sub.id
        """, (assignment_id,)).fetchall()
        return [dict(row) for row in rows]
    finally:
        connection.close()


# ---------------- MARKS AND FEEDBACK ----------------

def save_marks(submission_id, marks_obtained, max_marks, feedback):
    connection = get_connection()
    try:
        connection.execute("""
            INSERT INTO marks (
                submission_id, marks_obtained, max_marks,
                feedback, evaluated_at
            )
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(submission_id) DO UPDATE SET
                marks_obtained = excluded.marks_obtained,
                max_marks = excluded.max_marks,
                feedback = excluded.feedback,
                evaluated_at = excluded.evaluated_at
        """, (
            submission_id, marks_obtained, max_marks,
            feedback, datetime.now().isoformat()
        ))

        row = connection.execute("""
            SELECT s.id AS student_id, u.id AS user_id, a.title
            FROM submissions sub
            JOIN students s ON s.id = sub.student_id
            JOIN users u ON u.student_id = s.id
            JOIN assignments a ON a.id = sub.assignment_id
            WHERE sub.id = ?
        """, (submission_id,)).fetchone()

        if row:
            connection.execute("""
                INSERT INTO notifications (user_id, title, message)
                VALUES (?, ?, ?)
            """, (
                row["user_id"],
                "Assignment evaluated",
                f"Your assignment '{row['title']}' has been evaluated."
            ))

        connection.commit()
        return True
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


# ---------------- NOTIFICATIONS ----------------

def add_notification(user_id, title, message):
    connection = get_connection()
    try:
        connection.execute("""
            INSERT INTO notifications (user_id, title, message)
            VALUES (?, ?, ?)
        """, (user_id, title, message))
        connection.commit()
    finally:
        connection.close()


def notify_semester_students(semester, title, message):
    connection = get_connection()
    try:
        rows = connection.execute("""
            SELECT u.id
            FROM users u
            JOIN students s ON s.id = u.student_id
            WHERE s.semester = ?
        """, (semester,)).fetchall()

        for row in rows:
            connection.execute("""
                INSERT INTO notifications (user_id, title, message)
                VALUES (?, ?, ?)
            """, (row["id"], title, message))

        connection.commit()
    finally:
        connection.close()


def get_notifications(user_id):
    connection = get_connection()
    try:
        rows = connection.execute("""
            SELECT * FROM notifications
            WHERE user_id = ?
            ORDER BY id DESC LIMIT 30
        """, (user_id,)).fetchall()
        return [dict(row) for row in rows]
    finally:
        connection.close()


def mark_notifications_read(user_id):
    connection = get_connection()
    try:
        connection.execute("""
            UPDATE notifications SET is_read = 1
            WHERE user_id = ?
        """, (user_id,))
        connection.commit()
    finally:
        connection.close()


# ---------------- SIMILARITY REPORTS ----------------

def save_similarity_results(assignment_id, results):
    connection = get_connection()
    try:
        invalidate_similarity_report(connection, assignment_id)

        assignment = connection.execute("""
            SELECT semester FROM assignments WHERE id = ?
        """, (assignment_id,)).fetchone()

        if not assignment:
            raise ValueError("Assignment not found")

        for item in results:
            valid = connection.execute("""
                SELECT COUNT(*) AS total FROM students
                WHERE id IN (?, ?) AND semester = ?
            """, (
                item["student1_id"],
                item["student2_id"],
                assignment["semester"]
            )).fetchone()["total"]

            if valid != 2:
                continue

            connection.execute("""
                INSERT INTO similarity_results (
                    assignment_id, student1_id,
                    student2_id, similarity_percent
                )
                VALUES (?, ?, ?, ?)
            """, (
                assignment_id,
                item["student1_id"],
                item["student2_id"],
                item.get("similarity_percent", item.get("similarity", 0))
            ))

        connection.execute("""
            INSERT INTO similarity_report_runs
            (assignment_id, generated_at)
            VALUES (?, ?)
        """, (assignment_id, datetime.now().isoformat()))

        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def get_similarity_results(assignment_id):
    connection = get_connection()
    try:
        rows = connection.execute("""
            SELECT
                sr.student1_id,
                s1.name AS student1_name,
                s1.register_number AS student1_register,
                s1.semester AS semester1,
                sr.student2_id,
                s2.name AS student2_name,
                s2.register_number AS student2_register,
                s2.semester AS semester2,
                sr.similarity_percent
            FROM similarity_results sr
            JOIN assignments a ON a.id = sr.assignment_id
            JOIN students s1 ON s1.id = sr.student1_id
            JOIN students s2 ON s2.id = sr.student2_id
            WHERE sr.assignment_id = ?
              AND s1.semester = a.semester
              AND s2.semester = a.semester
            ORDER BY sr.similarity_percent DESC
        """, (assignment_id,)).fetchall()
        return [dict(row) for row in rows]
    finally:
        connection.close()


# ---------------- GRAPH ANALYSIS ----------------

def get_graph_data_by_semester(semester):
    connection = get_connection()
    try:
        query = """
            SELECT
                s1.name AS student1,
                s2.name AS student2,
                s1.register_number AS student1_register,
                s2.register_number AS student2_register,
                a.semester,
                sr.similarity_percent
            FROM similarity_results sr
            JOIN assignments a ON a.id = sr.assignment_id
            JOIN students s1 ON s1.id = sr.student1_id
            JOIN students s2 ON s2.id = sr.student2_id
            WHERE s1.semester = a.semester
              AND s2.semester = a.semester
        """
        if semester == "all":
            rows = connection.execute(
                query + " ORDER BY sr.similarity_percent DESC"
            ).fetchall()
        else:
            rows = connection.execute(
                query + """
                    AND a.semester = ?
                    ORDER BY sr.similarity_percent DESC
                """, (int(semester),)
            ).fetchall()
        return [dict(row) for row in rows]
    finally:
        connection.close()


def get_dashboard_data():
    connection = get_connection()
    try:
        return {
            "total_students": connection.execute(
                "SELECT COUNT(*) FROM students"
            ).fetchone()[0],
            "total_assignments": connection.execute(
                "SELECT COUNT(*) FROM assignments"
            ).fetchone()[0],
            "total_submissions": connection.execute(
                "SELECT COUNT(*) FROM submissions"
            ).fetchone()[0],
            "recent_assignments": connection.execute("""
                SELECT * FROM assignments
                ORDER BY id DESC LIMIT 10
            """).fetchall()
        }
    finally:
        connection.close()


if __name__ == "__main__":
    init_db()
    print("Database ready:", DB_PATH)
