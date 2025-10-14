
from flask import Flask, render_template, request
import sqlite3
import cv2
import base64
import re

app = Flask(__name__)

DB = "palm_pay.db"

def init_db():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            account_number TEXT UNIQUE NOT NULL,
            phone TEXT,
            address TEXT,
            account_type TEXT,
            pin TEXT NOT NULL,
            balance REAL DEFAULT 0 NOT NULL,
            hand_image BLOB
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_number TEXT NOT NULL,
            type TEXT NOT NULL,
            amount REAL NOT NULL,
            balance_after REAL NOT NULL,
            note TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        )
    ''')
    conn.commit()
    conn.close()

def get_user(acc):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT id, name, account_number, phone, address, account_type, pin, balance, hand_image FROM users WHERE account_number=?", (acc,))
    row = c.fetchone()
    conn.close()
    return row

def authenticate(acc, pin):
    if pin is None:
        return False
    pin = str(pin).strip()
    if not re.fullmatch(r"\d{4}", pin):
        return False
    u = get_user(acc)
    if not u:
        return False
    return str(u[6]).strip() == pin

def set_balance(acc, new_bal):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("UPDATE users SET balance=? WHERE account_number=?", (new_bal, acc))
    conn.commit()
    conn.close()

def add_txn(acc, ttype, amount, balance_after, note=""):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute(
        "INSERT INTO transactions (account_number, type, amount, balance_after, note) VALUES (?, ?, ?, ?, ?)",
        (acc, ttype, float(amount), float(balance_after), note)
    )
    conn.commit()
    conn.close()

init_db()

@app.route("/")
def home():
    return render_template("home.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return render_template("register.html", message=None)
    name = request.form.get("name","").strip()
    account_number = request.form.get("account_number","").strip()
    phone = request.form.get("phone","").strip()
    address = request.form.get("address","").strip()
    account_type = request.form.get("account_type","").strip()
    pin = str(request.form.get("pin","")).strip()

    errors = []
    if not name or not account_number or not pin:
        errors.append("Name, Account Number and PIN are required.")
    if not re.fullmatch(r"\d{4}", pin):
        errors.append("PIN must be exactly 4 digits.")
    if errors:
        return render_template("register.html", message=" ".join(errors))

    cap = cv2.VideoCapture(0)
    hand_image = None
    while True:
        ret, frame = cap.read()
        cv2.imshow("PalmPay - Press 's' to save hand image, 'q' to cancel", frame)
        key = cv2.waitKey(1)
        if key == ord('s'):
            hand_image = cv2.imencode('.png', frame)[1].tobytes()
            break
        elif key == ord('q'):
            break
    cap.release()
    cv2.destroyAllWindows()

    if hand_image is None:
        return render_template("register.html", message="Hand image not captured. Press 's' to save.")

    try:
        conn = sqlite3.connect(DB)
        c = conn.cursor()
        c.execute(
            "INSERT INTO users (name, account_number, phone, address, account_type, pin, hand_image, balance) VALUES (?, ?, ?, ?, ?, ?, ?, 0)",
            (name, account_number, phone, address, account_type, pin, hand_image)
        )
        conn.commit()
        conn.close()
        return render_template("register.html", message="Registration successful! Use the navbar to Deposit, Withdraw or Transfer.")
    except sqlite3.IntegrityError:
        return render_template("register.html", message="Account number already exists. Try a different one.")

@app.route("/users")
def users():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT id, name, account_number, balance, hand_image FROM users ORDER BY id DESC")
    rows = c.fetchall()
    conn.close()
    processed = []
    for r in rows:
        img_b64 = base64.b64encode(r[4]).decode("utf-8") if r[4] else ""
        processed.append((r[0], r[1], r[2], r[3], img_b64))
    return render_template("users.html", users=processed)

@app.route("/deposit", methods=["GET", "POST"])
def deposit():
    if request.method == "GET":
        return render_template("deposit.html", message=None)
    acc = request.form.get("account_number","").strip()
    pin = request.form.get("pin","").strip()
    amt = request.form.get("amount","0").strip()

    user = get_user(acc)
    if not user:
        return render_template("deposit.html", message="Account not found. Please register first.")

    if not authenticate(acc, pin):
        return render_template("deposit.html", message="Invalid PIN.")

    try:
        amount = float(amt)
        if amount <= 0:
            return render_template("deposit.html", message="Amount must be greater than 0.")
    except ValueError:
        return render_template("deposit.html", message="Invalid amount.")

    new_balance = float(user[7]) + amount
    set_balance(acc, new_balance)
    add_txn(acc, "deposit", amount, new_balance, "Cash deposit")
    return render_template("deposit.html", message=f"Deposit successful. New balance: {new_balance:.2f}")

@app.route("/withdraw", methods=["GET", "POST"])
def withdraw():
    if request.method == "GET":
        return render_template("withdraw.html", message=None)
    acc = request.form.get("account_number","").strip()
    pin = request.form.get("pin","").strip()
    amt = request.form.get("amount","0").strip()

    user = get_user(acc)
    if not user:
        return render_template("withdraw.html", message="Account not found. Please register first.")

    if not authenticate(acc, pin):
        return render_template("withdraw.html", message="Invalid PIN.")

    try:
        amount = float(amt)
        if amount <= 0:
            return render_template("withdraw.html", message="Amount must be greater than 0.")
    except ValueError:
        return render_template("withdraw.html", message="Invalid amount.")

    if float(user[7]) < amount:
        return render_template("withdraw.html", message="Insufficient balance.")
    new_balance = float(user[7]) - amount
    set_balance(acc, new_balance)
    add_txn(acc, "withdraw", amount, new_balance, "Cash withdrawal")
    return render_template("withdraw.html", message=f"Withdrawal successful. New balance: {new_balance:.2f}")

@app.route("/transfer", methods=["GET", "POST"])
def transfer():
    if request.method == "GET":
        return render_template("transfer.html", message=None)
    from_acc = request.form.get("from_account","").strip()
    pin = request.form.get("pin","").strip()
    to_acc = request.form.get("to_account","").strip()
    amt = request.form.get("amount","0").strip()

    sender = get_user(from_acc)
    receiver = get_user(to_acc)
    if not sender:
        return render_template("transfer.html", message="Sender account not found.")
    if not receiver:
        return render_template("transfer.html", message="Receiver account not found.")
    if not authenticate(from_acc, pin):
        return render_template("transfer.html", message="Invalid PIN.")

    try:
        amount = float(amt)
        if amount <= 0:
            return render_template("transfer.html", message="Amount must be greater than 0.")
    except ValueError:
        return render_template("transfer.html", message="Invalid amount.")

    if float(sender[7]) < amount:
        return render_template("transfer.html", message="Insufficient balance in sender account.")

    new_sender_bal = float(sender[7]) - amount
    set_balance(from_acc, new_sender_bal)
    add_txn(from_acc, "transfer_out", amount, new_sender_bal, f"To {to_acc}")

    new_receiver_bal = float(receiver[7]) + amount
    set_balance(to_acc, new_receiver_bal)
    add_txn(to_acc, "transfer_in", amount, new_receiver_bal, f"From {from_acc}")

    return render_template("transfer.html", message=f"Transferred {amount:.2f} from {from_acc} to {to_acc}. Sender new balance: {new_sender_bal:.2f}")

@app.route("/balance", methods=["GET", "POST"])
def balance():
    if request.method == "GET":
        return render_template("balance.html", message=None)
    acc = request.form.get("account_number","").strip()
    pin = request.form.get("pin","").strip()

    user = get_user(acc)
    if not user:
        return render_template("balance.html", message="Account not found. Please register first.")
    if not authenticate(acc, pin):
        return render_template("balance.html", message="Invalid PIN.")

    return render_template("balance.html", message=f"Your current balance is: {float(user[7]):.2f}")

@app.route("/history", methods=["GET", "POST"])
def history():
    if request.method == "GET":
        return render_template("history.html", message=None, txns=[])
    acc = request.form.get("account_number","").strip()
    pin = request.form.get("pin","").strip()

    user = get_user(acc)
    if not user:
        return render_template("history.html", message="Account not found.", txns=[])
    if not authenticate(acc, pin):
        return render_template("history.html", message="Invalid PIN.", txns=[])

    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute('''
        SELECT type, amount, balance_after, note, created_at
        FROM transactions
        WHERE account_number=?
        ORDER BY id DESC
        LIMIT 100
    ''', (acc,))
    rows = c.fetchall()
    conn.close()
    return render_template("history.html", message=f"Showing last {len(rows)} transactions for {acc}.", txns=rows)

if __name__ == "__main__":
    app.run(debug=True)
