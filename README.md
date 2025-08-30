
# Logical Books - A Simple Bookkeeping Application

## Introduction

Logical Books is a simple, self-hosted bookkeeping application designed for personal or small business use. It provides core accounting features in a straightforward web interface, allowing you to manage your finances with ease. The application is built with a Python Flask backend and a modern, responsive frontend powered by Bootstrap.

For a detailed guide on how to use the application, please see the [TUTORIAL.md](TUTORIAL.md) file.

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
*   **Statement of Cash Flows:** Shows how cash is moving in and out of the business.
*   **Budgeting:** Set monthly budgets for different expense categories and track your spending against them.
*   **Fixed Asset Management:** Track fixed assets and automatically calculate and record depreciation.
*   **Inventory Management:** Track inventory levels and automatically create journal entries for sales and cost of goods sold.
*   **Accrual Accounting:** Create and manage accruals with automatic reversing entries.
*   **Recurring Transactions:** Automatically detect and manage recurring transactions.
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
    *   Install the required packages: `./venv/bin/python3 -m pip install -r requirements.txt`

2.  **Database Setup:**
    *   Initialize the database: `./venv/bin/python3 -m flask db upgrade`

3.  **Running the Application:**
    *   **Development:** `./run_dev.sh`
    *   Open your web browser and navigate to `http://127.0.0.1:5000`.

## Testing

The application includes a test suite using `pytest` to ensure core functionalities are working as expected and to prevent regressions.

To run the tests:

1.  Navigate to the project's root directory.
2.  Run the tests: `./venv/bin/python3 -m pytest`

## Deployment to EC2 (Debian/Ubuntu)

This section outlines how to deploy the Logical Books application to a Debian-based EC2 instance using Gunicorn and Nginx for a production-ready setup.

### Prerequisites on EC2

Ensure your EC2 instance has SSH access and basic system updates applied.

### Deployment Steps

1.  **Transfer the Deployment Script:**
    Copy the `setup_prod_server.sh` script (provided separately) to your EC2 instance.

2.  **Update Repository URL in Script:**
    Open `setup_prod_server.sh` and replace `https://github.com/LukeL152/logical-books_flask.git` with the actual HTTPS URL of your GitHub repository.

3.  **Connect to EC2 and Run Setup Script:**
    SSH into your EC2 instance and execute the script:

    ```bash
    # Make the script executable
    chmod +x setup_prod_server.sh

    # Run the deployment script
    ./setup_prod_server.sh
    ```

    This script will:
    *   Install necessary system dependencies (Python, `venv`, `git`, `build-essential`, Nginx).
    *   Clone your application from GitHub to `/var/www/logical-books`.
    *   Set up a Python virtual environment and install all required packages.
    *   Run database migrations.
    *   Generate a unique `SECRET_KEY` for your Flask application.
    *   Configure and enable a `systemd` service for Gunicorn to run your Flask app.
    *   Configure and enable Nginx as a reverse proxy, serving your application on port 80.

### Updating an Existing Deployment

To update an already deployed application, use the `update.sh` script:

```bash
# Navigate to the application directory
cd /var/www/logical-books

# Run the update script
./update.sh
```
This script will pull the latest changes, update dependencies, run migrations, and instruct you to restart the systemd service.

### Accessing Your Application

After the setup or update completes successfully, your application should be accessible via your EC2 instance's public IP address in a web browser.

## Recent Enhancements

*   **Corrected Balance Sheet Calculation:** The Balance Sheet now accurately reflects Total Equity by including Net Income (Revenue - Expenses), ensuring your books are always balanced.
*   **Enhanced Transaction Rule Editing:** You can now directly specify Debit and Credit accounts when creating or editing transaction rules, providing more precise automation for your journal entries.
*   **Standardized Development Scripts:** All development and deployment scripts (`run_dev.sh`, `update.sh`, `create_migration.sh`, `setup_prod_server.sh`) have been standardized to use explicit virtual environment paths, improving robustness and consistency. The redundant `run_prod.sh` script has been removed.
*   **New Database Migration Workflow:** A new `create_migration.sh` script has been introduced to enforce a linear and conflict-free database migration history, preventing "multiple heads" errors.

## Future Improvements

*   **Multi-Currency Support:** Manage accounts and transactions in multiple currencies.
*   **Budgeting vs. Actuals Reporting:** Enhanced reporting on budget vs. actuals with variance analysis.
*   **User Roles and Permissions:** Control access to different parts of the application.
*   **Attachments:** Attach files, such as receipts and invoices, to journal entries and transactions.
*   **Financial Projections:** Create financial projections based on historical data and user-defined assumptions.
*   **Integration with Payment Gateways:** Automatically import transaction data from payment gateways like Stripe and PayPal.
*   **Mobile App:** A mobile app for iOS and Android to access financial data on the go.
