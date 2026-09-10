"""Legacy modes exercised with synthetic content and HTTP-only model doubles."""
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch
from agent import TreeholeRAGAgent


class ModelResponse:
    def __init__(self, message=None):
        self.message = message
    def raise_for_status(self):
        pass
    def json(self):
        return {'choices': [{'message': self.message}]}
    def iter_lines(self):
        yield ('data: ' + json.dumps({'choices': [{'delta': {'content': '测试回答'}}]})).encode()
        yield b'data: [DONE]'


class LegacyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.cache_patch = patch('agent.CACHE_DIR', self.temp.name)
        self.cache_patch.start()
        self.addCleanup(self.cache_patch.stop)
        self.output = redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)
        self.agent = TreeholeRAGAgent.__new__(TreeholeRAGAgent)
        self.agent.api_key, self.agent.api_base, self.agent.model = 'test', 'https://example.invalid', 'test'
        self.agent.info_callback = self.agent.stream_callback = None
        self.agent._all_comments_cache = {}
        class Client:
            def search_posts(self, keyword, **kwargs):
                return {'success': True, 'data': {'data': [{'pid': 1, 'text': '计网 hq 测评',
                    'timestamp': 100000, 'comment_total': 1, 'comments': [
                    {'cid': 3, 'text': '计网 hq 作业适中', 'name_tag': '洞主', 'is_lz': 1}]}]}}
        self.agent.client = Client()

    def test_manual_mode_still_returns_search_sources(self):
        with patch('agent.requests.post', return_value=ModelResponse()):
            result = self.agent.mode_manual_search('计网', '怎么样')
        self.assertEqual(result['answer'], '测试回答')
        self.assertEqual(result['sources'][0]['pid'], 1)

    def test_auto_mode_executes_tool_search_and_answers(self):
        tool = {'id': 'call1', 'type': 'function', 'function': {'name': 'search_treehole',
                'arguments': json.dumps({'keyword': '计网'})}}
        replies = [ModelResponse({'tool_calls': [tool]}),
                   ModelResponse({'content': 'enough'}), ModelResponse()]
        with patch('agent.requests.post', side_effect=replies), patch('agent.time.sleep'):
            result = self.agent.mode_auto_search('计网怎么样')
        self.assertEqual(result['search_count'], 1)
        self.assertEqual(result['answer'], '测试回答')
        self.assertEqual(result['sources'][0]['pid'], 1)

    def test_course_mode_retains_post_and_comment_review(self):
        with patch('agent.requests.post', return_value=ModelResponse()), patch('agent.time.sleep'):
            result = self.agent.mode_course_review('计网', 'hq')
        self.assertEqual(result['answer'], '测试回答')
        self.assertEqual(result['num_sources'], 2)
