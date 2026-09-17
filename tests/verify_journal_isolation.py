"""Explicit live test: creates two temporary users, tests only their rows, cleans up.
Never prints access tokens, passwords, service keys, or response bodies.
"""
import argparse
import os
from pathlib import Path
import secrets
import uuid
import requests


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-live', action='store_true', required=True)
    parser.add_argument('--env-file', type=Path)
    args = parser.parse_args()
    if args.env_file:
        for line in args.env_file.read_text().splitlines():
            if line.strip() and not line.lstrip().startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ.setdefault(key.strip(), value.strip().strip('\"\''))
    url = os.environ['SUPABASE_URL'].rstrip('/')
    service = os.environ['SUPABASE_SERVICE_ROLE_KEY']
    anon = os.environ['SUPABASE_ANON_KEY']
    users = []
    tables = ['journal_fills','journal_notes','journal_preferences','journal_discipline','journal_connections']

    def call(method, path, token, admin=False, **kwargs):
        headers = {'apikey': service if admin else anon, 'Authorization': 'Bearer ' + token,
                   'Content-Type': 'application/json', 'Prefer': 'return=representation'}
        if token == anon: headers.pop('Authorization', None)
        return requests.request(method, url + path, headers=headers, timeout=20, **kwargs)

    def check(ok, label):
        if not ok: raise RuntimeError('FAILED: ' + label)

    try:
        for _ in range(2):
            email = 'journal-security-' + uuid.uuid4().hex + '@example.invalid'
            password = secrets.token_urlsafe(40)
            response = call('POST','/auth/v1/admin/users',service,True,
                            json={'email':email,'password':password,'email_confirm':True})
            check(response.status_code in (200,201),'create temporary test user')
            user = response.json(); uid = user.get('id') or user['user']['id']
            users.append({'id':uid})
            response = call('POST','/auth/v1/token?grant_type=password',anon,
                            json={'email':email,'password':password})
            check(response.status_code == 200,'sign in test user (email/password provider must be enabled)')
            users[-1]['token'] = response.json()['access_token']

        fixtures = {
          'journal_notes': {'symbol':'SECURITY_TEST','close_datetime':'2026-01-01T10:00:00','body':'test only'},
          'journal_fills': {'trade_id':'security-'+uuid.uuid4().hex,'account':'SECURITY_TEST','symbol':'SECURITY_TEST','asset_class':'STK','datetime':'2026-01-01T10:00:00','trade_date':'2026-01-01','quantity':1,'trade_price':1,'proceeds':-1,'commission':0,'realized_pnl':0,'source':'security_test'},
          'journal_preferences': {'currency':'GBP','monthly_target':5000,'trading_days':20},
          'journal_discipline': {'day':'2026-01-01','followed_rules':True},
        }
        for owner in users:
            for table, fixture in fixtures.items():
                response = call('POST','/rest/v1/'+table,owner['token'],json={'user_id':owner['id'],**fixture})
                check(response.status_code in (200,201),table+' own insert')
                params = {'user_id':'eq.'+owner['id']}
                response = call('GET','/rest/v1/'+table,owner['token'],params=params)
                check(response.status_code == 200 and bool(response.json()),table+' own read')

        for owner, other in [(users[0],users[1]),(users[1],users[0])]:
            for table, fixture in fixtures.items():
                params = {'user_id':'eq.'+owner['id']}
                for token, label in [(other['token'],'cross-account'),(anon,'anonymous')]:
                    response = call('GET','/rest/v1/'+table,token,params=params)
                    check(response.status_code in (401,403) or (response.status_code==200 and response.json()==[]),table+' '+label+' read')
                response = call('PATCH','/rest/v1/'+table,other['token'],params=params,json=fixture)
                check(response.status_code in (401,403) or (response.status_code==200 and response.json()==[]),table+' cross-account update')
                response = call('DELETE','/rest/v1/'+table,other['token'],params=params)
                check(response.status_code in (401,403) or (response.status_code==200 and response.json()==[]),table+' cross-account delete')
                response = call('PATCH','/rest/v1/'+table,owner['token'],params=params,json={'user_id':other['id']})
                check(response.status_code in (401,403),table+' ownership transfer')
                # A new logical record avoids mistaking unique-key failure for RLS.
                forged = dict(fixture)
                if table=='journal_notes': forged['symbol']='FORGED_TEST'
                elif table=='journal_fills': forged['trade_id']='forged-'+uuid.uuid4().hex
                elif table=='journal_preferences': forged['currency']='EUR'
                else: forged['day']='2026-01-02'
                response = call('POST','/rest/v1/'+table,other['token'],json={'user_id':owner['id'],**forged})
                check(response.status_code in (401,403),table+' forged-owner insert')
            response = call('GET','/rest/v1/journal_connections',owner['token'],params={'user_id':'eq.'+owner['id']})
            check(response.status_code in (401,403),'broker vault denies direct user reads')
        print('PASS: two-user read/write/delete/ownership isolation and anonymous reads; vault blocks browser reads.')
    finally:
        cleanup_failed = False
        for user in users:
            for table in tables:
                try:
                    response=call('DELETE','/rest/v1/'+table,service,True,params={'user_id':'eq.'+user['id']})
                    if response.status_code not in (200,204,404): cleanup_failed=True
                except requests.RequestException: cleanup_failed=True
            try:
                response=call('DELETE','/auth/v1/admin/users/'+user['id'],service,True)
                if response.status_code not in (200,204): cleanup_failed=True
            except requests.RequestException: cleanup_failed=True
        if cleanup_failed:
            print('Cleanup needs checking for temporary user IDs:', ', '.join(u['id'] for u in users))
            raise RuntimeError('Temporary test-account cleanup incomplete.')
        print('Temporary test users and rows removed.')

if __name__ == '__main__':
    try: main()
    except Exception as error:
        # Do not dump requests exceptions (URLs or bodies may contain secrets).
        print(str(error) if isinstance(error, RuntimeError) else 'Verification could not finish. Check configuration and network access.')
        raise SystemExit(1)
