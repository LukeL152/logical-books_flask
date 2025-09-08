
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
./run_dev.sh
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

You can also add transactions manually. These are initially considered **unapproved transactions** and will need to be categorized into proper journal entries.

To add a new transaction, click on the "Transactions" link in the navigation bar and then click the "Add Transaction" button. You will need to provide a date, a description, and an amount for the transaction.

### Approving Transactions

Once you have imported or manually added transactions, you will need to approve them before they are converted into formal, balanced journal entries. This is where you apply the double-entry bookkeeping principles.

To approve transactions, click on the "Unapproved Transactions" link in the "Journal" dropdown menu. For each transaction:

1.  Select the **Debit Account**: This is where the value is increasing (e.g., an Expense account for a payment, or a Cash account for income received).
2.  Select the **Credit Account**: This is where the value is decreasing (e.g., a Cash account for a payment, or a Revenue account for income earned).

After selecting the accounts, click the "Approve Selected Transactions" button. This action creates a balanced journal entry, ensuring your books remain accurate.

## 4.5. Understanding Transaction Types vs. Journal Entries

Logical Books uses two main concepts for recording financial activity:

*   **Transactions:** These are raw, unapproved records of financial activity, often imported from bank statements or manually entered. They typically have a date, description, and amount. They are a staging area.
*   **Journal Entries:** These are the formal, balanced records of financial activity that adhere to double-entry bookkeeping principles. Every journal entry has a debit and a credit account for the same amount, ensuring your books are always in balance.

