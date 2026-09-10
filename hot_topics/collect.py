"""Bounded v3 collection. Failures and coverage are data, never empty success."""
from copy import deepcopy
from datetime import datetime, timezone
import time


def nonnegative_int(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        number = int(value)
        return number if number >= 0 and float(value) == number else None
    except (ValueError, TypeError, OverflowError):
        return None


def _page(result):
    if not isinstance(result, dict) or result.get('code') != 20000:
        raise RuntimeError('树洞接口业务错误')
    data = result.get('data')
    if not isinstance(data, dict) or not isinstance(data.get('list'), list):
        raise RuntimeError('树洞接口返回结构无效：需要 data.list')
    return data['list'], nonnegative_int(data.get('total'))


def _options(config):
    return {'limit': config.page_size, 'request_delay': config.request_delay,
            'max_retries': config.max_retries}


def collect_recent(client, config, now=None, progress=None):
    now = int(time.time() if now is None else now)
    start = now - config.hours * 3600
    selected, seen, page_signatures = {}, set(), set()
    descending, previous_time, old_pages = True, None, 0
    meta = {'window_start': start, 'window_end': now, 'pages': 0, 'scanned': 0,
            'duplicates': 0, 'invalid_records': 0, 'complete': False,
            'stop_reason': 'page_limit', 'api_total': None, 'errors': [],
            'started_at': datetime.now(timezone.utc).isoformat()}
    for page in range(1, config.max_scan_pages + 1):
        try:
            rows, total = _page(client.list_recent_posts(page=page, **_options(config)))
        except Exception as exc:
            meta.update(stop_reason='request_error', failed_page=page)
            meta['errors'].append(type(exc).__name__ + ': 近期列表请求失败')
            break
        meta['pages'] += 1
        if progress and (page == 1 or page % 10 == 0):
            progress(f'已扫描列表 {page} 页，已找到窗口内 {len(selected)} 帖')
        meta['api_total'] = total
        if not rows:
            meta.update(complete=True, stop_reason='empty_page')
            break
        signature = tuple(str(row.get('pid')) for row in rows if isinstance(row, dict))
        if signature in page_signatures:
            meta['stop_reason'] = 'repeated_page'
            break
        page_signatures.add(signature)
        regular_times = []
        for row in rows:
            if meta['scanned'] >= config.max_scan_posts:
                break
            meta['scanned'] += 1
            if not isinstance(row, dict):
                meta['invalid_records'] += 1
                continue
            pid = nonnegative_int(row.get('pid'))
            timestamp = nonnegative_int(row.get('timestamp'))
            if not pid or timestamp is None:
                meta['invalid_records'] += 1
                continue
            if pid in seen:
                meta['duplicates'] += 1
                continue
            seen.add(pid)
            if not row.get('is_top'):
                regular_times.append(timestamp)
            if start <= timestamp <= now:
                item = deepcopy(row)
                item.update(pid=pid, timestamp=timestamp)
                selected[pid] = item
        # v3 total is a moving pagination hint (observed 31, 61...), not a fixed count.
        # Ignore already-seen IDs when checking page shifts caused by new posts.
        if not regular_times or any(t is None for t in regular_times):
            old_pages = 0
        else:
            for stamp in regular_times:
                if previous_time is not None and stamp > previous_time:
                    descending = False
                previous_time = stamp
            old_pages = old_pages + 1 if all(t < start for t in regular_times) else 0
        if descending and old_pages >= 2 and meta['scanned'] < config.max_scan_posts:
            meta.update(complete=True, stop_reason='time_boundary',
                        ordering_evidence='observed_descending')
            break
        if meta['scanned'] >= config.max_scan_posts:
            meta['stop_reason'] = 'scan_limit'
            break
    meta['observed_descending'] = descending
    meta['unique_scanned'] = len(seen)
    meta['in_window'] = len(selected)
    meta['finished_at'] = datetime.now(timezone.utc).isoformat()
    if meta['invalid_records']:
        meta['complete'] = False
    return list(selected.values()), meta


def resolve_relations(pid, comments):
    result = deepcopy(comments)
    index = {nonnegative_int(c.get('cid')): c for c in result
             if nonnegative_int(c.get('pid', pid)) == pid}
    for comment in result:
        parent_id = nonnegative_int(comment.get('comment_id')) or None
        relation = {'parent_cid': parent_id, 'status': 'unknown'}
        if parent_id:
            relation['status'] = 'missing'
            parent = index.get(parent_id)
            if parent is not None and parent_id != nonnegative_int(comment.get('cid')):
                relation['status'] = 'resolved'
            else:
                parent = comment.get('quote')
                if (isinstance(parent, dict) and nonnegative_int(parent.get('cid')) == parent_id
                        and nonnegative_int(parent.get('pid')) == pid
                        and parent_id != nonnegative_int(comment.get('cid'))):
                    relation['status'] = 'quoted_only'
                else:
                    parent = None
            if parent is not None:
                relation.update(parent_text=parent.get('text', ''),
                                parent_name=parent.get('name_tag', 'Anonymous'))
        comment['relation'] = relation
    return result


def collect_comments(client, post, config):
    item = deepcopy(post)
    pid = item['pid']
    preview = item.get('comments') or item.get('comment_list') or []
    expected = nonnegative_int(item.get('reply'))
    fetched, preview_by_id = {}, {}
    info = {'declared_total': expected, 'preview_hint': nonnegative_int(item.get('comment_total')), 'api_total': None, 'pages': 0,
            'complete': False, 'pagination_complete': False, 'stop_reason': 'page_limit',
            'invalid_records': 0, 'failed_page': None,
            'started_at': datetime.now(timezone.utc).isoformat()}
    def insert(rows, target):
        for c in rows:
            if not isinstance(c, dict):
                info['invalid_records'] += 1
                continue
            cid = nonnegative_int(c.get('cid'))
            if not cid or nonnegative_int(c.get('pid', pid)) != pid:
                info['invalid_records'] += 1
                continue
            target[cid] = dict(c, pid=pid, cid=cid)
    insert(preview, preview_by_id)
    # Even zero counts can be stale. Refresh the comment endpoint once per selected post.
    for page in range(1, config.max_comment_pages + 1):
        try:
            rows, total = _page(client.list_hot_comments(pid, page=page, **_options(config)))
        except Exception:
            info.update(stop_reason='request_error', failed_page=page)
            break
        info['pages'] += 1
        if rows or info['api_total'] is None:
            info['api_total'] = total
        if not rows:
            info.update(pagination_complete=True, stop_reason='empty_page')
            break
        previous = len(fetched)
        insert(rows, fetched)
        if len(fetched) == previous:
            info['stop_reason'] = 'repeated_page'
            break
    if not info['pagination_complete']:
        # Keep original preview only on failure; don't resurrect absent comments on success.
        fetched = {**preview_by_id, **fetched}
    comments = sorted(fetched.values(), key=lambda c: (nonnegative_int(c.get('timestamp')) or 0, c['cid']))
    item['comments'] = resolve_relations(pid, comments)
    item.pop('comment_list', None)
    info['fetched_total'] = len(comments)
    info['count_mismatch'] = expected is not None and expected != len(comments)
    info['api_hint_differs'] = info['api_total'] is not None and info['api_total'] != len(comments)
    info['missing_parents'] = sum(c['relation']['status'] == 'missing' for c in item['comments'])
    info['complete'] = (info['pagination_complete'] and not info['count_mismatch']
                        and not info['invalid_records'])
    info['finished_at'] = datetime.now(timezone.utc).isoformat()
    item['comment_fetch'] = info
    return item
