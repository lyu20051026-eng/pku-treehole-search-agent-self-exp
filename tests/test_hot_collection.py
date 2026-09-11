import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import requests
from client import TreeholeClient
from hot_topics.config import HotConfig
from hot_topics.collect import collect_recent, collect_comments, resolve_relations


def response(rows, total=None):
    data = {'list': rows}
    if total is not None:
        data['total'] = total
    return {'code': 20000, 'data': data}


def post(pid, timestamp=100000):
    return {'pid': pid, 'timestamp': timestamp, 'text': '体育课选课', 'reply': 0}


class Pages:
    def __init__(self, pages):
        self.pages = pages
        self.requested = []

    def list_recent_posts(self, page, **kwargs):
        self.requested.append(page)
        result = self.pages[page - 1]
        if isinstance(result, Exception):
            raise result
        return result

    def list_hot_comments(self, pid, page, **kwargs):
        return self.list_recent_posts(page, **kwargs)


class CollectionTests(unittest.TestCase):
    def config(self, **kwargs):
        return HotConfig(request_delay=0, page_size=2, **kwargs)

    def test_enumerates_past_old_pinned_post_and_deduplicates(self):
        client = Pages([response([post(1, 1), post(2)]),
                        response([post(2), post(3, 100001)]), response([])])
        posts, meta = collect_recent(client, self.config(), now=100000)
        self.assertEqual([p['pid'] for p in posts], [2])
        self.assertEqual(meta['stop_reason'], 'empty_page')
        self.assertTrue(meta['complete'])
        self.assertEqual(meta['duplicates'], 1)

    def test_budget_does_not_claim_full_window(self):
        posts, meta = collect_recent(Pages([response([post(1), post(2)])]),
                                     self.config(max_scan_posts=2), now=100000)
        self.assertEqual(len(posts), 2)
        self.assertFalse(meta['complete'])
        self.assertEqual(meta['stop_reason'], 'scan_limit')

    def test_repeated_page_and_network_error_keep_partial_data(self):
        for second, reason in [(response([post(1), post(2)]), 'repeated_page'),
                               (RuntimeError('failed'), 'request_error')]:
            rows, meta = collect_recent(Pages([response([post(1), post(2)]), second]),
                                        self.config(), now=100000)
            self.assertEqual(len(rows), 2)
            self.assertEqual(meta['stop_reason'], reason)
            self.assertFalse(meta['complete'])

    def test_dynamic_total_is_not_a_stop_condition(self):
        rows, meta = collect_recent(Pages([response([post(1), post(2)], 2),
            response([post(3)], 4), response([], 4)]), self.config(), now=100000)
        self.assertEqual([p['pid'] for p in rows], [1, 2, 3])
        self.assertEqual(meta['stop_reason'], 'empty_page')

    def test_observed_descending_boundary_requires_two_old_pages(self):
        client = Pages([response([post(1, 100000), post(2, 99999)]),
            response([post(3, 10000), post(4, 9000)]),
            response([post(5, 8000), post(6, 7000)])])
        rows, meta = collect_recent(client, self.config(), now=100000)
        self.assertEqual([p['pid'] for p in rows], [1, 2])
        self.assertEqual(meta['stop_reason'], 'time_boundary')
        self.assertEqual(meta['ordering_evidence'], 'observed_descending')

    def test_page_shift_duplicates_do_not_disprove_descending_order(self):
        client = Pages([response([post(1, 100000), post(2, 99000)]),
            response([post(1, 100000), post(2, 99000), post(3, 9000)]),
            response([post(4, 8000), post(5, 7000)])])
        rows, scan = collect_recent(client, self.config(), now=100000)
        self.assertEqual([p['pid'] for p in rows], [1, 2])
        self.assertEqual(scan['stop_reason'], 'time_boundary')

    def test_timestamp_boundary_and_malformed_records(self):
        rows, meta = collect_recent(Pages([response([post(1, 13600), post(2, 13599),
            {'pid': 3, 'text': 'missing'}, post(4, 100001)], 4), response([])]),
            self.config(), now=100000)
        self.assertEqual([p['pid'] for p in rows], [1])
        self.assertEqual(meta['invalid_records'], 1)

    def test_comment_pagination_mismatch_and_cross_page_parent(self):
        p = post(7)
        p['reply'] = 4
        p['comment_total'] = 10
        client = Pages([response([
            {'pid': 7, 'cid': 10, 'text': '问题', 'name_tag': 'Alice'},
            {'pid': 7, 'cid': 11, 'text': '其他', 'name_tag': 'Alice'}], 3),
            response([{'pid': 7, 'cid': 12, 'text': '回答', 'comment_id': 10,
                       'name_tag': 'Bob', 'quote': []}], 3), response([], 3)])
        enriched = collect_comments(client, p, self.config())
        self.assertEqual(len(enriched['comments']), 3)
        info = enriched['comment_fetch']
        self.assertTrue(info['pagination_complete'])
        self.assertFalse(info['complete'])
        self.assertEqual(info['api_total'], 3)
        rel = enriched['comments'][2]['relation']
        self.assertEqual(rel['parent_cid'], 10)
        self.assertEqual(rel['parent_text'], '问题')
        self.assertEqual(rel['status'], 'resolved')

    def test_missing_quote_and_foreign_quote_never_invent_parent(self):
        rows = resolve_relations(7, [
            {'cid': 1, 'pid': 7, 'comment_id': 8, 'quote': []},
            {'cid': 2, 'pid': 7, 'comment_id': 9,
             'quote': {'cid': 9, 'pid': 999, 'text': 'other hole'}},
            {'cid': 3, 'pid': 7, 'comment_id': 10,
             'quote': {'cid': 10, 'pid': 7, 'text': 'quoted', 'name_tag': 'Alice'}},
            {'cid': 4, 'pid': 7, 'text': '@Alice hello'}])
        self.assertEqual([c['relation']['status'] for c in rows],
                         ['missing', 'missing', 'quoted_only', 'unknown'])
        self.assertEqual(rows[2]['relation']['parent_text'], 'quoted')

    def test_comment_failure_preserves_preview_and_progress(self):
        p = post(7)
        p.update(reply=3, comment_total=10, comment_list=[{'cid': 10, 'pid': 7, 'text': 'preview'}])
        client = Pages([response([{'cid': 11, 'pid': 7}, {'cid': 12, 'pid': 7}], 3),
                        RuntimeError('timeout')])
        enriched = collect_comments(client, p, self.config())
        self.assertEqual({c['cid'] for c in enriched['comments']}, {10, 11, 12})
        self.assertFalse(enriched['comment_fetch']['complete'])
        self.assertEqual(enriched['comment_fetch']['failed_page'], 2)


