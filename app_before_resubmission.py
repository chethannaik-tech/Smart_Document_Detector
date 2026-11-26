
import os
from datetime import datetime

import pdfplumber
from flask import (
    Flask, render_template, request, redirect,
    url_for, session, flash, send_from_directory, abort
)
from werkzeug.utils import secure_filename

from database import *
from similarity_engine import compare_documents


# ==========================================
# FLASK APPLICATION CONFIGURATION
# ==========================================

app = Flask(__name__)

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "change-this-secret-key-before-deployment"
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024

ALLOWED_EXTENSIONS = {"pdf"}

# Initialize database when Gunicorn imports app.py.
init_db()


# ==========================================
# FILE HANDLING
# ==========================================

def allowed_file(filename):
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS
    )


def extract_pdf_text(filepath):
    try:
        text = ""

        with pdfplumber.open(filepath) as pdf:
            for page in pdf.pages:
                text += (page.extract_text() or "") + "\n"

        return text

    except Exception as error:
        print("PDF extraction error:", error)
        return ""


def get_pdf_page_count(filepath):
    try:
        with pdfplumber.open(filepath) as pdf:
            return len(pdf.pages)
    except Exception:
        return 0


# ==========================================
# SIMILARITY REPORT GENERATION
# ==========================================

def generate_similarity_report_for_assignment(assignment_id):

    assignment = get_assignment_by_id(assignment_id)

    if not assignment:
        return []

    submissions = get_submissions_for_assignment_semester(
        assignment_id, assignment["semester"]
    )

    documents = []

    for submission in submissions:

        filepath = os.path.join(
            UPLOAD_FOLDER,
            os.path.basename(submission["file_name"])
        )

        if not os.path.isfile(filepath):
            continue

        extracted_text = extract_pdf_text(filepath)

        if extracted_text.strip():
            documents.append({
                "student_id": submission["student_id"],
                "text": extracted_text
            })

    results = []

    for i in range(len(documents)):
        for j in range(i + 1, len(documents)):

            analysis = compare_documents(
                documents[i]["text"],
                documents[j]["text"]
            )

            results.append({
                "student1_id": documents[i]["student_id"],
                "student2_id": documents[j]["student_id"],
                "similarity_percent": analysis["similarity_score"]
            })

    save_similarity_results(assignment_id, results)

    return results


# ==========================================
# AUTHORIZATION
# ==========================================

def teacher_required():
    if session.get("role") != "teacher":
        flash("Teacher login required.")
        return False
    return True


def student_required():
    if session.get("role") != "student":
        flash("Student login required.")
        return False
    return True


# ==========================================
# HOME
# ==========================================

@app.route("/")
def home():

    if "user_id" not in session:
        return redirect(url_for("login"))

    if session.get("role") == "teacher":
        return redirect(url_for("teacher_dashboard"))

    if session.get("role") == "student":
        return redirect(url_for("student_dashboard"))

    session.clear()
    return redirect(url_for("login"))


# ==========================================
# LOGIN
# ==========================================

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        user = authenticate_user(username, password)

        if user:

            session.clear()

            session["user_id"] = user["id"]
            session["role"] = user["role"]
            session["username"] = user["username"]

            if user["role"] == "teacher":
                return redirect(url_for("teacher_dashboard"))

            if user["role"] == "student":
                return redirect(url_for("student_dashboard"))

            session.clear()
            flash("This account role is not supported.")

        else:
            flash("Invalid username or password.")

    return render_template("login.html")


# ==========================================
# STUDENT REGISTRATION
# ==========================================

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        name = request.form.get("name", "").strip()
        register_number = request.form.get(
            "register_number", ""
        ).strip()

        email = request.form.get("email", "").strip()
        department = request.form.get("department", "").strip()
        semester = request.form.get("semester", "")
        password = request.form.get("password", "")

        if not all([
            name, register_number, email,
            department, semester, password
        ]):
            flash("Please fill in all fields.")
            return redirect(url_for("register"))

        try:
            semester = int(semester)

            if semester not in range(1, 9):
                raise ValueError

        except ValueError:
            flash("Select a valid semester.")
            return redirect(url_for("register"))

        if len(password) < 6:
            flash("Password must contain at least 6 characters.")
            return redirect(url_for("register"))

        if create_student_account(
            name,
            register_number,
            email,
            department,
            semester,
            password
        ):
            flash("Registration successful. Please login.")
            return redirect(url_for("login"))

        flash("Register number or username already exists.")

    return render_template("register.html")


