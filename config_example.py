"""
配置文件示例 - 请复制此文件为 config_private.py 并填入真实值

使用方法：
    cp config_example.py config_private.py
    # 然后编辑 config_private.py，填入你的真实配置
"""

# ==================== Treehole Credentials ====================
# Your PKU credentials for Treehole login
USERNAME = "<USERNAME>"
PASSWORD = "<PASSWORD>"

# ==================== DeepSeek API Configuration ====================
# Get your API key from: https://platform.deepseek.com/
DEEPSEEK_API_KEY = "<DEEPSEEK_API_KEY>"
DEEPSEEK_API_BASE = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-chat"  # or "deepseek-reasoner"

# ==================== Agent Configuration ====================
# Maximum number of posts to retrieve per search
MAX_SEARCH_RESULTS = 40

# Maximum number of posts to include in context for LLM
MAX_CONTEXT_POSTS = 30

# Maximum number of comments to include per post (for mode 1 & 2)
# Set to 0 to disable comments, -1 for unlimited
MAX_COMMENTS_PER_POST = 5

# Maximum number of search iterations in mode_auto_search (智能检索模式)
MAX_SEARCH_ITERATIONS = 5

# Temperature for LLM generation (0.0 - 1.0)
# Lower = more focused, Higher = more creative
TEMPERATURE = 0.7

# Maximum tokens for LLM response
MAX_RESPONSE_TOKENS = 4096

# ==================== Rate Limiting ====================
# Delay between search requests (seconds)
SEARCH_DELAY = 1.0

# Maximum retries for failed requests
MAX_RETRIES = 3

# ==================== Cache Configuration ====================
# Enable caching of search results
ENABLE_CACHE = True

# Cache directory
CACHE_DIR = "data/cache"

# Cache expiration time (seconds), 1 day = 86400
CACHE_EXPIRATION = 86400
# ==================== Mode 4: One-shot hot topics ====================
# Optional: old config_private.py files continue to work without these settings.
HOT_HOURS = 24                    # 4 / 8 / 12 / 24
HOT_TOP_POSTS = 30                # Final selected posts, NOT the scan size
HOT_MAX_SCAN_POSTS = 5000          # Partial coverage is reported if this cap is reached
HOT_MAX_SCAN_PAGES = 200
HOT_PAGE_SIZE = 30
HOT_MAX_COMMENT_PAGES = 200       # Per selected post; incomplete collection is marked
HOT_REQUEST_DELAY = 1.0           # Seconds between v3 requests
HOT_MAX_RETRIES = 3               # Total attempts, including the first request
HOT_MIN_KEYWORD_POSTS = 3         # Different posts mentioning a word
HOT_MIN_FAVORITES = 5             # likenum: favorites (not likes)
HOT_MIN_LIKES = 3                 # praise_num: likes
HOT_MIN_COMMENTS = 10
HOT_HIGH_PERCENTILE = 0.9         # Average rank within positive values of each metric
HOT_TOPIC_SIMILARITY = 0.25       # TF-IDF cosine threshold for auxiliary grouping
HOT_OUTPUT_DIR = "data/hot_topics"
HOT_CONTEXT_CHARS = 18000         # Per model request user-content budget, not token count
HOT_MAX_SUMMARY_CHUNKS = 40       # Note/reduction call budget, plus one final summary
HOT_ONLY_EXPORT = False

# Optional model override for mode 4 only (official API defaults to disabled).
# Non-official API bases omit this field unless explicitly configured.
# HOT_THINKING = "disabled"        # "enabled" / "disabled" / None (provider default)
