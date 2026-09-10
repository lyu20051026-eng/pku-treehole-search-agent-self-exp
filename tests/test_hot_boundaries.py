import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from contextlib import redirect_stdout
from hot_topics.collect import collect_comments, collect_recent
from hot_topics.config import HotConfig
from hot_topics.report import summarize
from test_hot_collection import Pages, response, post


class BoundaryTests(unittest.TestCase):
    def test_comment_dynamic_total_does_not_hide_next_page(self):
        client = Pages([response([{'pid': 7, 'cid': 1}], 1),
                        response([{'pid': 7, 'cid': 2}], 3), response([])])
        result = collect_comments(client, dict(post(7), reply=2, comment_total=10), HotConfig(request_delay=0))
        self.assertEqual([c['cid'] for c in result['comments']], [1, 2])
        self.assertTrue(result['comment_fetch']['pagination_complete'])
        self.assertTrue(result['comment_fetch']['complete'])
        self.assertTrue(result['comment_fetch']['api_hint_differs'])

    def test_pinned_old_page_does_not_count_as_time_boundary(self):
        old = dict(post(1, 1), is_top=1)
        client = Pages([response([old, post(2, 9000)]), response([dict(old,pid=3)]),
                        response([post(4, 99999)]), response([])])
        rows, scan = collect_recent(client, HotConfig(request_delay=0), now=100000)
        self.assertEqual([p['pid'] for p in rows], [4])
        self.assertEqual(scan['stop_reason'], 'empty_page')

    def test_chunk_budget_reports_partial_and_bounds_model_input(self):
        bundle = {'posts': [dict(post(7), text='test '*2000, comments=[])],
                  'scan': {'in_window': 1, 'complete': True}}
        seen = []
        def llm(user, system):
            seen.append(user)
            return '摘要 [#7]'
        answer, info = summarize(bundle, llm,
            HotConfig(context_chars=2000, max_summary_chunks=2), lambda message: None)
        self.assertTrue(info['partial'])
        self.assertEqual(info['used_chunks'], 2)
        self.assertEqual(info['note_calls'], 2)
        self.assertEqual(len(seen), 3)
        self.assertTrue(all(len(user) <= 2000 for user in seen))

    def test_comment_only_chunk_can_cite_its_post(self):
        bundle = {'posts': [dict(post(7), comments=[{'cid': 3, 'text': '材料 '*3000,
                   'relation': {'status': 'missing', 'parent_cid': 99}}])],
                  'scan': {'in_window': 1, 'complete': True}}
        answer, info = summarize(bundle, lambda u,s: '讨论 [#7]',
            HotConfig(context_chars=2000), lambda message: None)
        self.assertEqual(answer, '讨论 [#7]')
        self.assertFalse(info['partial'])

    def test_import_and_help_without_private_config(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as d:
            for name in ('agent.py', 'client.py', 'utils.py', 'config_example.py'):
                shutil.copy(root / name, d)
            result = subprocess.run([sys.executable, 'agent.py', '--help'], cwd=d,
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('--hot-replay', result.stdout)

    def test_no_login_client_created_during_replay_initialization(self):
        from agent import TreeholeRAGAgent
        with patch('agent.TreeholeClient', side_effect=AssertionError('must not log in')):
            with redirect_stdout(io.StringIO()):
                agent = TreeholeRAGAgent(authenticate=False)
        self.assertIsNone(agent.client)
