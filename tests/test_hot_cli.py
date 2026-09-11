import io
import json
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch
import requests
from agent import TreeholeRAGAgent


class CLITests(unittest.TestCase):
    def bare_agent(self):
        obj = TreeholeRAGAgent.__new__(TreeholeRAGAgent)
        obj.api_key, obj.api_base, obj.model = 'local-test', 'https://example.invalid', 'test'
        obj.info_callback = obj.stream_callback = None
        return obj

    def test_mode_four_dispatches_8_hours_and_returns_to_menu(self):
        obj = self.bare_agent()
        with patch('builtins.input', side_effect=['4', '8', 'q']), redirect_stdout(io.StringIO()):
            with patch.object(obj, 'mode_hot_topics', return_value={'status': 'exported'}) as run:
                obj.interactive_mode()
        self.assertEqual(run.call_args.kwargs['hours'], 8)

    def test_invalid_hot_hours_do_not_invoke_service(self):
        obj = self.bare_agent()
        with patch('builtins.input', side_effect=['4', '25', 'q']), redirect_stdout(io.StringIO()):
            with patch.object(obj, 'mode_hot_topics') as run:
                obj.interactive_mode()
        self.assertEqual(run.call_count, 0)

    def test_cli_absent_export_flag_preserves_config_default(self):
        from agent import main
        obj = self.bare_agent()
        with patch('sys.argv', ['agent.py', '--hot']), patch('agent.TreeholeRAGAgent', return_value=obj):
            with patch.object(obj, 'mode_hot_topics', return_value={'status': 'exported'}) as run:
                self.assertEqual(main(), 0)
        self.assertIsNone(run.call_args.kwargs['only_export'])

    def test_old_manual_mode_keeps_question_keyword_order(self):
        obj = self.bare_agent()
        with patch('builtins.input', side_effect=['1', '课程怎么样', '计网', 'q']), redirect_stdout(io.StringIO()):
            with patch.object(obj, 'mode_manual_search', return_value={}) as run:
                obj.interactive_mode()
        self.assertEqual(run.call_args.args, ('计网', '课程怎么样'))

    def test_strict_model_failure_raises_without_leaking_detail(self):
        obj = self.bare_agent()
        with patch('agent.requests.post', side_effect=requests.Timeout('secret response')):
            with self.assertRaises(RuntimeError) as raised:
                obj.call_deepseek('prompt', strict=True)
        self.assertNotIn('secret response', str(raised.exception))

    def test_truncated_stream_not_treated_as_summary(self):
        obj = self.bare_agent()
        class Stream:
            def raise_for_status(self):
                pass
            def iter_lines(self):
                yield b'data: {"choices":[{"delta":{"content":"partial"}}]}'
            def close(self):
                pass
        with patch('agent.requests.post', return_value=Stream()):
            with self.assertRaises(RuntimeError):
                obj.call_deepseek('prompt', strict=True)

    def test_official_summary_disables_default_reasoning_without_affecting_proxy(self):
        obj = self.bare_agent()
        class Reply:
            def raise_for_status(self): pass
            def close(self): pass
            def json(self): return {'choices': [{'message': {'content': 'ok'}, 'finish_reason': 'stop'}]}
        requests_sent = []
        def transport(url, **kwargs):
            requests_sent.append(kwargs['json'])
            return Reply()
        from types import SimpleNamespace
        with patch('agent._config', SimpleNamespace()), patch('agent.requests.post', side_effect=transport):
            obj.api_base = 'https://api.deepseek.com'
            obj.call_deepseek('prompt', strict=True, stream=False)
            obj.api_base = 'https://example.invalid'
            obj.call_deepseek('prompt', strict=True, stream=False)
        self.assertEqual(requests_sent[0].get('thinking'), {'type': 'disabled'})
        self.assertNotIn('thinking', requests_sent[1])

    def test_length_limit_has_actionable_diagnostic(self):
        obj = self.bare_agent()
        class Stream:
            def raise_for_status(self): pass
            def close(self): pass
            def iter_lines(self):
                yield b'data: {"choices":[{"delta":{},"finish_reason":"length"}]}'
                yield b'data: [DONE]'
        with patch('agent.requests.post', return_value=Stream()):
            with self.assertRaises(RuntimeError) as raised:
                obj.call_deepseek('prompt', strict=True)
        self.assertEqual(getattr(raised.exception, 'code', None), 'output_token_limit')

    def test_complete_stream_returns_buffer_without_printing_unvalidated_answer(self):
        obj = self.bare_agent()
        class Stream:
            def raise_for_status(self):
                pass
            def iter_lines(self):
                yield b'data: {"choices":[{"delta":{"content":"ok [#7]"}}]}'
                yield b'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}'
                yield b'data: [DONE]'
            def close(self):
                pass
        buffer = io.StringIO()
        with patch('agent.requests.post', return_value=Stream()), redirect_stdout(buffer):
            result = obj.call_deepseek('prompt', strict=True)
        self.assertEqual(result, 'ok [#7]')
        self.assertEqual(buffer.getvalue(), '')

    def test_mode_four_freezes_cutoff_before_duration_prompt(self):
        obj = self.bare_agent()
        with patch('agent.time.time', return_value=123456), patch('builtins.input', side_effect=['4', '12', 'q']), redirect_stdout(io.StringIO()) as output:
            with patch.object(obj, 'mode_hot_topics', return_value={}) as run:
                obj.interactive_mode()
        self.assertEqual(run.call_args.kwargs['now'], 123456)
        self.assertIn('截止时间', output.getvalue())

    def test_only_new_windows_are_accepted(self):
        from hot_topics.config import HotConfig
        for hours in (4, 8, 12, 24):
            self.assertEqual(HotConfig(hours=hours).hours, hours)
        for hours in (72, 168):
            with self.assertRaises(ValueError):
                HotConfig(hours=hours)
