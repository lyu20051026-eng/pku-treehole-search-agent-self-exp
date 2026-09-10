import unittest
from hot_topics.config import HotConfig
from hot_topics.ranking import rank_posts, tokenize


def p(pid, text, **counts):
    return dict(pid=pid, text=text, timestamp=100000, **counts)


class RankingTests(unittest.TestCase):
    def test_document_frequency_not_repetition(self):
        selected, words = rank_posts([
            p(1, '体育课 ' * 20), p(2, '体育课 选课'), p(3, '体育课 名额'),
            p(4, '奖学金 综测')], HotConfig(), now=100000)
        self.assertEqual(next(w['post_count'] for w in words if w['word'] == '体育课'), 3)
        self.assertEqual({i['pid'] for i in selected if i['selection']['hot_candidate']}, {1, 2, 3})

    def test_high_favorite_post_survives_without_hot_keyword(self):
        rows = [p(i, '体育课 选课') for i in range(1, 5)]
        rows.append(p(5, '失物招领 手表', likenum=100, praise_num=1, reply=0))
        selected, _ = rank_posts(rows, HotConfig(top_posts=3), now=100000)
        hot = next(i for i in selected if i['pid'] == 5)
        self.assertIn('高收藏', hot['selection']['reasons'])
        self.assertEqual(hot['metrics']['favorites'], 100)
        self.assertEqual(hot['metrics']['likes'], 1)

    def test_real_comment_count_uses_reply_not_preview_hint(self):
        selected, _ = rank_posts([p(1, '体育课', reply=21, comment_total=11),
                                 p(2, '食堂', reply=1, comment_total=10),
                                 p(3, '图书馆', comment_total=11)], HotConfig(), now=100000)
        by_id = {item['pid']: item for item in selected}
        self.assertEqual(by_id[1]['metrics']['comments'], 21)
        self.assertEqual(by_id[2]['metrics']['comments'], 1)
        self.assertIsNone(by_id[3]['metrics']['comments'])

    def test_author_labels_are_not_hot_topics(self):
        selected, words = rank_posts([p(i, 'dz 求拉 体育课') for i in (1, 2, 3)], HotConfig(), now=100000)
        self.assertNotIn('dz', [w['word'] for w in words])
        self.assertIn('体育课', [w['word'] for w in words])

    def test_missing_counts_and_zero_counts_are_distinct(self):
        selected, _ = rank_posts([p(1, '图书馆', likenum=0), p(2, '食堂', praise_num=0)],
                                 HotConfig(), now=100000)
        first = next(i for i in selected if i['pid'] == 1)
        self.assertIsNone(first['metrics']['likes'])
        self.assertEqual(first['metrics']['favorites'], 0)
        self.assertFalse(first['selection']['hot_candidate'])
        self.assertEqual(first['scores']['engagement'], 0)

    def test_grouping_is_deterministic_and_no_input_mutation(self):
        original = [p(1, '体育课 选课 名额'), p(2, '体育课 选课 扩容'), p(3, '图书馆 座位')]
        a, _ = rank_posts(original, HotConfig(), now=100000)
        b, _ = rank_posts(list(reversed(original)), HotConfig(), now=100000)
        self.assertEqual(a, b)
        groups = {i['pid']: i['topic_group'] for i in a}
        self.assertEqual(groups[1], groups[2])
        self.assertNotEqual(groups[1], groups[3])
        self.assertNotIn('scores', original[0])

    def test_filters_empty_hidden_content_and_preserves_english_abbreviation(self):
        self.assertIn('ics', tokenize('ICS 与 icS 的课程'))
        rows, _ = rank_posts([p(1, ''), p(2, '测试', hidden=1), p(3, 'ICS 课程')],
                            HotConfig(), now=100000)
        self.assertEqual([i['pid'] for i in rows], [3])
