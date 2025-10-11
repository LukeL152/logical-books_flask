from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify, current_app
from app import db
from app.models import PlaidItem, PlaidAccount, PendingPlaidLink, Account, Transaction, Client
import plaid
from plaid.api import plaid_api
from plaid.model.products import Products
from plaid.model.country_code import CountryCode
from plaid.model.link_token_create_request import LinkTokenCreateRequest
from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser
from plaid.model.link_token_get_request import LinkTokenGetRequest
from plaid.model.link_token_create_request_update import LinkTokenCreateRequestUpdate
from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest
from plaid.model.item_remove_request import ItemRemoveRequest
from plaid.model.transactions_get_request import TransactionsGetRequest
from plaid.model.transactions_get_request_options import TransactionsGetRequestOptions
from plaid.model.transactions_sync_request import TransactionsSyncRequest
from plaid.model.accounts_get_request import AccountsGetRequest
from plaid.model.accounts_balance_get_request import AccountsBalanceGetRequest
import os
import json
from datetime import datetime
import logging

plaid_bp = Blueprint('plaid', __name__)

import jwt
import hashlib

def verify_plaid_webhook(request):
    """Verifies a Plaid webhook request."""
    # Get the JWT from the Plaid-Verification header
    jwt_token = request.headers.get('Plaid-Verification')
    if not jwt_token:
        return False, ("Webhook has no Plaid-Verification header.", 400)

    try:
        # Get the key ID from the JWT header
        jwt_header = jwt.get_unverified_header(jwt_token)
        key_id = jwt_header['kid']

        # Fetch the corresponding JWK from Plaid
        response = current_app.plaid_client.webhook_verification_key_get(
            plaid.model.webhook_verification_key_get_request.WebhookVerificationKeyGetRequest(key_id=key_id)
        )
        jwk = response['key']

        # Verify the JWT signature
        algorithm = jwt.get_algorithm_by_name('ES256')
        public_key = algorithm.from_jwk(json.dumps(jwk))
        decoded_jwt = jwt.decode(jwt_token, public_key, algorithms=['ES256'], options={"verify_aud": False})

        # Check the timestamp
        iat = decoded_jwt['iat']
        if datetime.fromtimestamp(iat) < datetime.now() - timedelta(minutes=5):
            return False, ("Webhook timestamp is too old.", 403)

        # Verify the request body hash
        request_body_sha256 = decoded_jwt['request_body_sha256']
        computed_hash = hashlib.sha256(request.get_data()).hexdigest()
        if request_body_sha256 != computed_hash:
            return False, ("Request body hash does not match.", 403)

        return True, (None, 200)

    except (jwt.InvalidTokenError, plaid.exceptions.ApiException) as e:
        return False, (str(e), 403)

@plaid_bp.route('/plaid')
def plaid_page():
    current_app.logger.info("--- plaid_page: start ---")
    if 'client_id' not in session:
        current_app.logger.warning("plaid_page: client_id not in session, redirecting to clients page")
        return redirect(url_for('clients.clients'))
    
    client_id = session.get('client_id')
    current_app.logger.info(f"plaid_page: client_id={client_id}")
    if not client_id:
        current_app.logger.warning("plaid_page: client_id is None, redirecting to clients page")
        return redirect(url_for('clients.clients'))

    client = Client.query.get(client_id)
    plaid_items = PlaidItem.query.filter_by(client_id=client_id).all()
    accounts = Account.query.filter_by(client_id=client_id).order_by(Account.name).all()
    
    current_app.logger.info("--- plaid_page: end ---")
    return render_template('plaid.html', 
                           plaid_items=plaid_items, 
                           accounts=accounts, 
                           client=client)

@plaid_bp.route('/api/current_link_token')
def current_link_token():
    current_app.logger.info("--- current_link_token: start ---")
    t = session.get('link_token')
    if not t:
        current_app.logger.warning("current_link_token: no link_token in session")
        return jsonify({'error': 'no token in session'}), 404
    current_app.logger.info(f"current_link_token: found link_token: {t}")
    current_app.logger.info("--- current_link_token: end ---")
    return jsonify({'link_token': t})

