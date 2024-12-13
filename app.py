import spacy
import dateparser
from flask import Flask, render_template, request, redirect, url_for
from mysql.connector import connect
from datetime import datetime, timedelta
import threading
import time
from plyer import notification
import pyttsx3
import re

# Initialize spaCy NLP model
nlp = spacy.load("en_core_web_sm")

app = Flask(__name__)

# Database connection
def db_connect():
    return connect(
        host="127.0.0.1",
        user="root",
        password="",
        database="task_manager"
    )

# Function to send notifications and voice reminders
def send_notification(message):
    try:
        engine = pyttsx3.init()
        voices = engine.getProperty('voices')
        engine.setProperty('voice', voices[1].id)  # Set to female voice
        engine.setProperty('rate', 150)
        engine.say(message)
        engine.runAndWait()

        notification.notify(
            title="Task Reminder",
            message=message,
            timeout=10
        )
    except Exception as e:
        print(f"Notification Error: {e}")

# Function to parse date and time from natural language
def parse_date_time(text):
    parsed_date = dateparser.parse(text)
    return parsed_date

# Background thread to check for reminders
def check_reminders():
    while True:
        current_time = datetime.now() 
        connection = db_connect()
        cursor = connection.cursor(dictionary=True)

        cursor.execute("SELECT * FROM task WHERE completed = 0")
        tasks = cursor.fetchall()

        for task in tasks:
            task_time = task['due_time']

            if task_time and isinstance(task_time, str):
                task_time = datetime.strptime(task_time, '%Y-%m-%d %H:%M:%S')

            if task_time and (task_time - current_time).total_seconds() <= 300 and not task['pre_reminder_sent']:
                send_notification(f"Reminder: {task['description']} is due soon!")
                cursor.execute("UPDATE task SET pre_reminder_sent = 1 WHERE id = %s", (task['id'],))

            if task_time and current_time >= task_time and not task['due_reminder_sent']:
                send_notification(f"Reminder: {task['description']} is due now!")
                cursor.execute("UPDATE task SET due_reminder_sent = 1 WHERE id = %s", (task['id'],))

            if task_time and current_time > task_time and not task['completed']:
                cursor.execute("UPDATE task SET completed = 1 WHERE id = %s", (task['id'],))

        connection.commit()
        cursor.close()
        connection.close()
        time.sleep(60)

# Start background thread for reminders
thread = threading.Thread(target=check_reminders, daemon=True)
thread.start()

@app.route('/')
def index():
    connection = db_connect()
    cursor = connection.cursor(dictionary=True)
    # Fetch all tasks ordered by completion status and due time
    cursor.execute("SELECT * FROM task ORDER BY completed ASC, due_time ASC")
    tasks = cursor.fetchall()
    cursor.close()
    connection.close()

    return render_template('index.html', tasks=tasks)

@app.route('/add_task', methods=['POST'])
def add_task():
    task_details = request.form['task_details']
    # Extract task description and due time from input
    match = re.match(r"(.*) at (.*)", task_details)

    if not match:
        return "Invalid input format. Please use 'task description at time/date'.", 400

    description = match.group(1).strip()
    time_str = match.group(2).strip()

    due_time = parse_date_time(time_str)
    if not due_time:
        return "Invalid time format. Please use '11 AM tomorrow' or '14/12/2024 at 11 AM'.", 400

    now = datetime.now()

    if "tomorrow" in time_str.lower():
        due_time = due_time.replace(year=now.year, month=now.month, day=now.day) + timedelta(days=1)
    elif "today" in time_str.lower() and due_time.date() == now.date():
        due_time = due_time.replace(year=now.year, month=now.month, day=now.day)
    elif due_time.date() < now.date():
        due_time = due_time.replace(year=now.year, month=now.month, day=now.day) + timedelta(days=1)

    connection = db_connect()
    cursor = connection.cursor()
    cursor.execute(
        "INSERT INTO task (description, due_time, completed, pre_reminder_sent, due_reminder_sent) VALUES (%s, %s, %s, %s, %s)",
        (description, due_time, 0, 0, 0)
    )
    connection.commit()
    cursor.close()
    connection.close()
    return redirect(url_for('index'))

@app.route('/delete_task/<int:task_id>', methods=['POST'])
def delete_task(task_id):
    connection = db_connect()
    cursor = connection.cursor()
    cursor.execute("DELETE FROM task WHERE id = %s", (task_id,))
    connection.commit()
    cursor.close()
    connection.close()
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)
