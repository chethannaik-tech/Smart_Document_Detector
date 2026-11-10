
from flask import (
    Flask, render_template, request,
    redirect, url_for, flash, session,
    send_from_directory, abort
)

from functools import wraps
from werkzeug.utils import secure_filename
from pypdf import PdfReader
from difflib import SequenceMatcher

import os
import uuid
import re
import hashlib

from database import (
    init_db,
    get_dashboard_data,
    get_connection,
    add_student,
    get_all_students,
    get_all_assignments,
    create_user,
    verify_user,
    get_student_by_register_number,
    add_submission,
    get_student_submissions,
    get_all_submissions,
    get_submission_by_id,
    get_submission_for_student_assignment,
    allow_resubmission,
    update_submission_file,
    get_submissions_for_assignment,
    get_assignments_due_for_similarity,
    save_similarity_report,
    get_similarity_report,
    get_similarity_report_run
)


# ==========================================
# FLASK CONFIGURATION
# ==========================================

app = Flask(__name__)

app.secret_key = os.environ.get(
    "FLASK_SECRET_KEY",
    "change-this-local-development-key"
)

UPLOAD_FOLDER = os.path.join(
    app.root_path,
    "instance",
    "uploads"
)

ALLOWED_EXTENSIONS = {"pdf"}

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

init_db()


# ==========================================
# FILE VALIDATION
# ==========================================

def allowed_file(filename):

    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS
    )


# ==========================================
# TEACHER ACCESS PROTECTION
# ==========================================

def teacher_required(function):

    @wraps(function)
    def wrapper(*args, **kwargs):

        if "user_id" not in session:
            return redirect(url_for("teacher_login"))

        if session.get("role") != "teacher":

            flash("Teacher access only!", "error")

            return redirect(url_for("student_dashboard"))

        return function(*args, **kwargs)

    return wrapper


# ==========================================
# STUDENT ACCESS PROTECTION
# ==========================================

def student_required(function):

    @wraps(function)
    def wrapper(*args, **kwargs):

        if "user_id" not in session:
            return redirect(url_for("student_login"))

        if session.get("role") != "student":

            flash("Student access only!", "error")

            return redirect(url_for("teacher_dashboard"))

        return function(*args, **kwargs)

    return wrapper


# ==========================================
# PDF HASH GENERATION
# ==========================================

def get_pdf_hash(file_path):

    try:

        sha256 = hashlib.sha256()

        with open(file_path, "rb") as pdf_file:

            for chunk in iter(
                lambda: pdf_file.read(8192),
                b""
            ):

                sha256.update(chunk)

        return sha256.hexdigest()

    except OSError:

        app.logger.exception("PDF hash generation failed")

        return None


# ==========================================
# PDF TEXT EXTRACTION
# ==========================================

def extract_pdf_text(file_name):

    file_path = os.path.join(
        app.config["UPLOAD_FOLDER"],
        file_name
    )

    if not os.path.isfile(file_path):
        return ""

    try:

        reader = PdfReader(file_path)

        if reader.is_encrypted:
            return ""

        extracted_pages = []

        for page in reader.pages:

            page_text = page.extract_text() or ""

            extracted_pages.append(page_text)

        text = " ".join(extracted_pages)

        # Normalize text
        text = text.lower()

        text = re.sub(
            r"\s+",
            " ",
            text
        )

        text = text.strip()

        return text

    except Exception:

        app.logger.exception(
            "PDF text extraction failed: %s",
            file_name
        )

        return ""


# ==========================================
# TEXT SIMILARITY CALCULATION
# ==========================================

def calculate_similarity(text1, text2):

    # Exact extracted text match
    if text1 == text2:
        return 100.0

    words1 = text1.split()
    words2 = text2.split()

    if not words1 or not words2:
        return 0.0

    similarity = SequenceMatcher(
        None,
        words1,
        words2,
        autojunk=False
    ).ratio() * 100

    return round(similarity, 2)


# ==========================================
# SIMILARITY DETECTION
# ==========================================