# ==========================================
# TEACHER DASHBOARD
# ==========================================

@app.route("/teacher-dashboard")
def teacher_dashboard():

    if not teacher_required():
        return redirect(url_for("login"))

    selected_semester = request.args.get("semester", "all")

    if selected_semester != "all":
        try:
            number = int(selected_semester)

            if number not in range(1, 9):
                raise ValueError

            selected_semester = str(number)

        except ValueError:
            selected_semester = "all"

    assignments = get_assignments_by_semester(selected_semester)
    students = get_students_by_semester(selected_semester)
    submissions = get_submissions_by_semester(selected_semester)
    stats = get_dashboard_data()

    return render_template(
        "dashboard.html",
        assignments=assignments,
        students=students,
        submissions=submissions,
        selected_semester=selected_semester,
        stats=stats
    )


# ==========================================
# CREATE ASSIGNMENT
# ==========================================

@app.route("/create-assignment", methods=["GET", "POST"])
def create_assignment():

    if not teacher_required():
        return redirect(url_for("login"))

    if request.method == "POST":

        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        subject = request.form.get("subject", "").strip()
        department = request.form.get("department", "").strip()
        semester = request.form.get("semester", "")

        start_date = request.form.get("start_date", "")
        end_date = request.form.get("end_date", "")

        max_pages = request.form.get("max_pages", "20")
        threshold = request.form.get("similarity_threshold", "50")
        max_marks = request.form.get("max_marks", "100")

        reference = request.files.get("reference_file")
        reference_filename = None

        try:
            semester = int(semester)
            max_pages = int(max_pages)
            threshold = float(threshold)
            max_marks = float(max_marks)

            if semester not in range(1, 9):
                raise ValueError

            if max_pages < 1:
                raise ValueError

            if not 0 <= threshold <= 100:
                raise ValueError

            if max_marks <= 0:
                raise ValueError

            if not title or not subject or not department:
                raise ValueError

            if not start_date or not end_date:
                raise ValueError

            if end_date < start_date:
                raise ValueError

        except ValueError:
            flash("Please enter valid assignment details.")
            return redirect(url_for("create_assignment"))

        if reference and reference.filename:

            if not allowed_file(reference.filename):
                flash("Reference file must be a PDF.")
                return redirect(url_for("create_assignment"))

            safe_name = secure_filename(reference.filename)

            reference_filename = (
                f"reference_{datetime.now().strftime('%Y%m%d%H%M%S%f')}_{safe_name}"
            )

            reference.save(
                os.path.join(UPLOAD_FOLDER, reference_filename)
            )

        assignment_id = create_assignment_record(
            title=title,
            description=description,
            semester=semester,
            start_date=start_date,
            end_date=end_date,
            max_pages=max_pages,
            threshold=threshold,
            subject=subject,
            department=department,
            reference_file=reference_filename,
            max_marks=max_marks,
            accepted_format="pdf",
            created_by=session["user_id"]
        )

        notify_semester_students(
            semester,
            "New assignment",
            f"New assignment '{title}' is available for Semester {semester}."
        )

        flash(f"Assignment created successfully. ID: {assignment_id}")

        return redirect(url_for("teacher_dashboard"))

    return render_template("create_assignment.html")


# ==========================================
# STUDENT DASHBOARD
# ==========================================

