import base64
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch, Mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import journal_security as security

# Dispatch tests must never contact a real broker or database.
fake_cloud = SimpleNamespace(verify_user=Mock(return_value='alice'), compute_stats=Mock(),
                             sync_from_ibkr=Mock(), insert_fills=Mock())
spec = importlib.util.spec_from_file_location('journal_api_security_test', ROOT / 'api/journal.py')
api = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, {'journal_cloud': fake_cloud}):
    spec.loader.exec_module(api)


def request(action='connection', body=b'{}', token='valid', origin=None, method='POST', length=None):
    h = object.__new__(api.handler)
    h.path = '/api/journal.py?action=' + action
    h.headers = {'Content-Length': str(len(body) if length is None else length)}
    if token: h.headers['Authorization'] = 'Bearer ' + token
    if origin: h.headers['Origin'] = origin
    h.rfile, h.wfile = io.BytesIO(body), io.BytesIO()
    h.output_headers = {}
    h.send_response = lambda status: setattr(h, 'status', status)
    h.send_header = lambda key, value: h.output_headers.update({key:value})
    h.end_headers = lambda: None
    getattr(h, 'do_' + method)()
    return h.status, json.loads(h.wfile.getvalue()), h.output_headers


class JournalSecurityTests(unittest.TestCase):
    def setUp(self):
        security._BUCKETS.clear()
        self.env = patch.dict(os.environ, {'JOURNAL_SECURITY_STORAGE':'0', 'JOURNAL_VAULT_KEY':base64.b64encode(b'a'*32).decode()}, clear=False)
        self.env.start()
        self.addCleanup(self.env.stop)
        fake_cloud.verify_user.reset_mock()
        fake_cloud.verify_user.return_value = 'alice'

    def test_encryption_binds_to_user_and_rejects_tampering(self):
        value = {'token':'report-token-123','query_id':'123'}
        sealed = security.seal('alice', value)
        self.assertNotIn(value['token'], sealed)
        self.assertEqual(security.unseal('alice', sealed), value)
        self.assertNotEqual(sealed, security.seal('alice', value))
        for user, cipher in [('bob', sealed), ('alice', sealed[:-8] + 'AAAAAAAA')]:
            with self.assertRaises(security.SecurityError): security.unseal(user, cipher)

    def test_bad_key_fails_closed(self):
        with patch.dict(os.environ, {'JOURNAL_VAULT_KEY':'bad'}):
            with self.assertRaises(security.SecurityError): security.seal('alice', {})

    def test_no_authenticated_user_no_database_access(self):
        fake_cloud.verify_user.return_value = None
        with patch.object(security, 'save_connection') as save:
            self.assertEqual(request()[0], 401)
            save.assert_not_called()

    def test_untrusted_origin_rejected_before_auth(self):
        self.assertEqual(request(origin='https://evil.example')[0], 403)
        fake_cloud.verify_user.assert_not_called()

    def test_payload_user_id_cannot_change_credential_owner(self):
        with patch.object(security, 'save_connection', return_value={'ok':True}) as save:
            self.assertEqual(request(body=b'{"user_id":"bob"}')[0], 200)
            self.assertEqual(save.call_args.args[0], 'alice')

    def test_size_json_and_error_boundaries(self):
        self.assertEqual(request(length=security.MAX_BODY+1)[0], 413)
        self.assertEqual(request(length=-1)[0], 413)
        for body in (b'[]', b'null', b'{bad'):
            self.assertEqual(request(body=body)[0], 400)
        fake_cloud.compute_stats.side_effect = RuntimeError('secret-token-and-account')
        try:
            status, data, headers = request('stats', method='GET')
            self.assertEqual(status, 500)
            self.assertNotIn('secret-token', json.dumps(data))
            self.assertEqual(headers['Cache-Control'], 'no-store')
        finally: fake_cloud.compute_stats.side_effect = None

    def test_sync_error_never_returns_upstream_secret(self):
        fake_cloud.sync_from_ibkr.return_value = {'ok':False,'error':'https://broker/?token=secret'}
        status, data, _ = request('sync',body=b'{"token":"report-token-123","query_id":"123"}')
        self.assertEqual(status,200)
        self.assertNotIn('secret', json.dumps(data))

    def test_import_rejects_xml_entities(self):
        self.assertEqual(request('import-flex',body=b'<!DOCTYPE x [<!ENTITY a "b">]><x/>')[0],400)

    def test_local_limits_and_user_isolation(self):
        for _ in range(2): security.rate_limit('alice','sync','token')
        with self.assertRaises(security.SecurityError) as error: security.rate_limit('alice','sync','token')
        self.assertEqual(error.exception.status,429)
        security.rate_limit('bob','sync','token')

    def test_distributed_limit_does_not_fall_back_on_failure(self):
        with patch.dict(os.environ, {'JOURNAL_SECURITY_STORAGE':'1'}), patch.object(security,'_rest',side_effect=security.SecurityError('unavailable',503)):
            with self.assertRaises(security.SecurityError): security.rate_limit('alice','sync','token')

    def test_profile_owner_and_validation(self):
        with patch.dict(os.environ, {'JOURNAL_SECURITY_STORAGE':'1'}), patch.object(security,'_rest') as rest:
            security.write_profile('jwt','alice',{'kind':'rules','day':'2026-01-01','followed':True,'user_id':'bob'})
            self.assertEqual(rest.call_args.kwargs['json']['user_id'],'alice')
            for target in (0, float('inf'), float('nan'), True):
                with self.assertRaises(security.SecurityError):
                    security.write_profile('jwt','alice',{'kind':'goal','currency':'GBP','monthlyTarget':target,'tradingDays':20})

    def test_ciphertext_cannot_be_read_through_status(self):
        with patch.object(security,'vault_enabled',return_value=True), patch.object(security,'_rest',return_value=[{'user_id':'alice'}]) as rest:
            self.assertEqual(security.connection('alice'),{'enabled':True,'connected':True})
            self.assertEqual(rest.call_args.kwargs['params']['select'],'user_id')


