import math
from collections import Counter

STOPWORDS = [
    "怎么", "如何", "请问", "一下", "可以", "能不能", "有没有", "是不是",
    "什么", "为什么", "哪里", "哪个", "我们", "你们", "他们",
    "吗", "呢", "啊", "吧", "的", "了", "我", "你", "他", "想", "要", "这", "那",
]

def normalize(text: str) -> str:
    lowered = text.lower()

    for word in STOPWORDS:
        lowered = lowered.replace(word, " ")

    return "".join(ch for ch in lowered if ch.isalnum())

def tokenize(text: str) -> Counter:
    s = normalize(text)

    if len(s) < 2:
        # 只剩一个字或空，切不出 bigram，原样返回
        return Counter([s]) if s else Counter()

    return Counter(s[i:i + 2] for i in range(len(s) - 1))

def cosine(a: Counter, b: Counter) -> float:
    if not a or not b:
        return 0.0

    common = set(a) & set(b)
    if not common:
        return 0.0 

    dot = sum(a[k] * b[k] for k in common)
    norm_a = math.sqrt(sum(v * v for v in a.values()))
    norm_b = math.sqrt(sum(v * v for v in b.values()))
    return dot / (norm_a * norm_b)

def is_contained(query: str, phrase: str) -> bool:
    q = normalize(query)
    p = normalize(phrase)

    if not q or not p:
        return False

    return q in p or p in q