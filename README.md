
# Logical Books - A Simple Bookkeeping Application

## Introduction

Logical Books is a simple, self-hosted bookkeeping application designed for personal or small business use. It provides core accounting features in a straightforward web interface, allowing you to manage your finances with ease. The application is built with a Python Flask backend and a modern, responsive frontend powered by Bootstrap.

## Features

*   **Multi-Client Support:** Manage finances for multiple, separate entities. Each client has its own chart of accounts, journal entries, and import templates.
*   **Chart of Accounts:** Create, read, update, and delete accounts. Accounts are grouped by type (Asset, Liability, Equity, Income, Expense).
*   **Journal Entries:** Manually enter transactions into a searchable journal. You can also edit and delete entries individually or in bulk.
*   **Transaction Types:** Classify transactions as Income, Expense, or Internal Transfer for more accurate reporting.
*   **CSV Imports:** Import transactions from multiple CSV files at once. The application supports customizable templates to map columns from your bank's export format to the application's fields. This includes support for single-column (positive/negative) and dual-column (debit/credit) amount formats.
*   **Transaction Categorization:** Assign categories to your transactions for better tracking and analysis.
*   **General Ledger:** View a summary of each account's activity, including opening and closing balances, debits, credits, and the year-to-date net change.
*   **Income Statement:** Generate a simple profit and loss report showing total income, total expenses, and net income.
*   **Balance Sheet:** View a snapshot of your financial position with a report on your assets, liabilities, and equity.
*   **Budgeting:** Set monthly budgets for different expense categories and track your spending against them.
*   **Database Migrations:** Your data is safe! The application uses Flask-Migrate to manage database schema changes without deleting your data.

## How it Works

### Backend

The backend is a Python application built with the Flask web framework. It uses Flask-SQLAlchemy to interact with a SQLite database, which stores all of the application's data. The application is designed to be self-contained and easy to run.

### Frontend

The frontend is built with a modern, responsive design using the Bootstrap framework. It uses a base template to provide consistent navigation and a clean user interface across all devices.

### Database

The application uses a single SQLite database file (`bookkeeping.db`) to store all of its data. The database schema is managed by Flask-Migrate, which allows for easy updates and changes without data loss.

## Getting Started

1.  **Installation:**
    *   Clone the repository.
    *   Create a Python virtual environment: `python3 -m venv venv`
    *   Activate the virtual environment: `source venv/bin/activate`
    *   Install the required packages: `pip install -r requirements.txt`

2.  **Database Setup:**
    *   Initialize the database: `flask db upgrade`

3.  **Running the Application:**
    *   Run the application: `./run.sh`
    *   Open your web browser and navigate to `http://127.0.0.1:5000`.

## Testing

The application includes a test suite using `pytest` to ensure core functionalities are working as expected and to prevent regressions.

To run the tests:

1.  Activate your virtual environment: `source venv/bin/activate`
2.  Navigate to the project's root directory.
3.  Run the tests: `python3 -m pytest`

## Future Improvements

*   **User Authentication:** Add user accounts and authentication to secure the application.
*   **Recurring Transactions:** Add the ability to create recurring journal entries.
