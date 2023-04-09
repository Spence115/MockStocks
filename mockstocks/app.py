import os
import sqlite3
import datetime

from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.security import check_password_hash, generate_password_hash
from helpers import apology, login_required, lookup, usd

# NOTE: use the following to use the data provided by IEX.
#       Replace KEY with your own key
# export API_KEY=KEY

## The following is the schema of the database 'finance.db' being used in this app.               ##
## The variables shown after each table are used for data fetching/writing with the SQL database  ##
## which provides clarity about what data is being queried                                        ##

# CREATE TABLE users (
#     id INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
#     username TEXT NOT NULL,
#     hash TEXT NOT NULL,
#     cash NUMERIC NOT NULL DEFAULT 10000.00
#     );

users_id_ind, users_username_ind, users_hash_ind, users_cash_ind = range(4)

# CREATE TABLE sqlite_sequence(name,seq);
# CREATE UNIQUE INDEX username ON users (username);

# CREATE TABLE history (
#   transaction_id INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
#   user_id INTEGER NOT NULL,
#   order_type TEXT NOT NULL CHECK (order_type IN ('sell', 'buy')),
#   ticker TEXT NOT NULL,
#   shares NUMERIC NOT NULL,
#   price NUMERIC NOT NULL,
#   timestamp DATETIME NOT NULL
# );

history_transaction_id_ind, history_user_id_ind, history_order_type_ind, history_ticker_ind, history_shares_ind, history_price_ind, history_timestamp_ind = range(7)

# CREATE TABLE portfolio (
#   holding_id INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
#   user_id INTEGER NOT NULL,
#   symbol TEXT NOT NULL,
#   company TEXT NOT NULL,
#   total_shares NUMERIC NOT NULL
# );

portfolio_holding_id_ind, portfolio_user_id_ind, portfolio_symbol_ind, portfolio_company_ind, portfolio_total_shares_ind = range(5)