def generate_similarity_report_for_assignment(assignment_id):

    submissions = get_submissions_for_assignment(
        assignment_id
    )

    valid_submissions = []

    # Extract text and hash from each PDF
    for submission in submissions:

        file_name = submission["file_name"]

        file_path = os.path.join(
            app.config["UPLOAD_FOLDER"],
            file_name
        )

        if not os.path.isfile(file_path):
            continue

        pdf_hash = get_pdf_hash(file_path)

        if pdf_hash is None:
            continue

        extracted_text = extract_pdf_text(file_name)

        # Ignore image-only or unreadable PDFs
        if not extracted_text:
            continue

        valid_submissions.append({
            "student_id": submission["student_id"],
            "text": extracted_text,
            "hash": pdf_hash
        })

    comparisons = []

    # Compare each unique pair
    for first_index in range(len(valid_submissions)):

        for second_index in range(
            first_index + 1,
            len(valid_submissions)
        ):

            first = valid_submissions[first_index]

            second = valid_submissions[second_index]

            # Same exact PDF file
            if first["hash"] == second["hash"]:

                similarity = 100.0

            else:

                similarity = calculate_similarity(
                    first["text"],
                    second["text"]
                )

            comparisons.append({

                "student1_id": first["student_id"],

                "student2_id": second["student_id"],

                "similarity_percent": similarity

            })

    # Save report
    save_similarity_report(
        assignment_id,
        comparisons
    )

    return (
        len(valid_submissions),
        len(comparisons)
    )


# ==========================================
# HOME PAGE
# ==========================================

@app.route("/")
def home():

    if session.get("role") == "teacher":

        return redirect(
            url_for("teacher_dashboard")
        )

    if session.get("role") == "student":

        return redirect(
            url_for("student_dashboard")
        )

    return render_template("home.html")


# ==========================================
# TEACHER LOGIN
# ==========================================

@app.route("/teacher-login", methods=["GET", "POST"])
def teacher_login():

    if request.method == "POST":

        username = request.form.get(
            "username", ""
        ).strip()

        password = request.form.get(
            "password", ""
        )

        user = verify_user(
            username,
            password
        )

        if user and user["role"] == "teacher":

            session.clear()

            session["user_id"] = user["id"]

            session["username"] = user["username"]

            session["role"] = "teacher"

            return redirect(
                url_for("teacher_dashboard")
            )

        flash(
            "Invalid teacher username or password!",
            "error"
        )

    return render_template("teacher_login.html")


# ==========================================
# STUDENT LOGIN
# ==========================================

@app.route("/student-login", methods=["GET", "POST"])
def student_login():

    if request.method == "POST":

        username = request.form.get(
            "username", ""
        ).strip()

        password = request.form.get(
            "password", ""
        )

        user = verify_user(
            username,
            password
        )

        if user and user["role"] == "student":

            session.clear()

            session["user_id"] = user["id"]

            session["username"] = user["username"]

            session["role"] = "student"

            return redirect(
                url_for("student_dashboard")
            )

        flash(
            "Invalid student username or password!",
            "error"
        )

    return render_template("student_login.html")


# ==========================================
# STUDENT REGISTRATION
# ==========================================

@app.route("/register-student", methods=["GET", "POST"])
def register_student():

    if request.method == "POST":

        name = request.form.get(
            "name", ""
        ).strip()

        register_number = request.form.get(
            "register_number", ""
        ).strip()

        department = request.form.get(
            "department", ""
        ).strip()

        password = request.form.get(
            "password", ""
        )

        confirm_password = request.form.get(
            "confirm_password", ""
        )

        if not all([
            name,
            register_number,
            department,
            password
        ]):

            flash(
                "Please fill all details!",
                "error"
            )

        elif password != confirm_password:

            flash(
                "Passwords do not match!",
                "error"
            )

        elif len(password) < 8:

            flash(
                "Password must contain at least 8 characters!",
                "error"
            )

        else:

            success = add_student(
                name,
                register_number,
                department
            )

            if success:

                user_created = create_user(
                    register_number,
                    password,
                    "student"
                )

                if user_created:

                    flash(
                        "Registration successful! Please login.",
                        "success"
                    )

                    return redirect(
                        url_for("student_login")
                    )

                connection = get_connection()

                connection.execute(
                    """
                    DELETE FROM students
                    WHERE register_number = ?
                    """,
                    (register_number,)
                )

                connection.commit()

                connection.close()

                flash(
                    "Username already exists!",
                    "error"
                )

            else:

                flash(
                    "Register number already exists!",
                    "error"
                )

    return render_template(
        "register_student.html"
    )