class ClientTests(unittest.TestCase):
    def test_v3_contract_and_retry_429(self):
        captured = []
        def get(url, **kwargs):
            captured.append((url, kwargs))
            r = requests.Response()
            r.status_code = 429 if len(captured) == 1 else 200
            r._content = json.dumps(response([], 0)).encode()
            return r
        with tempfile.TemporaryDirectory() as d:
            client = TreeholeClient(cookies_file=str(Path(d) / 'cookie'))
            with patch.object(client.session, 'get', side_effect=get), patch('client.time.sleep'):
                result = client.list_hot_comments(7, page=2, limit=10, request_delay=0)
        self.assertEqual(result['data']['total'], 0)
        self.assertEqual(len(captured), 2)
        self.assertTrue(captured[0][0].endswith('/chapi/api/v3/comment/list'))
        self.assertEqual(captured[0][1]['params'],
            {'pid': 7, 'page': 2, 'limit': 10, 'sort': 0, 'comment_stream': 1})
        self.assertEqual(captured[0][1]['timeout'], (10, 60))

    def test_rejects_business_error_instead_of_empty_success(self):
        r = requests.Response()
        r.status_code = 200
        r._content = b'{"code":401,"data":null,"message":"login"}'
        with tempfile.TemporaryDirectory() as d:
            client = TreeholeClient(cookies_file=str(Path(d) / 'cookie'))
            with patch.object(client.session, 'get', return_value=r):
                with self.assertRaises(RuntimeError):
                    client.list_recent_posts(page=1, limit=10, request_delay=0)

    def test_invalid_window_rejected(self):
        with self.assertRaises(ValueError):
            HotConfig(hours=0)

    def test_new_windows_filter_exact_start_and_fixed_end(self):
        for hours in (4, 8, 12, 24):
            now = 200000
            start = now - hours * 3600
            client = Pages([response([post(1, start-1), post(2, start),
                post(3, now), post(4, now+1)]), response([])])
            rows, meta = collect_recent(client, HotConfig(hours=hours, request_delay=0), now=now)
            self.assertEqual([p['pid'] for p in rows], [2, 3])
            self.assertEqual((meta['window_start'], meta['window_end']), (start, now))