@plaid_bp.route('/api/create_link_token', methods=['POST'])
def create_link_token():
    current_app.logger.info("--- create_link_token: start ---")
    try:
        client_id = session['client_id']  # will 400/KeyError if missing; fine since /plaid protects it
        redirect_uri = "https://lemainframe.duckdns.org/plaid"
        current_app.logger.info(f"create_link_token: client_id={client_id}, redirect_uri={redirect_uri}")

        req = LinkTokenCreateRequest(
            user=LinkTokenCreateRequestUser(client_user_id=str(client_id)),
            client_name="Logical Books",
            products=[Products(p) for p in current_app.config['PLAID_PRODUCTS']],
            country_codes=[CountryCode(c) for c in current_app.config['PLAID_COUNTRY_CODES']],
            language='en',
            redirect_uri="https://lemainframe.duckdns.org/plaid",   # <<< keep this for OAuth inst’ns
        )
        resp = current_app.plaid_client.link_token_create(req)
        link_token = resp['link_token']
        current_app.logger.info(f"create_link_token: created link_token: {link_token}")

        # save for OAuth resume + client identification
        db.session.add(PendingPlaidLink(link_token=link_token, client_id=client_id, purpose='standard'))
        db.session.commit()

        current_app.logger.info("--- create_link_token: end ---")
        return jsonify(resp.to_dict())
    except plaid.exceptions.ApiException as e:
        current_app.logger.error(f"create_link_token: Plaid API exception: {e}")
        return jsonify(json.loads(e.body)), 500
    except Exception as e:
        current_app.logger.error(f"create_link_token: Unexpected error: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@plaid_bp.route('/api/generate_hosted_link/<int:client_id>', methods=['POST'])
def generate_hosted_link(client_id):
    # Ensure the current user has access to this client
    if session.get('client_id') != client_id:
        return "Unauthorized", 403

    if not current_app.config['PLAID_WEBHOOK_URL']:
        logging.error("PLAID_WEBHOOK_URL is not set in the environment.")
        return jsonify({'error': 'Server configuration error'}), 500

    try:
        request = LinkTokenCreateRequest(
            user=LinkTokenCreateRequestUser(
                client_user_id=str(client_id)
            ),
            client_name="Logical Books",
            products=[Products(p) for p in current_app.config['PLAID_PRODUCTS']],
            country_codes=[CountryCode(c) for c in current_app.config['PLAID_COUNTRY_CODES']],
            language='en',
            webhook=current_app.config['PLAID_WEBHOOK_URL'],
            redirect_uri="https://lemainframe.duckdns.org/plaid",
            hosted_link={},
        )
        response = current_app.plaid_client.link_token_create(request)
        
        link_token = response['link_token']
        new_pending_link = PendingPlaidLink(link_token=link_token, client_id=client_id, purpose='hosted')
        db.session.add(new_pending_link)
        db.session.commit()

        hosted_link_url = response['hosted_link_url']
        return jsonify({'hosted_link_url': hosted_link_url})
    except plaid.exceptions.ApiException as e:
        return jsonify(json.loads(e.body)), 500

@plaid_bp.route('/api/create_link_token_for_update', methods=['POST'])
def create_link_token_for_update():
    plaid_item_id = request.json['plaid_item_id']
    item = PlaidItem.query.get_or_404(plaid_item_id)
    if item.client_id != session['client_id']:
        return "Unauthorized", 403

    try:
        link_token_request = LinkTokenCreateRequest(
            client_name="Logical Books",
            country_codes=[CountryCode(c) for c in current_app.config['PLAID_COUNTRY_CODES']],
            language='en',
            access_token=item.access_token,
            redirect_uri="https://lemainframe.duckdns.org/plaid",
        )
        response = current_app.plaid_client.link_token_create(link_token_request)
        return jsonify(response.to_dict())
    except plaid.exceptions.ApiException as e:
        return jsonify(json.loads(e.body)), 500

def _exchange_public_token(public_token, institution_name, institution_id, client_id):
    current_app.logger.info(f"_exchange_public_token: public_token={public_token}, institution_name={institution_name}, institution_id={institution_id}, client_id={client_id}")
    try:
        exchange_request = ItemPublicTokenExchangeRequest(public_token=public_token)
        exchange_response = current_app.plaid_client.item_public_token_exchange(exchange_request)
        access_token = exchange_response['access_token']
        item_id = exchange_response['item_id']
        current_app.logger.info(f"_exchange_public_token: Received access_token={access_token}, item_id={item_id}")

        # Check if this item already exists for this client
        existing_item = PlaidItem.query.filter_by(item_id=item_id, client_id=client_id).first()
        if existing_item:
            current_app.logger.info(f'_exchange_public_token: Item {item_id} already exists for client {client_id}. Ignoring.')
            return None, None, 'This institution is already linked.' # Indicate that no new item was created

        new_item = PlaidItem(
            client_id=client_id,
            item_id=item_id,
            access_token=access_token,
            institution_name=institution_name,
            institution_id=institution_id
        )
        db.session.add(new_item)
        db.session.commit()
        
        # Also sync accounts right away
        sync_plaid_accounts(new_item.id)

        return new_item, None, 'Bank account linked successfully!'
    except plaid.exceptions.ApiException as e:
        current_app.logger.error(f"_exchange_public_token: Plaid API exception during token exchange: {e.body}")
        return None, {'error': 'Plaid API error'}, None

@plaid_bp.route('/api/exchange_public_token', methods=['POST'])
def exchange_public_token():
    current_app.logger.info("--- exchange_public_token: start ---")
    body = request.get_json() or {}
    public_token = body.get('public_token')
    link_token   = body.get('link_token')
    current_app.logger.info(f"exchange_public_token: Received public_token={public_token}, link_token={link_token}")

    client_id = None
    if link_token:
        pending = PendingPlaidLink.query.filter_by(link_token=link_token).first()
        if pending:
            client_id = pending.client_id
            db.session.delete(pending)
            db.session.commit()
            current_app.logger.info(f"exchange_public_token: Resolved client_id={client_id} from pending link_token.")

    if client_id is None:
        client_id = session.get('client_id')  # last resort
        current_app.logger.info(f"exchange_public_token: Resolved client_id={client_id} from session (last resort).")

    if not client_id:
        current_app.logger.error("exchange_public_token: Could not resolve client for this Link session.")
        return jsonify({'error': 'Could not resolve client for this Link session.'}), 400

    institution_name = body.get('institution_name')
    institution_id = body.get('institution_id')
    current_app.logger.info(f"exchange_public_token: institution_name={institution_name}, institution_id={institution_id}")

    new_item, error, success_message = _exchange_public_token(public_token, institution_name, institution_id, client_id)
    if error:
        current_app.logger.error(f"exchange_public_token: Error during public token exchange: {error}")
        return jsonify(error), 500
    if not new_item:
        current_app.logger.warning(f"exchange_public_token: Institution {institution_name} already linked or no new item created.")
        return jsonify({'error': f'This institution ({institution_name}) is already linked.'}), 409
    
    flash(success_message, 'success')
    current_app.logger.info(f"exchange_public_token: Successfully exchanged public token for client_id={client_id}. Redirecting to /plaid.")
    current_app.logger.info("--- exchange_public_token: end ---")
    return jsonify({'status': 'success', 'redirect_url': url_for('plaid.plaid_page')})

@plaid_bp.route('/api/plaid_webhook', methods=['POST'])
def plaid_webhook():
    current_app.logger.info("--- plaid_webhook: start ---")
    is_valid, error_response = verify_plaid_webhook(request)
    if not is_valid:
        current_app.logger.error(f"plaid_webhook: Webhook verification failed: {error_response[0]}")
        return jsonify({'error': error_response[0]}), error_response[1]

    data = request.get_json()
    current_app.logger.info(f"Received Plaid webhook: {data}")
    webhook_code = data.get('webhook_code')
    link_token = data.get('link_token')

    current_app.logger.info(f"Received Plaid webhook: {data.get('webhook_type')} - {webhook_code}")

    if webhook_code == 'SESSION_FINISHED':
        pending_link = PendingPlaidLink.query.filter_by(link_token=link_token).first()

        if not pending_link:
            current_app.logger.warning(f"Webhook for link_token '{link_token}' received, but no pending client found.")
            return jsonify({'status': 'ignored', 'reason': 'client_not_found'})

        client_id = pending_link.client_id

        if data.get('status', '').upper() == 'SUCCESS':
            public_token = data.get('public_tokens')[0] # Assuming one for now
            
            try:
                # For Hosted Link, we must call /link/token/get to fetch the institution details.
                link_get_request = plaid.model.link_token_get_request.LinkTokenGetRequest(link_token=link_token)
                link_get_response = current_app.plaid_client.link_token_get(link_get_request)

                institution_id = None
                institution_name = None

                if link_get_response and 'link_sessions' in link_get_response and link_get_response['link_sessions']:
                    first_session = link_get_response['link_sessions'][0]
                    if 'results' in first_session and 'item_add_results' in first_session['results'] and first_session['results']['item_add_results']:
                        first_item_add_result = first_session['results']['item_add_results'][0]
                        if 'institution' in first_item_add_result:
                            institution_id = first_item_add_result['institution'].get('institution_id')
                            institution_name = first_item_add_result['institution'].get('name')

                if not institution_id or not institution_name:
                    logging.error(f"Could not find institution details in /link/token/get response for {link_token}")
                    return jsonify({'status': 'error', 'reason': 'institution_details_missing_from_api'}), 500

                _exchange_public_token(public_token, institution_name, institution_id, client_id)
                logging.info(f"Successfully processed SESSION_FINISHED webhook for client {client_id}")
                db.session.delete(pending_link)
                db.session.commit()
                current_app.logger.info("--- plaid_webhook: end (success) ---")
                return jsonify({'status': 'success'})

            except plaid.exceptions.ApiException as e:
                logging.error(f"Plaid API error during /link/token/get: {e}")
                return jsonify({'status': 'error', 'reason': 'plaid_api_error'}), 500
        else:
            logging.info(f"Webhook for link_token '{link_token}' was not successful (status: {data.get('status')}).")
            db.session.delete(pending_link)
            db.session.commit()
            current_app.logger.info("--- plaid_webhook: end (not success) ---")
            return jsonify({'status': 'ignored', 'reason': 'not_success'})

    current_app.logger.info("--- plaid_webhook: end (received) ---")
    return jsonify({'status': 'received'})

@plaid_bp.route('/api/transactions/sync', methods=['POST'])
def sync_transactions():
    plaid_account_id = request.json['plaid_account_id']
    current_app.logger.info(f"Syncing transactions for plaid_account_id: {plaid_account_id}")
    plaid_account = PlaidAccount.query.get_or_404(plaid_account_id)
    item = plaid_account.plaid_item
    if item.client_id != session['client_id']:
        return "Unauthorized", 403

    added_count = 0
    
    try:
        cursor = item.cursor
        sync_request = TransactionsSyncRequest(
            access_token=item.access_token,
        )
        if cursor:
            sync_request.cursor = cursor

        response = current_app.plaid_client.transactions_sync(sync_request)
        
        added = response['added']

        # Filter transactions to only include those for the requested account
        added_for_account = [t for t in added if t['account_id'] == plaid_account.account_id]
        added_count = len(added_for_account)

        for t in added_for_account:
            new_transaction = Transaction(
                date=t['date'],
                description=t['name'],
                amount=-t['amount'], # Plaid returns positive for debits, negative for credits
                category=t['category'][0] if t['category'] else None,
                client_id=session['client_id'],
                is_approved=False,
                source_account_id=plaid_account.local_account_id
            )
            db.session.add(new_transaction)

        item.cursor = response['next_cursor']
        item.last_synced = datetime.now()
        db.session.commit()

    except Exception as e:
        try:
            error_body = json.loads(e.body)
            if 'error_code' in error_body and error_body['error_code'] == 'NO_ACCOUNTS':
                current_app.logger.info("No accounts found for this item during transaction sync.")
                return jsonify({'status': 'no_accounts'})
        except:
            pass # Not a Plaid error with a JSON body

        current_app.logger.error(f"Error syncing transactions: {e}")
        return jsonify({'error': 'An error occurred while syncing transactions.'}), 500

    return jsonify({'status': 'success', 'added': added_count})

@plaid_bp.route('/api/plaid/set_account', methods=['POST'])
def set_plaid_account():
    plaid_account_id = request.json['plaid_account_id']
    account_id = request.json['account_id']
    plaid_account = PlaidAccount.query.get_or_404(plaid_account_id)
    if plaid_account.plaid_item.client_id != session['client_id']:
        return "Unauthorized", 403
    
    plaid_account.local_account_id = account_id
    db.session.commit()
    return jsonify({'status': 'success'})

def update_balances(plaid_item):
    try:
        balance_request = AccountsBalanceGetRequest(access_token=plaid_item.access_token)
        accounts_response = current_app.plaid_client.accounts_balance_get(balance_request)
        balances = accounts_response['accounts']

        for balance_info in balances:
            plaid_account = PlaidAccount.query.filter_by(account_id=balance_info['account_id']).first()
            if plaid_account and plaid_account.local_account:
                plaid_account.local_account.current_balance = balance_info['balances']['current']
                plaid_account.local_account.balance_last_updated = datetime.utcnow()
        
        db.session.commit()
        return True
    except Exception as e:
        current_app.logger.error(f"Error updating balances: {e}")
        return False

@plaid_bp.route('/api/plaid/refresh_balances', methods=['POST'])
def refresh_balances():
    plaid_item_id = request.json['plaid_item_id']
    item = PlaidItem.query.get_or_404(plaid_item_id)
    if item.client_id != session['client_id']:
        return "Unauthorized", 403

    if update_balances(item):
        return jsonify({'status': 'success'})
    else:
        return jsonify({'error': 'Failed to update balances'}), 500

def sync_plaid_accounts(plaid_item_id=None):
    with current_app.app_context():
        current_app.logger.info(f'Syncing accounts for plaid_item_id: {plaid_item_id}')
        if plaid_item_id:
            plaid_items = [PlaidItem.query.get(plaid_item_id)]
        else:
            plaid_items = PlaidItem.query.filter_by(client_id=session['client_id']).all()

        total_added = 0
        total_deleted = 0

        for item in plaid_items:
            if not item:
                continue
            try:
                accounts_request = AccountsGetRequest(access_token=item.access_token)
                accounts_response = current_app.plaid_client.accounts_get(accounts_request)
                accounts = accounts_response['accounts']
                current_app.logger.info(f'Found {len(accounts)} accounts for item {item.id}')

                valid_plaid_account_ids = {acc['account_id'] for acc in accounts}
                local_plaid_accounts = PlaidAccount.query.filter_by(plaid_item_id=item.id).all()
                local_plaid_account_ids = {acc.account_id for acc in local_plaid_accounts}

                added_count = 0
                for account in accounts:
                    if account['account_id'] not in local_plaid_account_ids:
                        current_app.logger.info(f'Adding account {account["account_id"]} to the database')
                        new_plaid_account = PlaidAccount(
                            plaid_item_id=item.id,
                            account_id=account['account_id'],
                            name=account['name'],
                            mask=account['mask'],
                            # enums in Plaid SDK
                            type=(account['type'].value
                                  if hasattr(account['type'], 'value') else str(account['type'])) ,
                            subtype=(account['subtype'].value
                                     if hasattr(account['subtype'], 'value') else str(account['subtype'])) ,
                        )
                        db.session.add(new_plaid_account)
                        added_count += 1

                deleted_count = 0
                for local_acc in local_plaid_accounts:
                    if local_acc.account_id not in valid_plaid_account_ids:
                        db.session.delete(local_acc)
                        deleted_count += 1

                db.session.commit()
                total_added += added_count
                total_deleted += deleted_count
                current_app.logger.info(
                    f"Sync complete for item {item.id}. Added: {added_count}, Deleted: {deleted_count}"
                )
            except plaid.exceptions.ApiException as e:
                current_app.logger.error(f"Error syncing accounts for item {item.id}: {e}")
        return total_added, total_deleted
                
@plaid_bp.route('/api/plaid/sync_accounts', methods=['POST'])
def sync_accounts_route():
    plaid_item_id = request.json.get('plaid_item_id')
    added, deleted = sync_plaid_accounts(plaid_item_id)
    return jsonify({'status': 'success', 'added': added, 'deleted': deleted})

@plaid_bp.route('/api/plaid/fetch_transactions', methods=['POST'])
def fetch_transactions():
    plaid_item_id = request.json.get('plaid_item_id')
    plaid_account_id = request.json.get('plaid_account_id')
    start_date_str = request.json['start_date']
    end_date_str = request.json['end_date']

    start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
    end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()

    item = None
    target_account_ids = None

    if plaid_item_id:
        item = PlaidItem.query.get_or_404(plaid_item_id)
        plaid_accounts = PlaidAccount.query.filter(PlaidAccount.plaid_item_id == item.id).all()
        target_account_ids = [pa.account_id.strip() for pa in plaid_accounts]
    elif plaid_account_id:
        plaid_account = PlaidAccount.query.get_or_404(plaid_account_id)
        item = plaid_account.plaid_item
        target_account_ids = [plaid_account.account_id.strip()]
    else:
        return jsonify({'error': 'Either plaid_item_id or plaid_account_id must be provided'}), 400

    if item.client_id != session['client_id']:
        return "Unauthorized", 403

    try:
        transactions_get_request = TransactionsGetRequest(
            access_token=item.access_token,
            start_date=start_date,
            end_date=end_date,
        )
        response = current_app.plaid_client.transactions_get(transactions_get_request)
        all_transactions = response['transactions']
        
        transactions = []
        if target_account_ids is not None:
            transactions = [t for t in all_transactions if t['account_id'].strip() in target_account_ids]
        else:
            transactions = all_transactions

        account_id_map = {pa.account_id: pa.local_account_id for pa in PlaidAccount.query.filter(PlaidAccount.plaid_item_id == item.id).all()}

        added_count = 0
        for t in transactions:
            if not Transaction.query.filter_by(plaid_transaction_id=t['transaction_id']).first():
                source_account_id = account_id_map.get(t['account_id'])
                new_transaction = Transaction(
                    plaid_transaction_id=t['transaction_id'],
                    date=t['date'],
                    description=t['name'],
                    amount=-t['amount'],
                    category=t['category'][0] if t['category'] else None,
                    client_id=session['client_id'],
                    is_approved=False,
                    source_account_id=source_account_id
                )
                db.session.add(new_transaction)
                added_count += 1
        
        db.session.commit()
    except Exception as e:
        return jsonify({'error': 'An error occurred while fetching transactions.'}), 500

@plaid_bp.route('/api/plaid/delete_account', methods=['POST'])
def delete_plaid_account():
    plaid_account_id = request.json['plaid_account_id']
    account = PlaidAccount.query.get_or_404(plaid_account_id)
    if account.plaid_item.client_id != session['client_id']:
        return "Unauthorized", 403

    try:
        db.session.delete(account)
        db.session.commit()
        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'error': 'An error occurred while deleting the account.'}), 500
@plaid_bp.route('/api/plaid/delete_institution', methods=['POST'])
def delete_institution():
    plaid_item_id = request.json['plaid_item_id']
    item = PlaidItem.query.get_or_404(plaid_item_id)
    if item.client_id != session['client_id']:
        return "Unauthorized", 403

    try:
        # Remove the item from Plaid
        remove_request = ItemRemoveRequest(access_token=item.access_token)
        current_app.plaid_client.item_remove(remove_request)

        # Remove the item from the database
        db.session.delete(item)
        db.session.commit()

        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'error': 'An error occurred while deleting the institution.'}), 500

@plaid_bp.route('/api/plaid/debug_link_token', methods=['POST'])
def debug_link_token():
    link_token = request.json['link_token']
    try:
        response = current_app.plaid_client.link_token_get(LinkTokenGetRequest(link_token=link_token))
        return jsonify(response.to_dict())
    except plaid.exceptions.ApiException as e:
        return jsonify(json.loads(e.body)), 500
    except Exception as e:
        current_app.logger.error(f"Unexpected error in debug_link_token: {e}")
        return jsonify({'error': 'Internal server error'}), 500