# Configure application
app = Flask(__name__)

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""

    try:
        # Connect to the SQL database
        dbcon = sqlite3.connect("finance.db")
        sql_cursor = dbcon.cursor()

        # Global indices for SQL
        global portfolio_symbol_ind, portfolio_company_ind, portfolio_total_shares_ind

        # Lists to be appended to down below
        ticker = []
        company = []
        tot_shares = []
        price_per_share = []
        holding_price = []

        # Gets portfolio info for user that is logged in
        holdings = sql_cursor.execute("SELECT * FROM portfolio WHERE user_id = ? ORDER BY symbol ASC",
                                      (session.get('user_id'),)).fetchall()

        # Populates all the lists with all data relevant to each holding
        for i in range(len(holdings)):
            ticker.append(holdings[i][portfolio_symbol_ind])
            company.append(holdings[i][portfolio_company_ind])
            tot_shares.append(holdings[i][portfolio_total_shares_ind])
            # Individual share price
            stockInfo = lookup(ticker[i])
            price_per_share.append(stockInfo["price"])
            # Total holding price
            holding_price.append(tot_shares[i] * stockInfo["price"])

        funds = sql_cursor.execute("SELECT cash FROM users WHERE id = ?", (session.get('user_id'),)).fetchone()
        user = sql_cursor.execute("SELECT username FROM users WHERE id = ?", (session.get('user_id'),)).fetchone()

        # Ensure the user exists before proceeding
        if user is not None:
            username = user[0]
        else:
            return apology("User not found", 400)

        # Account value summary
        user_cash = funds[0]
        stock_value = sum(holding_price)
        account_value = usd(user_cash + stock_value)

        return render_template("index.html", username=username, ticker=ticker, company=company, tot_shares=tot_shares,
                                price_per_share=price_per_share, holding_price=holding_price,
                                user_cash=user_cash, stock_value=stock_value, account_value=account_value)

    finally:
        # Close database connection
        sql_cursor.close()


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""

    try:
        # Connect to the SQL database
        dbcon = sqlite3.connect("finance.db")
        sql_cursor = dbcon.cursor()

        global portfolio_symbol_ind

        # User reached route via POST (as by submitting a form via POST)
        if request.method == "POST":

            # Ensure symbol was populated
            if not request.form.get("symbol"):
                return apology("must provide ticker symbol", 400)

            # Ensure shares field was populated
            if not request.form.get("shares"):
                return apology("must provide number of shares to purchase", 400)

            # Stock that user wants to purchase
            ticker = request.form.get("symbol")

            # Ensure shares is numeric
            try:
                # Number of shares user wants to purchase
                shares = float(request.form.get("shares"))
            except (ValueError):
                return apology("Invalid, shares must be numeric", 400)

            # Ensure shares are not 0 or negative numbers
            if shares < 1:
                return apology("Invalid, purchased shares must be great than value of 0", 400)

            # Ensure shares is a whole number
            if shares % 1 != 0:
                return apology("cannot buy fractional shares", 400)

            # Dictionary for user's desired stock info
            stockDict = lookup(ticker)

            # Ensure ticker symbol actually exists
            if not stockDict:
                return apology("not a valid ticker symbol", 400)

            # Stores stock info into corresponding variables
            stockName = stockDict["name"]
            stockPrice = stockDict["price"]
            stockSymbol = stockDict["symbol"]

            # User's total cash prior to purchase
            funds = sql_cursor.execute("SELECT cash FROM users WHERE id = ?", (session.get('user_id'),)).fetchone()

            # Checks if user has enough funds for transaction
            # funds[0]["cash"] extracts first element from funds list to get actual cash number
            #   Ex: funds[0]["cash"] = 10000, whereas funds = [{'cash': 10000}]
            if funds[0] < (stockPrice * shares):
                return apology("insufficient funds", 400)

            else:
                # Formats timestamp before inserting into database
                formatted_timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

                # Record stock purchase in history table
                sql_cursor.execute("INSERT INTO history (user_id, order_type, ticker, shares, price, timestamp) VALUES(?, ?, ?, ?, ?, ?)",
                                   (session.get('user_id'), 'buy', stockSymbol, shares, stockPrice, formatted_timestamp,))
                dbcon.commit()

                # Checks to see if user already owns shares of a stock they are purchasing
                exists = sql_cursor.execute("SELECT symbol FROM portfolio WHERE user_id = ? AND symbol = ?",
                                            (session.get('user_id'), stockSymbol),).fetchone()

                # If they already own shares of this type of stock, add number of purchased shares to existing shares in user's portfolio
                if exists and exists[0] == stockSymbol:
                    currentShares = sql_cursor.execute(
                        "SELECT total_shares FROM portfolio WHERE user_id = ? AND symbol = ?", (session.get('user_id'), stockSymbol,)).fetchone()
                    newShares = currentShares[0] + shares
                    sql_cursor.execute("UPDATE portfolio SET total_shares = ? WHERE user_id = ? AND symbol = ?",
                                       (newShares, session.get('user_id'), stockSymbol,))
                    dbcon.commit()
                # Else, create a new row in user's portfolio for tracking this stock's info
                else:
                    sql_cursor.execute("INSERT INTO portfolio (user_id, symbol, company, total_shares) VALUES (?, ?, ?, ?)",
                                       (session.get('user_id'), stockSymbol, stockName, shares,))
                    dbcon.commit()

                # Subtracts the total cost from the user's cash
                newCash = funds[0] - (stockPrice * shares)
                sql_cursor.execute("UPDATE users SET cash = ? WHERE id = ?", (newCash, session.get('user_id'),))
                dbcon.commit()

            # Redirect user to the hompage once purchase complete
            return redirect("/")

        # User reached route via GET (as by clicking a link or via redirect)
        else:
            return render_template("buy.html")

    finally:
        # Close database connection
        sql_cursor.close()


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""

    try:
        # Connect to the SQL database
        dbcon = sqlite3.connect("finance.db")
        sql_cursor = dbcon.cursor()

        # Indices used for SQL
        global history_order_type_ind, history_ticker_ind, history_shares_ind, history_price_ind, history_timestamp_ind

        # Lists to be appended to down below
        order_type = []
        ticker = []
        shares = []
        price_per_share = []
        transaction_price = []
        timestamp = []

        # Gets historical info for user that is logged in
        records = sql_cursor.execute("SELECT * FROM history WHERE user_id = ? ORDER BY timestamp DESC",
                                     (session.get('user_id'),)).fetchall()

        if not records:
            return apology("no transaction history on this account", 400)

        # Populates all the lists with all data relevant to each transaction
        for i in range(len(records)):
            order_type.append(records[i][history_order_type_ind])
            ticker.append(records[i][history_ticker_ind])
            shares.append(records[i][history_shares_ind])
            price_per_share.append(records[i][history_price_ind])
            transaction_price.append((records[i][history_shares_ind] * records[i][history_price_ind]))
            timestamp.append((records[i][history_timestamp_ind]))

        # Get's account username
        user = sql_cursor.execute("SELECT username FROM users WHERE id = ?", (session.get('user_id'),)).fetchone()
        username = user[0]

        return render_template("history.html", order_type=order_type, ticker=ticker, shares=shares,
                                price_per_share=price_per_share, transaction_price=transaction_price,
                                timestamp=timestamp, username=username)

    finally:
        # Close database connection
        sql_cursor.close()


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    try:
        # Connect to the SQL database
        dbcon = sqlite3.connect("finance.db")
        sql_cursor = dbcon.cursor()

        # Index for SQL
        global users_id_ind

        # Forget any user_id
        session.clear()

        # User reached route via POST (as by submitting a form via POST)
        if request.method == "POST":

            # Ensure username was submitted
            if not request.form.get("username"):
                return apology("must provide username", 400)

            # Ensure password was submitted
            elif not request.form.get("password"):
                return apology("must provide password", 400)

            # Query database for username
            rows = sql_cursor.execute("SELECT * FROM users WHERE username = ?", (request.form.get("username"),)).fetchall()

            # Ensure username exists and password is correct
            if len(rows) != 1 or not check_password_hash(rows[0][2], request.form.get("password")):
                return apology("invalid username and/or password", 400)

            # Remember which user has logged in
            session["user_id"] = rows[0][users_id_ind]

            # Redirect user to home page
            return redirect("/")

        # User reached route via GET (as by clicking a link or via redirect)
        else:
            return render_template("login.html")

    finally:
        # Close database connection
        sql_cursor.close()


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure symbol was submitted
        if not request.form.get("symbol"):
            return apology("must provide ticker symbol for quote", 400)

        # Stock that user wants to lookup
        ticker = request.form.get("symbol")

        # Dictionary for user's desired stock info
        stockDict = lookup(ticker)

        # Ensure ticker symbol actually exists
        if not stockDict:
            return apology("not a valid ticker symbol", 400)

        # Stores stock info in session objects
        session['stockName'] = stockDict["name"]
        session['stockPrice'] = usd(stockDict["price"])
        session['stockSymbol'] = stockDict["symbol"]

        # Render quoted template with looked up info
        return redirect("/quoted.html")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("quote.html")


