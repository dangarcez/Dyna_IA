import json
import unittest
import httpx
from dynatrace_http import DynatraceDocuments, DynatraceError


class DynatraceHttpTests(unittest.TestCase):
    def test_list_filter_and_bearer(self):
        calls = []
        def handler(request):
            calls.append(request)
            return httpx.Response(200, json={'documents': [], 'totalCount': 0})
        client = DynatraceDocuments(url='https://test.apps.dynatrace.com', token='fake-token', transport=httpx.MockTransport(handler))
        try:
            result = client.list_dashboards(page_size=10)
            self.assertEqual(result['totalCount'], 0)
            self.assertEqual(calls[0].headers['Authorization'], 'Bearer fake-token')
            self.assertEqual(calls[0].url.params['filter'], "type='dashboard'")
        finally:
            client.close()

    def test_get_dashboard_fetches_metadata_and_content(self):
        def handler(request):
            if request.url.path.endswith('/metadata'):
                return httpx.Response(200, json={'type':'dashboard','id':'d1','version':'8','access':['read','write'],'name':'Demo'})
            if request.url.path.endswith('/content'):
                return httpx.Response(200, json={'version':21,'variables':[],'tiles':{},'layouts':{}})
            raise AssertionError(request.url)
        with DynatraceDocuments(url='https://test.apps.dynatrace.com', token='x', transport=httpx.MockTransport(handler)) as c:
            metadata, content = c.get_dashboard('d1')
        self.assertEqual(metadata['version'], '8')
        self.assertEqual(content['version'], 21)

    def test_create_sends_multipart_content(self):
        def handler(request):
            raw = request.read()
            self.assertEqual(request.method, 'POST')
            self.assertIn(b'name="content"', raw)
            self.assertIn(b'application/json', raw)
            self.assertIn(b'name="name"', raw)
            self.assertIn(b'name="type"', raw)
            return httpx.Response(201, json={'id':'new-id'})
        with DynatraceDocuments(url='https://test.apps.dynatrace.com', token='x', transport=httpx.MockTransport(handler)) as c:
            response = c.create_dashboard('Demo', {'version': 21, 'variables':[], 'tiles':{}, 'layouts':{}})
        self.assertEqual(response['id'], 'new-id')

    def test_update_uses_optimistic_locking(self):
        def handler(request):
            self.assertEqual(request.method, 'PUT')
            self.assertEqual(request.url.params['optimistic-locking-version'], '12')
            self.assertIn(b'name="content"', request.read())
            return httpx.Response(200, json={'id':'a', 'version':'13'})
        with DynatraceDocuments(url='https://test.apps.dynatrace.com', token='x', transport=httpx.MockTransport(handler)) as c:
            response = c.update_content('a', {'version':21}, '12')
        self.assertEqual(response['version'], '13')

    def test_conflict_gives_safe_error(self):
        def handler(request):
            return httpx.Response(409, text='token-secret no details')
        with DynatraceDocuments(url='https://test.apps.dynatrace.com', token='token-secret', transport=httpx.MockTransport(handler)) as c:
            with self.assertRaises(DynatraceError) as context:
                c.get_metadata('d1')
        self.assertNotIn('token-secret', str(context.exception))
        self.assertIn('Conflito de versão', str(context.exception))

    def test_invalid_env_url(self):
        with self.assertRaises(ValueError):
            DynatraceDocuments(url='http://localhost:8080', token='x')
        with self.assertRaises(ValueError):
            DynatraceDocuments(url='https://test.apps.dynatrace.com/path', token='x')


if __name__ == '__main__':
    unittest.main()
