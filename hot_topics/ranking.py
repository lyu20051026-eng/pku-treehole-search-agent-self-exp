"""Deterministic candidate union: document frequency and independent engagement."""
from bisect import bisect_left, bisect_right
from collections import Counter
from copy import deepcopy
from functools import lru_cache
import logging
import math
from pathlib import Path
import re
import unicodedata

from .collect import nonnegative_int


@lru_cache(maxsize=1)
def _tokenizer():
    import jieba
    jieba.setLogLevel(logging.WARNING)
    tokenizer = jieba.Tokenizer()
    with Path(__file__).with_name('campus_words.txt').open('rb') as dictionary:
        tokenizer.load_userdict(dictionary)
    stop = set(Path(__file__).with_name('stopwords.txt').read_text(encoding='utf-8').split())
    return tokenizer, stop


def tokenize(text):
    tokenizer, stop = _tokenizer()
    text = unicodedata.normalize('NFKC', str(text or '')).lower()
    text = re.sub(r'https?://\S+|#\d+', ' ', text)
    return [word for word in tokenizer.cut(text) if word not in stop and len(word) >= 2
            and re.fullmatch(r'[a-z][a-z0-9+_-]*|[\u4e00-\u9fff]+', word)]


def _metrics(post):
    comments = nonnegative_int(post.get('reply'))
    return {'favorites': nonnegative_int(post.get('likenum')),
            'likes': nonnegative_int(post.get('praise_num')),
            'comments': comments}


def _percentile(value, population):
    # Zero is not popular, even in a zero-only sample. Ties get their average rank.
    if value is None or value <= 0 or not population:
        return 0.0
    left, right = bisect_left(population, value), bisect_right(population, value)
    return ((left + 1 + right) / 2) / len(population)


def _vector(tokens, df, n):
    counts = Counter(tokens)
    weights = {w: (1 + math.log(c)) * (math.log((1+n)/(1+df[w]))+1)
               for w, c in counts.items()}
    norm = math.sqrt(sum(v*v for v in weights.values())) or 1
    return {w: v/norm for w, v in weights.items()}


def _cosine(a, b):
    return sum(v*b.get(w, 0) for w, v in a.items())


def rank_posts(posts, config, now):
    usable = sorted([deepcopy(p) for p in posts if str(p.get('text') or '').strip()
                     and not nonnegative_int(p.get('hidden', 0))], key=lambda p: p['pid'])
    token_lists = [tokenize(p['text']) for p in usable]
    df = Counter(w for words in token_lists for w in set(words))
    hot_words = {w for w, count in df.items() if count >= config.min_keyword_posts}
    keywords = [{'word': w, 'post_count': count, 'coverage': round(count/max(1,len(usable)), 4)}
                for w, count in sorted(df.items(), key=lambda pair: (-pair[1], pair[0]))
                if w in hot_words][:50]
    # Same vocabulary for user-visible keywords and ranking explanations.
    hot_words = {entry['word'] for entry in keywords}
    counts = [_metrics(p) for p in usable]
    names = {'favorites': '高收藏', 'likes': '高点赞', 'comments': '高评论'}
    thresholds = {'favorites': config.min_favorites, 'likes': config.min_likes,
                  'comments': config.min_comments}
    weights = {'favorites': .4, 'likes': .3, 'comments': .3}
    populations = {key: sorted(c[key] for c in counts if c[key] is not None and c[key] > 0)
                   for key in names}
    vectors = {}
    for post, words, metrics in zip(usable, token_lists, counts):
        matched = sorted(set(words) & hot_words, key=lambda w: (-df[w], w))
        topic_score = (sum(df[w] for w in matched[:5]) /
                       max(1, sum(sorted((df[w] for w in hot_words), reverse=True)[:5])))
        percentiles = {key: _percentile(metrics[key], populations[key]) for key in names}
        available_weight = sum(weights[k] for k in names if metrics[k] is not None)
        engagement = sum(weights[k]*percentiles[k] for k in names)/ (available_weight or 1)
        fresh = max(0.0, min(1.0, 1-(now-post['timestamp'])/(config.hours*3600)))
        reasons = ['热词: ' + '、'.join(matched[:5])] if matched else []
        for key, label in names.items():
            value = metrics[key]
            if value is not None and value > 0 and value >= thresholds[key] and percentiles[key] >= config.high_percentile:
                reasons.append(label)
        post['metrics'] = metrics
        post['scores'] = {'topic': round(topic_score, 6), 'engagement': round(engagement, 6),
                          'freshness': round(fresh, 6),
                          'total': round(.4*topic_score + .5*engagement + .1*fresh, 6),
                          'metric_percentiles': percentiles}
        post['selection'] = {'hot_candidate': bool(reasons), 'reasons': reasons or ['补充样本（未达热点门槛）']}
        post['keywords'] = matched[:5]
        vectors[post['pid']] = _vector(words, df, len(usable))
    usable.sort(key=lambda p: (-int(p['selection']['hot_candidate']), -p['scores']['total'],
                              -p['timestamp'], p['pid']))
    # Reserve one representative for each independent engagement signal.
    representatives = []
    for label in names.values():
        representative = next((p for p in usable if label in p['selection']['reasons']), None)
        if representative is not None and representative not in representatives:
            representatives.append(representative)
    reserve_ids = {p['pid'] for p in representatives[:config.top_posts]}
    chosen = reserve_ids | {p['pid'] for p in [p for p in usable if p['pid'] not in reserve_ids]
                            [:config.top_posts-len(reserve_ids)]}
    selected = [p for p in usable if p['pid'] in chosen]
    # Compare each post to group representatives, preventing transitive chain merging.
    groups = []
    for post in selected:
        vector = vectors[post['pid']]
        best = max(((i, _cosine(vector, representative)) for i, representative in enumerate(groups)),
                   key=lambda pair: pair[1], default=(-1, -1))
        if best[0] >= 0 and best[1] >= config.topic_similarity:
            post['topic_group'] = best[0] + 1
        else:
            groups.append(vector)
            post['topic_group'] = len(groups)
    return selected, keywords
