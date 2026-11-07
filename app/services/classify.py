from pydantic import BaseModel

class ClassifyResult(BaseModel):
    category: str           
    category_name: str       
    urgency: str             
    sentiment: str           
    matched: list[str]       
    need_human: bool

CATEGORY_KEYWORDS: dict[str, tuple[str, list[str]]] = {
    "billing": ("账单发票", ["发票", "开票", "账单", "扣费", "收费", "套餐", "续费", "价格", "专票", "红冲", "抬头"]),
    "account": ("账号问题", ["密码", "账号", "注册", "手机号", "验证码", "子账号", "锁定", "实名", "邮箱"]),
    "refund": ("退款政策", ["退款", "退钱", "退还", "退费", "返现", "退订"]),
    "tech": ("技术故障", ["报错", "500", "打不开", "加载", "白屏", "崩溃", "崩了", "上传", "接口", "卡住", "很慢", "用不了"]),
    "complaint": ("投诉", ["投诉", "太差", "垃圾", "骗子", "骗人", "曝光", "12315", "领导", "差评", "无语"]),
    "consult": ("一般咨询", ["怎么", "如何", "请问", "能不能", "可以吗", "是什么", "支持吗", "有没有"]),
}

CATEGORY_PRIORITY = ["complaint", "refund", "tech", "billing", "account", "consult"]

URGENT_WORDS = ["紧急", "急", "马上", "立刻", "全都", "无法", "挂了", "用不了", "投诉", "曝光", "12315"]
ANGRY_WORDS = ["垃圾", "骗子", "骗人", "太差", "恶心", "无语", "气死", "曝光", "投诉", "什么破"]
ANXIOUS_WORDS = ["急", "快点", "着急", "马上", "多久", "什么时候", "还没", "催"]

def classify(text:str) -> ClassifyResult:
    lowered = text.lower()

    hits: dict[str, list[str]] = {}
    for code, (_, keywords) in CATEGORY_KEYWORDS.items():
        found = [kw for kw in keywords if kw in lowered]
        if found:
            hits[code] = found

    if hits:
        category = min(
            hits,
            key=lambda c:(-len(hits[c]),CATEGORY_PRIORITY.index(c)),
        )
        matched = hits[category]
    else:
        category = "consult"
        matched = []

    urgent_hits = [w for w in URGENT_WORDS if w in lowered]
    urgency = "high" if urgent_hits else ("medium" if category == "complaint" else "low")

    angry_hits = [w for w in ANGRY_WORDS if w in lowered]
    anxious_hits = [w for w in ANXIOUS_WORDS if w in lowered]
    if angry_hits or (text.count("!") + text.count("！")) >= 2:
        sentiment = "angry"
    elif anxious_hits:
        sentiment = "anxious"
    else:
        sentiment = "neutral"

    need_human = category == "complaint" or (sentiment == "angry" and urgency == "high")

    return ClassifyResult(
        category=category,
        category_name=CATEGORY_KEYWORDS[category][0],
        urgency=urgency,
        sentiment=sentiment,
        matched=matched + urgent_hits,
        need_human=need_human,
    )