# ==========================================
# TEACHER DASHBOARD
# ==========================================

@app.route("/teacher")
@teacher_required
def teacher_dashboard():

    due_assignments = get_assignments_due_for_similarity()

    for assignment in due_assignments:

        try:

            generate_similarity_report_for_assignment(
                assignment["id"]
            )

        except Exception:

            app.logger.exception(
                "Automatic similarity check failed"
            )

    data = get_dashboard_data()

    return render_template(
        "dashboard.html",
        data=data
    )


# ==========================================
# CREATE ASSIGNMENT
# ==========================================

@app.route(
    "/create-assignment",
    methods=["GET", "POST"]
)
@teacher_required
def create_assignment():

    if request.method == "POST":

        title = request.form.get(
            "title", ""
        ).strip()

        description = request.form.get(
            "description", ""
        )

        start_date = request.form.get(
            "start_date", ""
        )

        end_date = request.form.get(
            "end_date", ""
        )

        try:

            max_pages = int(
                request.form.get("max_pages", 30)
            )

            threshold = int(
                request.form.get("threshold", 40)
            )

            if not title:

                raise ValueError(
                    "Assignment title is required."
                )

            if not 1 <= max_pages <= 30:

                raise ValueError(
                    "Maximum pages must be between 1 and 30."
                )

            if not 0 <= threshold <= 100:

                raise ValueError(
                    "Threshold must be between 0 and 100."
                )

            if not start_date or not end_date:

                raise ValueError(
                    "Please select both dates."
                )

            if end_date <= start_date:

                raise ValueError(
                    "End date must be after start date."
                )

            connection = get_connection()

            try:

                connection.execute(
                    """
                    INSERT INTO assignments
                    (
                        title,
                        description,
                        start_date,
                        end_date,
                        max_pages,
                        similarity_threshold
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        title,
                        description,
                        start_date,
                        end_date,
                        max_pages,
                        threshold
                    )
                )

                connection.commit()

            finally:

                connection.close()

            flash(
                "Assignment created successfully!",
                "success"
            )

            return redirect(
                url_for("teacher_dashboard")
            )

        except ValueError as error:

            flash(
                str(error),
                "error"
            )

    return render_template(
        "create_assignment.html"
    )


# ==========================================
# VIEW STUDENTS
# ==========================================

@app.route("/students")
@teacher_required
def students():

    student_list = get_all_students()

    return render_template(
        "students.html",
        students=student_list
    )


# ==========================================
# STUDENT DASHBOARD
# ==========================================

@app.route("/student")
@student_required
def student_dashboard():

    assignments = get_all_assignments()

    student = get_student_by_register_number(
        session.get("username")
    )

    if student is None:
        abort(404)

    submissions = get_student_submissions(
        student["id"]
    )

    return render_template(
        "student_dashboard.html",
        username=session.get("username"),
        assignments=assignments,
        submissions=submissions
    )


# ==========================================
# STUDENT ASSIGNMENT UPLOAD
# ==========================================

@app.route(
    "/submit-assignment",
    methods=["GET", "POST"]
)
@student_required
def submit_assignment():

    assignments = get_all_assignments()

    student = get_student_by_register_number(
        session.get("username")
    )

    if student is None:
        abort(404)

    selected_assignment_id = request.args.get(
        "assignment_id",
        type=int
    )

    if request.method == "POST":

        assignment_id = request.form.get(
            "assignment_id",
            type=int
        )

        uploaded_file = request.files.get("file")

        if not assignment_id or not uploaded_file:

            flash(
                "Please select an assignment and PDF file!",
                "error"
            )

            return redirect(
                url_for("submit_assignment")
            )

        if uploaded_file.filename == "":

            flash(
                "Please select a PDF file!",
                "error"
            )

            return redirect(
                url_for(
                    "submit_assignment",
                    assignment_id=assignment_id
                )
            )

        if not allowed_file(uploaded_file.filename):

            flash(
                "Only PDF files are allowed!",
                "error"
            )

            return redirect(
                url_for(
                    "submit_assignment",
                    assignment_id=assignment_id
                )
            )

        # Verify assignment
        connection = get_connection()

        try:

            assignment = connection.execute(
                """
                SELECT *
                FROM assignments
                WHERE id = ?
                """,
                (assignment_id,)
            ).fetchone()

        finally:

            connection.close()

        if assignment is None:

            flash(
                "Invalid assignment selected!",
                "error"
            )

            return redirect(
                url_for("student_dashboard")
            )

        # Check existing submission
        existing_submission = get_submission_for_student_assignment(
            student["id"],
            assignment["id"]
        )

        if existing_submission is not None:

            if not existing_submission["resubmission_allowed"]:

                flash(
                    "You have already submitted this assignment. "
                    "Wait for teacher permission to upload again.",
                    "error"
                )

                return redirect(
                    url_for("student_dashboard")
                )

        # Check PDF signature
        file_content = uploaded_file.read(5)

        uploaded_file.seek(0)

        if file_content != b"%PDF-":

            flash(
                "The selected file is not a valid PDF!",
                "error"
            )

            return redirect(
                url_for(
                    "submit_assignment",
                    assignment_id=assignment_id
                )
            )

        # Validate PDF page count
        try:

            pdf_reader = PdfReader(uploaded_file)

            if pdf_reader.is_encrypted:

                flash(
                    "Password-protected PDFs are not allowed!",
                    "error"
                )

                return redirect(
                    url_for(
                        "submit_assignment",
                        assignment_id=assignment_id
                    )
                )

            page_count = len(pdf_reader.pages)

            uploaded_file.seek(0)

        except Exception:

            flash(
                "Unable to read this PDF file!",
                "error"
            )

            return redirect(
                url_for(
                    "submit_assignment",
                    assignment_id=assignment_id
                )
            )

        if page_count == 0:

            flash(
                "Empty PDF files are not allowed!",
                "error"
            )

            return redirect(
                url_for(
                    "submit_assignment",
                    assignment_id=assignment_id
                )
            )

        if page_count > assignment["max_pages"]:

            flash(
                f"Your PDF contains {page_count} pages. "
                f"Maximum allowed pages: {assignment['max_pages']}.",
                "error"
            )

            return redirect(
                url_for(
                    "submit_assignment",
                    assignment_id=assignment_id
                )
            )

        # Save uploaded PDF
        original_name = secure_filename(
            uploaded_file.filename
        )

        unique_name = str(uuid.uuid4()) + ".pdf"

        save_path = os.path.join(
            app.config["UPLOAD_FOLDER"],
            unique_name
        )

        uploaded_file.save(save_path)

        try:

            if existing_submission is None:

                add_submission(
                    student["id"],
                    assignment["id"],
                    unique_name,
                    original_name
                )

                message = (
                    "Assignment submitted successfully!"
                )

            else:

                old_file_name = existing_submission["file_name"]

                updated = update_submission_file(
                    existing_submission["id"],
                    unique_name,
                    original_name
                )

                if not updated:

                    raise Exception(
                        "Resubmission permission is not active."
                    )

                old_path = os.path.join(
                    app.config["UPLOAD_FOLDER"],
                    old_file_name
                )

                if os.path.isfile(old_path):
                    os.remove(old_path)

                message = (
                    "Corrected PDF submitted successfully!"
                )

            flash(
                message,
                "success"
            )

            return redirect(
                url_for("student_dashboard")
            )

        except Exception:

            if os.path.exists(save_path):
                os.remove(save_path)

            app.logger.exception(
                "Submission save failed"
            )

            flash(
                "Unable to submit assignment. Please try again.",
                "error"
            )

            return redirect(
                url_for("student_dashboard")
            )

    return render_template(
        "submit_assignment.html",
        assignments=assignments,
        selected_assignment_id=selected_assignment_id
    )


# ==========================================
# TEACHER VIEW SUBMISSIONS
# ==========================================

@app.route("/teacher-submissions")
@teacher_required
def teacher_submissions():

    submissions = get_all_submissions()

    return render_template(
        "teacher_submissions.html",
        submissions=submissions
    )


# ==========================================
# ALLOW RESUBMISSION
# ==========================================

@app.route(
    "/allow-resubmission/<int:submission_id>",
    methods=["POST"]
)
@teacher_required
def teacher_allow_resubmission(submission_id):

    submission = get_submission_by_id(
        submission_id
    )

    if submission is None:
        abort(404)

    if submission["resubmission_allowed"]:

        flash(
            "Resubmission is already allowed for this student.",
            "error"
        )

    else:

        success = allow_resubmission(
            submission_id
        )

        if success:

            flash(
                "Resubmission permission granted successfully!",
                "success"
            )

        else:

            flash(
                "Unable to grant resubmission permission.",
                "error"
            )

    return redirect(
        url_for("teacher_submissions")
    )


# ==========================================
# MANUAL SIMILARITY CHECK
# ==========================================

@app.route(
    "/check-similarity/<int:assignment_id>",
    methods=["POST"]
)
@teacher_required
def check_similarity(assignment_id):

    connection = get_connection()

    try:

        assignment = connection.execute(
            """
            SELECT *
            FROM assignments
            WHERE id = ?
            """,
            (assignment_id,)
        ).fetchone()

    finally:

        connection.close()

    if assignment is None:
        abort(404)

    try:

        valid_count, comparison_count = (
            generate_similarity_report_for_assignment(
                assignment_id
            )
        )

        flash(
            f"Similarity check completed! "
            f"{valid_count} readable PDF submissions checked "
            f"and {comparison_count} comparisons generated.",
            "success"
        )

    except Exception:

        app.logger.exception(
            "Manual similarity check failed"
        )

        flash(
            "Unable to generate similarity report. "
            "Please check the PDF files.",
            "error"
        )

    return redirect(
        url_for(
            "similarity_report",
            assignment_id=assignment_id
        )
    )


# ==========================================
# SIMILARITY REPORT
# ==========================================

@app.route(
    "/similarity-report/<int:assignment_id>"
)
@teacher_required
def similarity_report(assignment_id):

    connection = get_connection()

    try:

        assignment = connection.execute(
            """
            SELECT *
            FROM assignments
            WHERE id = ?
            """,
            (assignment_id,)
        ).fetchone()

    finally:

        connection.close()

    if assignment is None:
        abort(404)

    results = get_similarity_report(
        assignment_id
    )

    report_run = get_similarity_report_run(
        assignment_id
    )

    submissions = get_submissions_for_assignment(
        assignment_id
    )

    return render_template(
        "similarity_report.html",
        assignment=assignment,
        results=results,
        report_run=report_run,
        submissions=submissions
    )


# ==========================================
# DOWNLOAD SUBMISSION
# ==========================================

@app.route(
    "/download-submission/<int:submission_id>"
)
@teacher_required
def download_submission(submission_id):

    submission = get_submission_by_id(
        submission_id
    )

    if submission is None:
        abort(404)

    file_path = os.path.join(
        app.config["UPLOAD_FOLDER"],
        submission["file_name"]
    )

    if not os.path.isfile(file_path):
        abort(404)

    download_name = (
        submission["original_name"]
        or "assignment.pdf"
    )

    return send_from_directory(
        app.config["UPLOAD_FOLDER"],
        submission["file_name"],
        as_attachment=True,
        download_name=download_name
    )


# ==========================================
# LOGOUT
# ==========================================

@app.route("/logout")
def logout():

    session.clear()

    flash(
        "You have logged out successfully!",
        "success"
    )

    return redirect(
        url_for("home")
    )


# ==========================================
# FILE TOO LARGE ERROR
# ==========================================

@app.errorhandler(413)
def file_too_large(error):

    flash(
        "File is too large. Maximum upload size is 50 MB.",
        "error"
    )

    if session.get("role") == "student":

        return redirect(
            url_for("submit_assignment")
        )

    return redirect(
        url_for("home")
    )


# ==========================================
# RUN APPLICATION
# ==========================================

if __name__ == "__main__":

    app.run(debug=True)