While `JournalEntry` records have a `transaction_type` field (e.g., 'income', 'expense') for filtering and reporting purposes, the true nature of the transaction (whether it's income, expense, or a transfer) is primarily determined by the **types of accounts** used in the debit and credit sides of the Journal Entry. The `transaction_type` field acts as a helpful tag for quick categorization and reporting, but the underlying double-entry is what drives the financial statements.

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

## 11. Recurring Transactions

### Detecting Recurring Transactions

Logical Books can automatically detect recurring transactions by analyzing your transaction history for patterns in description and amount at regular intervals. To view the detected recurring transactions, click on the "Recurring Transactions" link in the "Journal" dropdown menu.

### Approving Recurring Transactions

Once a recurring transaction has been detected, you can approve it by selecting a debit and credit account and clicking the "Approve" button. Once approved, a new `RecurringTransaction` record will be created, and a journal entry will be automatically created for the transaction on a daily, weekly, monthly, or yearly basis.

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
./run_dev.sh
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

To add a new account to the chart of accounts, click on the "Chart of Accounts" link in the navigation bar. The table is now interactive, allowing you to sort, search, and filter accounts. When adding or editing accounts, the parent account dropdown is now searchable for easier selection.

You can also edit an existing account by clicking on the "Edit" button next to the account in the chart of accounts.

## 4. Managing Transactions

### Importing Transactions

Logical Books allows you to import transactions from a CSV file. To import transactions, click on the "Tools" dropdown in the navigation bar and select "Import". Then, select the account for which you want to import transactions and choose a CSV file to upload. The import process is now more robust and will help prevent duplicate entries.

You will need to create an import template to map the columns in your CSV file to the fields in Logical Books. To create a new template, click on the "Add Template" button and fill out the form.

### Manually Adding Transactions

You can also add transactions manually. These are initially considered **unapproved transactions** and will need to be categorized into proper journal entries.

To add a new transaction, click on the "New" dropdown in the navigation bar and select "Add New Transaction". You will need to provide a date, a description, an amount, and optionally a vendor for the transaction.

### Approving Transactions

Once you have imported or manually added transactions, you will need to approve them before they are converted into formal, balanced journal entries. This is where you apply the double-entry bookkeeping principles.

To approve transactions, click on the "Journal" dropdown menu in the navigation bar and select "Unapproved Transactions". The table is now interactive, allowing you to sort, search, and filter. Potential duplicate transactions (matching existing journal entries) are highlighted in red. You can also use the "Delete All Duplicates" button to quickly remove them.

For each transaction:

1.  Select the **Debit Account**: This is where the value is increasing (e.g., an Expense account for a payment, or a Cash account for income received).
2.  Select the **Credit Account**: This is where the value is decreasing (e.g., a Cash account for a payment, or a Revenue account for income earned).
3.  Optionally, select a **Vendor** for the transaction.

After selecting the accounts, click the "Approve Selected Transactions" button. This action creates a balanced journal entry, ensuring your books remain accurate.

## 4.5. Understanding Transaction Types vs. Journal Entries

Logical Books uses two main concepts for recording financial activity:

*   **Transactions:** These are raw, unapproved records of financial activity, often imported from bank statements or manually entered. They typically have a date, description, and amount. They are a staging area.
*   **Journal Entries:** These are the formal, balanced records of financial activity that adhere to double-entry bookkeeping principles. Every journal entry has a debit and a credit account for the same amount, ensuring your books are always in balance.

While `JournalEntry` records have a `transaction_type` field (e.g., 'income', 'expense') for filtering and reporting purposes, the true nature of the transaction (whether it's income, expense, or a transfer) is primarily determined by the **types of accounts** used in the debit and credit sides of the Journal Entry. The `transaction_type` field acts as a helpful tag for quick categorization and reporting, but the underlying double-entry is what drives the financial statements.

## 5. Journal Entries

### Viewing Journal Entries

To view the journal entries, click on the "Journal" dropdown menu in the navigation bar and select "Journal Entries". The journal is a chronological record of all the financial transactions of a business. The table is now interactive, allowing you to sort, search, and filter. Potential duplicate entries are highlighted in red, and you can use the "Delete All Duplicates" button to quickly remove them.

### Adding and Editing Journal Entries

You can also add and edit journal entries manually. To add a new journal entry, click on the "Actions" dropdown on the journal page and select "Add New Entry". To edit an existing journal entry, click on the "Edit" button next to the entry in the journal. The debit and credit account dropdowns are now searchable for easier selection.

## 6. Financial Statements

Logical Books can generate the following financial statements:

*   **Income Statement:** Shows the company's financial performance over a period of time.
*   **Balance Sheet:** Shows the company's financial position at a specific point in time.
*   **Statement of Cash Flows:** Shows how cash is moving in and out of the business.

To view the financial statements, click on the "Reports" dropdown in the navigation bar and select the desired statement.

## 7. Fixed Assets and Depreciation

### Adding Fixed Assets

To add a new fixed asset, click on the "Tools" dropdown in the navigation bar and select "Fixed Assets". Then, click the "Add Fixed Asset" button and fill out the form. You will need to provide a name, a purchase date, a cost, a useful life, and a salvage value for the asset.

### Viewing the Depreciation Schedule

To view the depreciation schedule for a fixed asset, click on the "Depreciation Schedule" button next to the asset in the fixed assets list.

## 8. Inventory and Sales

### Adding Products

To add a new product, click on the "Inventory" dropdown in the navigation bar and select "Products". Then, click the "Add Product" button and fill out the form. You will need to provide a name, a description, and a cost for the product.

### Managing Inventory

To view the inventory, click on the "Inventory" dropdown in the navigation bar and select "Inventory". The inventory page shows the quantity of each product on hand.

### Recording Sales

To record a sale, click on the "Inventory" dropdown in the navigation bar and select "Sales". Then, click the "Add Sale" button and fill out the form. You will need to provide a date, a product, a quantity, and a price for the sale.

When you record a sale, the inventory is automatically updated, and the corresponding journal entries are created for the sale and the cost of goods sold.

## 9. Accruals

### Adding Accruals

To add a new accrual, click on the "Inventory" dropdown in the navigation bar and select "Accruals". Then, click the "Add Accrual" button and fill out the form. You will need to provide a date, a description, an amount, a debit account, and a credit account for the accrual.

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

## 11. Recurring Transactions

### Detecting Recurring Transactions

Logical Books can automatically detect recurring transactions by analyzing your transaction history for patterns in description and amount at regular intervals. To view the detected recurring transactions, click on the "Tools" dropdown in the navigation bar and select "Recurring Transactions".

### Approving Recurring Transactions

Once a recurring transaction has been detected, you can approve it by selecting a debit and credit account and clicking the "Approve" button. Once approved, a new `RecurringTransaction` record will be created, and a journal entry will be automatically created for the transaction on a daily, weekly, monthly, or yearly basis.

## 12. Transaction Rules

Transaction rules allow you to automate the categorization and account assignment of your transactions. Rules can be based on keywords, transaction amounts, and can automatically set categories, transaction types, and most importantly, the **Debit and Credit accounts** for your journal entries.

### Creating and Editing Rules

1.  Navigate to "Tools" dropdown in the main menu and select "Transaction Rules".
2.  Click "Add Rule" or "Edit" an existing rule.
3.  **Rule Criteria:**
    *   **Name:** A descriptive name for your rule.
    *   **Keyword:** A word or phrase found in the transaction description (e.g., "Starbucks", "Rent").
    *   **Value Condition:** (Optional) Apply the rule based on the transaction amount (e.g., "Less Than", "Greater Than", "Equals" a specific value).
4.  **Rule Actions:**
    *   **Category:** Assign a category to the transaction.
    *   **Set Type:** Assign a `transaction_type` (Income, Expense) for filtering.
    *   **Debit Account:** Select the account to be debited when this rule applies (e.g., "Expenses: Office Supplies").
    *   **Credit Account:** Select the account to be credited when this rule applies (e.g., "Assets: Checking Account").
    *   **Automatic:** If checked, the rule will automatically apply to unapproved transactions. If unchecked, you can manually apply it.
5.  **Account Inclusion/Exclusion:** You can specify specific accounts for which this rule should or should not apply.

### Applying Rules

Rules can be applied automatically (if marked as "Automatic") or manually from the "Unapproved Transactions" page.

## 13. Vendor Management

Logical Books now allows you to track your vendors. This helps in organizing your payables and provides better insights into your spending.

### Adding and Editing Vendors

To manage your vendors, click on the "Vendors" link in the navigation bar. From there, you can:

*   **Add New Vendor:** Click the "Add New Vendor" button and fill out the vendor details.
*   **Edit Vendor:** Click the "Edit" button next to an existing vendor to modify their information.

When adding or editing transactions, you can now associate a transaction with a specific vendor using the new "Vendor" dropdown.

## 14. Dynamic Transaction Analysis

Logical Books now includes a powerful dynamic transaction analysis tool, powered by AG-Grid. This allows you to explore your financial data in a highly interactive and customizable way, without needing to hard-code new reports.

### How to Use the Transaction Analysis Tool

1.  Navigate to the "Tools" dropdown in the navigation bar and select "Transaction Analysis".
2.  **Filter Your Data:** Use the date range selectors, and the multi-select dropdowns for "Account" and "Vendor" to narrow down the transactions you want to analyze.
3.  **Group and Pivot:** The core power of this tool lies in its ability to dynamically group and pivot your data. Drag any column header (e.g., "Category", "Account", "Vendor", "Date", "Description") into the "Row Groups" or "Column Labels" sections at the top of the grid. This will instantly aggregate your data based on your chosen criteria.
4.  **Aggregate Values:** The "Amount" column will automatically sum up the values for your chosen groups. You can also change the aggregation type (e.g., to count transactions) by right-clicking on the "Amount" column header and selecting "Aggregations".
5.  **Filter and Sort:** Use the built-in filters and sorting options on each column to further refine your view.
6.  **Chart Your Data:** The tool includes a built-in charting engine. Select the data you want to visualize within the grid, right-click, and choose "Chart Range" to create various types of charts (e.g., bar charts, pie charts) directly from your aggregated data.

This dynamic analysis tool provides unparalleled flexibility to gain insights from your transaction data.

