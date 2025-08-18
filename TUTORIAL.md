
# Logical Books Tutorial

## 1. Introduction

### What is Logical Books?

Logical Books is a web-based bookkeeping application built with Python's Flask framework. It provides a comprehensive set of features for managing financial data, including client management, fiscal year management, account management, journal entry management, data import, rule-based categorization, financial reporting, budgeting, and inter-account transfers.

### Who is it for?

Logical Books is designed for small business owners, freelancers, and accountants who need a simple yet powerful tool to manage their finances. It is also a great tool for students who are learning about accounting and bookkeeping.

## 2. Getting Started

### Installation

To get started with Logical Books, you will need to have Python 3.x installed on your computer. You can download the latest version of Python from the official website: [https://www.python.org/downloads/](https://www.python.org/downloads/)

Once you have Python installed, you can clone the Logical Books repository from GitHub:

```bash
git clone https://github.com/LukeL152/logical-books_flask.git
```

Next, navigate to the `logical-books` directory and install the required dependencies:

```bash
cd logical-books
pip install -r requirements.txt
```

Finally, run the application:

```bash
./run.sh
```

The application will be available at `http://127.0.0.1:5000/`.

### Creating a Client

When you first launch Logical Books, you will be prompted to create a new client. A client can be a person, a company, or any other entity for which you want to track financial data. To create a new client, simply enter a name for the client and click the "Create Client" button.

Once you have created a client, you can select it from the list of clients to start managing its financial data.

## 3. Chart of Accounts

### What is a Chart of Accounts?

The chart of accounts is a list of all the financial accounts of a business. It is used to classify and record financial transactions. The chart of accounts is organized into five main categories:

*   **Assets:** What the business owns.
*   **Liabilities:** What the business owes.
*   **Equity:** The owner's stake in the business.
*   **Revenue:** The income the business earns from its operations.
*   **Expenses:** The costs the business incurs to generate revenue.

### Adding and Editing Accounts

To add a new account to the chart of accounts, click on the "Chart of Accounts" link in the navigation bar. Then, click the "Add Account" button and fill out the form. You will need to provide a name, a type, and an opening balance for the account.

You can also edit an existing account by clicking on the "Edit" button next to the account in the chart of accounts.

## 4. Managing Transactions

### Importing Transactions

Logical Books allows you to import transactions from a CSV file. To import transactions, click on the "Import" link in the navigation bar. Then, select the account for which you want to import transactions and choose a CSV file to upload.

You will need to create an import template to map the columns in your CSV file to the fields in Logical Books. To create a new template, click on the "Add Template" button and fill out the form.

### Manually Adding Transactions

You can also add transactions manually. To add a new transaction, click on the "Transactions" link in the navigation bar and then click the "Add Transaction" button. You will need to provide a date, a description, and an amount for the transaction.

### Approving Transactions

Once you have imported or manually added transactions, you will need to approve them before they are converted into journal entries. To approve transactions, click on the "Unapproved Transactions" link in the "Journal" dropdown menu. Then, select the debit and credit accounts for each transaction and click the "Approve Selected Transactions" button.

## 5. Journal Entries

### Viewing Journal Entries

To view the journal entries, click on the "Journal Entries" link in the "Journal" dropdown menu. The journal is a chronological record of all the financial transactions of a business.

### Adding and Editing Journal Entries

You can also add and edit journal entries manually. To add a new journal entry, click on the "Add Entry" button on the journal page. To edit an existing journal entry, click on the "Edit" button next to the entry in the journal.

## 6. Financial Statements

Logical Books can generate the following financial statements:

*   **Income Statement:** Shows the company's financial performance over a period of time.
*   **Balance Sheet:** Shows the company's financial position at a specific point in time.
*   **Statement of Cash Flows:** Shows how cash is moving in and out of the business.

To view the financial statements, click on the corresponding link in the navigation bar.

## 7. Fixed Assets and Depreciation

### Adding Fixed Assets

To add a new fixed asset, click on the "Fixed Assets" link in the navigation bar. Then, click the "Add Fixed Asset" button and fill out the form. You will need to provide a name, a purchase date, a cost, a useful life, and a salvage value for the asset.

### Viewing the Depreciation Schedule

To view the depreciation schedule for a fixed asset, click on the "Depreciation Schedule" button next to the asset in the fixed assets list.

## 8. Inventory and Sales

### Adding Products

To add a new product, click on the "Products" link in the "Inventory" dropdown menu. Then, click the "Add Product" button and fill out the form. You will need to provide a name, a description, and a cost for the product.

### Managing Inventory

To view the inventory, click on the "Inventory" link in the "Inventory" dropdown menu. The inventory page shows the quantity of each product on hand.

### Recording Sales

To record a sale, click on the "Sales" link in the "Inventory" dropdown menu. Then, click the "Add Sale" button and fill out the form. You will need to provide a date, a product, a quantity, and a price for the sale.

When you record a sale, the inventory is automatically updated, and the corresponding journal entries are created for the sale and the cost of goods sold.

## 9. Accruals

### Adding Accruals

To add a new accrual, click on the "Accruals" link in the "Inventory" dropdown menu. Then, click the "Add Accrual" button and fill out the form. You will need to provide a date, a description, an amount, a debit account, and a credit account for the accrual.

### Automatic Reversal of Accruals

Accruals are automatically reversed at the beginning of the next accounting period. This ensures that the accruals are only recognized in the period in which they are incurred.

## 10. Reporting and KPIs

### Key Performance Indicators

Logical Books calculates and displays the following key performance indicators (KPIs):

*   **Gross Profit Margin:** The percentage of revenue that exceeds the cost of goods sold.
*   **Operating Profit Margin:** The percentage of revenue that is left after paying for variable costs of production.
*   **Net Profit Margin:** The percentage of revenue that is left after all expenses, including taxes and interest, have been deducted.
*   **Current Ratio:** Measures the company's ability to pay short-term obligations.
*   **Debt-to-Equity Ratio:** Measures the company's financial leverage.

### Exporting Data

You can export the following data to a CSV file:

*   Ledger
*   Income Statement
*   Balance Sheet

To export data, click on the "Export to CSV" button on the corresponding page.
