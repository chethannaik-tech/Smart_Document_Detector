from database import init_db, get_connection, create_user
from getpass import getpass

init_db()

connection = get_connection()

teacher_exists = connection.execute(
    "SELECT id FROM users WHERE role = 'teacher' LIMIT 1"
).fetchone()

connection.close()

if teacher_exists:
    print("A teacher account already exists.")
else:
    print("\n--- CREATE TEACHER ACCOUNT ---")

    username = input("Enter teacher username: ").strip()

    password = getpass("Create teacher password: ")
    confirm_password = getpass("Confirm teacher password: ")

    if not username or not password:
        print("Username and password cannot be empty.")

    elif password != confirm_password:
        print("Passwords do not match.")

    elif len(password) < 8:
        print("Password must contain at least 8 characters.")

    else:
        success = create_user(username, password, "teacher")

        if success:
            print("\nTeacher account created successfully!")
            print("You can now use this account to log in.")
        else:
            print("This username already exists.")