@app.route("/student-dashboard")
def student_dashboard():

    if not student_required():
        return redirect(url_for("login"))

    student = get_student_by_user_id(session["user_id"])

    if not student:
        session.clear()
        flash("Student profile not found.")
        return redirect(url_for("login"))

    assignments = get_student_semester_assignments(student["semester"])
    submissions = get_student_submissions_for_dashboard(student["id"])
    notifications = get_notifications(session["user_id"])

    submitted_ids = {
        item["assignment_id"] for item in submissions
    }

    pending_assignments = [
        item for item in assignments
        if item["id"] not in submitted_ids
    ]

    return render_template(
        "student_dashboard.html",
        student=student,
        assignments=assignments,
        submissions=submissions,
        pending_assignments=pending_assignments,
        notifications=notifications
    )


# ==========================================
# SUBMIT ASSIGNMENT
# ==========================================

@app.route("/submit/<int:assignment_id>", methods=["GET", "POST"])
def submit_assignment(assignment_id):

    if not student_required():
        return redirect(url_for("login"))

    student = get_student_by_user_id(session["user_id"])
    assignment = get_assignment_by_id(assignment_id)

    if not student or not assignment:
        flash("Student or assignment not found.")
        return redirect(url_for("student_dashboard"))

    if student["semester"] != assignment["semester"]:
        flash("You cannot submit another semester's assignment.")
        return redirect(url_for("student_dashboard"))

    existing = get_submission_for_student_assignment(
        student["id"], assignment_id
    )

    if request.method == "POST":

        file = request.files.get("file")

        if not file or not file.filename:
            flash("Please select a PDF file.")
            return redirect(url_for(
                "submit_assignment",
                assignment_id=assignment_id
            ))

        if not allowed_file(file.filename):
            flash("Only PDF files are accepted.")
            return redirect(url_for(
                "submit_assignment",
                assignment_id=assignment_id
            ))

        if existing:
            flash("You have already submitted this assignment.")
            return redirect(url_for("student_dashboard"))

        original_name = secure_filename(file.filename)

        unique_name = (
            f"student{student['id']}_assignment{assignment_id}_"
            f"{datetime.now().strftime('%Y%m%d%H%M%S%f')}_{original_name}"
        )

        filepath = os.path.join(UPLOAD_FOLDER, unique_name)
        file.save(filepath)

        page_count = get_pdf_page_count(filepath)

        if page_count == 0:
            os.remove(filepath)
            flash("Unable to read this PDF.")
            return redirect(url_for(
                "submit_assignment",
                assignment_id=assignment_id
            ))

        if page_count > assignment["max_pages"]:
            os.remove(filepath)
            flash(
                f"PDF exceeds the {assignment['max_pages']} page limit."
            )
            return redirect(url_for(
                "submit_assignment",
                assignment_id=assignment_id
            ))

        extracted_text = extract_pdf_text(filepath)

        if not extracted_text.strip():
            os.remove(filepath)
            flash("No readable text found in this PDF.")
            return redirect(url_for(
                "submit_assignment",
                assignment_id=assignment_id
            ))

        add_submission_record(
            student["id"],
            assignment_id,
            unique_name,
            original_name
        )

        flash("Assignment submitted successfully.")
        return redirect(url_for("student_dashboard"))

    return render_template(
        "submit_assignment.html",
        assignment=assignment,
        existing=existing
    )


# ==========================================
# MARKS AND FEEDBACK
# ==========================================

@app.route("/evaluate/<int:submission_id>", methods=["GET", "POST"])
def evaluate_submission(submission_id):

    if not teacher_required():
        return redirect(url_for("login"))

    connection = get_connection()

    try:
        row = connection.execute("""
            SELECT
                sub.*,
                s.name AS student_name,
                s.register_number,
                a.title AS assignment_title,
                a.max_marks AS assignment_max_marks,
                m.marks_obtained,
                m.feedback
            FROM submissions sub
            JOIN students s ON s.id = sub.student_id
            JOIN assignments a ON a.id = sub.assignment_id
            LEFT JOIN marks m ON m.submission_id = sub.id
            WHERE sub.id = %s
        """, (submission_id,)).fetchone()

        submission = dict(row) if row else None

    finally:
        connection.close()

    if not submission:
        flash("Submission not found.")
        return redirect(url_for("teacher_dashboard"))

    if request.method == "POST":

        try:
            marks = float(request.form.get("marks", ""))
            feedback = request.form.get("feedback", "").strip()

            maximum = float(
                submission["assignment_max_marks"] or 100
            )

            if marks < 0 or marks > maximum:
                raise ValueError

            save_marks(submission_id, marks, maximum, feedback)

            flash("Marks and feedback saved.")
            return redirect(url_for("teacher_dashboard"))

        except ValueError:
            flash("Enter valid marks within the maximum marks.")

    return render_template(
        "evaluate_submission.html",
        submission=submission
    )


