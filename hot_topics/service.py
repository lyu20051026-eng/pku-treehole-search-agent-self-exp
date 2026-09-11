"""One-shot collection and credential-free replay."""
from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
import time
from uuid import uuid4

from .collect import collect_recent, collect_comments
from .ranking import rank_posts
from .errors import HotModelError
from .report import atomic_write, save_bundle, render_sources, report_header, summarize, SummaryError, _stamp


def _export_and_summarize(bundle, llm, config, progress):
    directory = Path(config.output_dir).expanduser().resolve() / (
        datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid4().hex[:8])
    directory.mkdir(parents=True)
    data_path, sources_path, summary_path = (directory / name for name in ('posts.json', 'sources.md', 'summary.md'))
    bundle['status'] = 'exported'
    save_bundle(data_path, bundle)
    atomic_write(sources_path, render_sources(bundle))
    progress('原始素材已保存：' + str(data_path))
    answer = ''
    if not bundle['posts']:
        bundle['status'] = 'no_data' if bundle['scan']['complete'] else 'collection_failed'
        answer = '没有可总结的帖子。' if bundle['scan']['complete'] else '采集未完成且没有有效帖子，请检查登录、网络和扫描范围。'
    elif config.only_export:
        answer = '仅导出素材，未调用大语言模型。'
    else:
        try:
            answer, summary_info = summarize(bundle, llm, config, progress)
            bundle['summary_info'] = summary_info
            bundle['status'] = 'partial_summary' if summary_info['partial'] else 'completed'
        except Exception as exc:
            bundle['status'] = 'summary_failed'
            # Exceptions may contain provider responses. Export only a safe classification.
            bundle['summary_error'] = type(exc).__name__
            bundle['summary_error_code'] = exc.code if isinstance(exc, (SummaryError, HotModelError)) else 'model_request_failed'
            answer = '总结未生成：模型请求、出处校验或上下文预算检查失败。原始素材已保留，可使用 --hot-replay 重试。'
            if isinstance(exc, (SummaryError, HotModelError)):
                answer += '\n\n诊断：' + str(exc)
    bundle['answer'] = answer
    header = report_header(bundle)
    if bundle.get('summary_info'):
        info = bundle['summary_info']
        header += f"模型素材覆盖：{info['used_chunks']}/{info['total_chunks']} 块；模型调用 {info.get('model_calls', 0)} 次（输出纠正 {info.get('repair_calls', 0)} 次）。\n\n"
    atomic_write(summary_path, header + answer + '\n')
    save_bundle(data_path, bundle)
    return {'status': bundle['status'], 'answer': header + answer,
            'data_path': str(data_path), 'sources_path': str(sources_path),
            'summary_path': str(summary_path), 'num_sources': len(bundle['posts']),
            'sources': [{'pid': p['pid']} for p in bundle['posts']]}


def run_hot_topics(client, llm, config, now=None, progress=print):
    now = int(time.time() if now is None else now)
    progress(f'统计窗口：{_stamp(now - config.hours * 3600)} 至 {_stamp(now)}')
    progress(f'扫描最近 {config.hours} 小时帖子，最多扫描 {config.max_scan_posts} 条')
    posts, scan = collect_recent(client, config, now, progress=progress)
    selected, keywords = rank_posts(posts, config, now)
    enriched = []
    for index, post in enumerate(selected, 1):
        progress(f"获取评论 {index}/{len(selected)}：#{post['pid']}")
        enriched.append(collect_comments(client, post, config))
    bundle = {'schema_version': 1, 'created_at': datetime.now(timezone.utc).isoformat(),
              'config': asdict(config), 'scan': scan, 'keywords': keywords, 'posts': enriched}
    return _export_and_summarize(bundle, llm, config, progress)


def replay_hot_topics(path, llm, config, progress=print):
    with Path(path).expanduser().open(encoding='utf-8') as stream:
        bundle = json.load(stream)
    if bundle.get('schema_version') != 1 or not isinstance(bundle.get('posts'), list) or not isinstance(bundle.get('scan'), dict):
        raise ValueError('不是有效的热点导出 JSON（schema_version=1）')
    # Keep original window/ranking config as provenance; current config controls only generation.
    bundle['replayed_from'] = str(Path(path).expanduser().resolve())
    bundle['generation_config'] = asdict(config)
    for name in ('answer', 'summary_error', 'summary_error_code', 'summary_info', 'rejected_drafts', 'evidence_notes'):
        bundle.pop(name, None)
    return _export_and_summarize(bundle, llm, config, progress)