@app.route("/quoted.html")
@login_required
def quoted():
    """Provide quoted stock price."""

    # Retrieve session data for stock info
    stockName = session.get('stockName')
    stockPrice = session.get('stockPrice')
    stockSymbol = session.get('stockSymbol')
    # Pass data into html file and render it
    return render_template("quoted.html", name=stockName, price=stockPrice, ticker=stockSymbol)


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""

    try:
        # Connect to the SQL database
        dbcon = sqlite3.connect("finance.db")
        sql_cursor = dbcon.cursor()

        # Forget any user_id
        session.clear()

        # User reached route via POST (as by submitting a form via POST)
        if request.method == "POST":

            # Loads user's new account info
            newUsername = request.form.get("username")
            newPass = request.form.get("password")
            newPassConf = request.form.get("confirmation")

            # For checking dupes in database
            query = sql_cursor.execute("SELECT * FROM users WHERE username = ?", (newUsername,)).fetchall()

            # Ensure username was submitted
            if not request.form.get("username"):
                return apology("must provide username", 400)

            # Ensure's username does not already exist
            elif len(query) > 0:
                return apology("username already exists", 400)

            # Ensure password was submitted
            elif not request.form.get("password"):
                return apology("must provide password", 400)

            # Ensure password confirmation was submitted
            elif not request.form.get("confirmation"):
                return apology("must confirm password", 400)

            # Ensure password matches password confirmation
            elif newPass != newPassConf:
                return apology("password does not match password confirmation", 400)

            # Ensure password is over 8 chars long
            elif len(newPass) < 8:
                return apology("password too short - must be at least 8 characters long", 400)

            # Ensure password is within max length
            elif len(newPass) > 26:
                return apology("password too long - must be within 26 characters long", 400)

            # Ensure password meets the following criteria:
            # - Contains at least 2 letters
            # - Contains at least 2 numbers
            # - Contains at least 1 special character
            passDict = {'letters': 0, 'numbers': 0, 'special': 0}
            for j in newPass:
                if j.isalpha():
                    passDict['letters'] += 1
                elif j.isdigit():
                    passDict['numbers'] += 1
                else:
                    passDict['special'] += 1

            if passDict['letters'] < 2:
                return apology("password must contain at least 2 letters", 400)
            elif passDict['numbers'] < 2:
                return apology("password must contain at least 2 numbers", 400)
            elif passDict['special'] < 1:
                return apology("password must contain at 1 special character", 400)

            # Hashes user's new password
            hashPass = generate_password_hash(newPass, method='pbkdf2:sha256', salt_length=8)

            # Adds new user to the database
            sql_cursor.execute("INSERT INTO users (username, hash) VALUES(?, ?)", (newUsername, hashPass,))
            dbcon.commit()

            # Redirect user to home page
            return redirect("/")

        # User reached route via GET (as by clicking a link or via redirect)
        else:
            return render_template("register.html")

    finally:
        # Close database connection
        sql_cursor.close()


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""

    try:
        # Connect to the SQL database
        dbcon = sqlite3.connect("finance.db")
        sql_cursor = dbcon.cursor()

        # Indices for SQL
        global portfolio_total_shares_ind, portfolio_symbol_ind

        # User reached route via POST (as by submitting a form via POST)
        if request.method == "POST":

            # Ensure symbol was populated
            if not request.form.get("symbol"):
                return apology("must provide ticker symbol", 400)

            # Ensure shares field was populated
            if not request.form.get("shares"):
                return apology("must provide number of shares to purchase", 400)

            # Fetches relevant user info in order to process selling of stocks
            user_id = session.get('user_id')
            symbol = request.form.get("symbol")
            shares = float(request.form.get("shares"))

            # Ensures shares are not 0 or negative numbers
            if shares < 1:
                return apology("Invalid, purchased shares must be great than value of 0", 400)

            # Dictionary for user's desired stock info
            stockDict = lookup(symbol)

            # Ensure ticker symbol actually exists
            if not stockDict:
                return apology("not a valid ticker symbol", 400)

            # Stores stock info into corresponding variables
            stockName = stockDict["name"]
            stockPrice = stockDict["price"]
            stockSymbol = stockDict["symbol"]

            # Selects all of user's available stocks
            holdings = sql_cursor.execute("SELECT * FROM portfolio WHERE user_id = ? AND symbol = ?",
                                          (user_id, stockSymbol,)).fetchall()

            # Informs user if they do not own stock and returns apology
            if not holdings:
                return apology("you do not own any shares of this stock", 400)

            current_shares = holdings[0][portfolio_total_shares_ind]

            # Ensure user has sufficient shares to complete sell order
            if shares > current_shares:
                return apology("not enough shares to complete transaction", 400)

            # Updates user's portfolio accordingly
            sql_cursor.execute("UPDATE portfolio SET total_shares = total_shares - ? WHERE user_id = ? AND symbol = ?",
                               (shares, user_id, stockSymbol,))
            dbcon.commit()

            # Adds cash gains to user's total cash in account
            gains = shares * stockPrice
            sql_cursor.execute("UPDATE users SET cash = cash + ? WHERE id = ?", (gains, user_id,))
            dbcon.commit()

            # Formats timestamp before inserting into database
            formatted_timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            # Record transaction into history table
            sql_cursor.execute("INSERT INTO history (user_id, order_type, ticker, shares, price, timestamp) VALUES(?, ?, ?, ?, ?, ?)",
                               (user_id, 'sell', stockSymbol, shares, stockPrice, formatted_timestamp,))
            dbcon.commit()

            # Redirect user to the hompage once purchase complete
            return redirect("/")

        # User reached route via GET (as by clicking a link or via redirect)
        else:

            # Lists to be appended to down below
            ticker = []

            # Gets historical info for user that is logged in
            symbols = sql_cursor.execute("SELECT * FROM portfolio WHERE user_id = ?", (session.get('user_id'),)).fetchall()

            if not symbols:
                return apology("you don't own any shares", 400)

            # Fills ticker with all stocks types that user owns. To be using in dropdown for sell page
            for i in range(len(symbols)):
                ticker.append(symbols[i][portfolio_symbol_ind])

            return render_template("sell.html", ticker=ticker)

    finally:
        # Close database connection
        sql_cursor.close()