# ==========================================
# REFERENCE FILE DOWNLOAD
# ==========================================

@app.route("/reference/<int:assignment_id>")
def download_reference(assignment_id):

    if session.get("role") not in ("teacher", "student"):
        return redirect(url_for("login"))

    assignment = get_assignment_by_id(assignment_id)

    if not assignment or not assignment.get("reference_file"):
        abort(404)

    if session.get("role") == "student":
        student = get_student_by_user_id(session["user_id"])

        if not student or student["semester"] != assignment["semester"]:
            abort(403)

    return send_from_directory(
        UPLOAD_FOLDER,
        os.path.basename(assignment["reference_file"]),
        as_attachment=True
    )


# ==========================================
# SIMILARITY ANALYSIS
# ==========================================

@app.route("/check-similarity/<int:assignment_id>", methods=["POST"])
def check_similarity(assignment_id):

    if not teacher_required():
        return redirect(url_for("login"))

    assignment = get_assignment_by_id(assignment_id)

    if not assignment:
        flash("Assignment not found.")
        return redirect(url_for("teacher_dashboard"))

    results = generate_similarity_report_for_assignment(assignment_id)

    flash(
        f"Similarity analysis completed. "
        f"{len(results)} document pairs compared."
    )

    return redirect(url_for(
        "teacher_dashboard",
        semester=assignment["semester"]
    ))


@app.route("/similarity-report/<int:assignment_id>")
def similarity_report(assignment_id):

    if not teacher_required():
        return redirect(url_for("login"))

    assignment = get_assignment_by_id(assignment_id)

    if not assignment:
        flash("Assignment not found.")
        return redirect(url_for("teacher_dashboard"))

    results = get_similarity_results(assignment_id)

    return render_template(
        "similarity_report.html",
        assignment=assignment,
        results=results
    )


# ==========================================
# GRAPH ANALYSIS
# ==========================================

@app.route("/graph-lab")
def graph_lab():

    if not teacher_required():
        return redirect(url_for("login"))

    semester = request.args.get("semester", "all")

    if semester != "all":
        try:
            number = int(semester)

            if number not in range(1, 9):
                raise ValueError

            semester = str(number)

        except ValueError:
            semester = "all"

    data = get_graph_data_by_semester(semester)

    return render_template(
        "graph_lab.html",
        data=data,
        selected_semester=semester
    )


# ==========================================
# NOTIFICATIONS
# ==========================================

@app.route("/notifications/read", methods=["POST"])
def read_notifications():

    if "user_id" not in session:
        return redirect(url_for("login"))

    mark_notifications_read(session["user_id"])

    if session.get("role") == "student":
        return redirect(url_for("student_dashboard"))

    return redirect(url_for("teacher_dashboard"))


# ==========================================
# DOWNLOAD SUBMISSIONS
# ==========================================

@app.route("/uploads/<path:filename>")
def download_file(filename):

    if session.get("role") not in ("teacher", "student"):
        return redirect(url_for("login"))

    return send_from_directory(
        UPLOAD_FOLDER,
        os.path.basename(filename),
        as_attachment=True
    )


# ==========================================
# LOGOUT
# ==========================================

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ==========================================
# ERROR HANDLING
# ==========================================

@app.errorhandler(413)
def file_too_large(error):

    flash("File too large. Maximum upload size is 50 MB.")

    if session.get("role") == "student":
        return redirect(url_for("student_dashboard"))

    return redirect(url_for("teacher_dashboard"))


# ==========================================
# LOCAL DEVELOPMENT
# ==========================================

if __name__ == "__main__":
    app.run(debug=True)