# Execute the actual local handler's class definition without importing bot
# modules or starting services. These checks cover the formerly open dev path.
class LocalBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import ast
        import urllib.request
        from urllib.parse import urlparse, unquote
        from http.server import SimpleHTTPRequestHandler
        tree = ast.parse((ROOT / 'server.py').read_text())
        node = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'DashboardHandler')
        scope = {'SimpleHTTPRequestHandler':SimpleHTTPRequestHandler, 'Path':Path, 'os':os,
                 'urlparse':urlparse, 'unquote':unquote, 'urllib':urllib, 'json':json}
        exec(compile(ast.Module(body=[node], type_ignores=[]), 'server.py', 'exec'), scope)
        cls.handler = scope['DashboardHandler']

    def test_get_and_head_share_private_file_boundary(self):
        for path in ('/.env','/%2eenv','/.git/config','/trade_journal.db','/server.py','/output/','/assets/'):
            h = object.__new__(self.handler)
            h.path = path
            h.send_error = Mock()
            self.assertIsNone(h.send_head())
            h.send_error.assert_called_once_with(404)

    def test_dev_fallback_requires_explicit_loopback_and_no_vercel(self):
        h = object.__new__(self.handler)
        h.headers = {}
        h.client_address = ('127.0.0.1',1)
        with patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(h._journal_user_id())
            os.environ['ALLOW_LOCAL_JOURNAL']='1'
            self.assertEqual(h._journal_user_id(),'local')
            h.client_address=('192.0.2.1',1)
            self.assertIsNone(h._journal_user_id())
            h.client_address=('127.0.0.1',1)
            os.environ['VERCEL']='1'
            self.assertIsNone(h._journal_user_id())

if __name__ == '__main__': unittest.main()
