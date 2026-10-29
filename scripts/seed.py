"""种子数据：让系统从"空库"变成"能用"。

分层设计：
    默认        只灌基础数据（角色、权限点、系统配置）—— 生产环境可以跑
    --demo      额外灌演示数据（5 员工、20 知识、20 工单）—— 只在开发环境跑

幂等：用业务唯一键（code / username / key）判断"是否已存在"，
      跑 10 次结果和跑 1 次一样。
"""

import argparse
import hashlib
import pathlib
import random
import sys
from datetime import datetime, timedelta, timezone

# 把项目根目录加入搜索路径，否则 import app 失败（scripts/ 下的脚本都要写这段）
PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import select

import app.models  # noqa: F401  导入后所有模型才登记进 metadata
from app.db.session import SessionLocal
from app.models import (
    Conversation,
    KbArticle,
    KbCategory,
    Message,
    Permission,
    Rating,
    Role,
    SystemConfig,
    Ticket,
    TicketLog,
    User,
)


# ══════════════════════════════════════════════════════════════
# 工具：密码哈希（临时版）
# ══════════════════════════════════════════════════════════════
def hash_password(password: str) -> str:
    """PBKDF2 加盐哈希。

    ⚠️ 这只是临时版，S2 会搬到 app/core/security.py 重写一遍。
    格式：算法$迭代次数$盐$哈希值  —— 把参数一起存下来，
         以后想调迭代次数，老密码依然能验证。
    """
    salt = b"deskflow-seed-salt"          # 种子数据固定盐，只为好复现
    iterations = 260_000
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    return f"pbkdf2_sha256${iterations}${salt.hex()}${digest.hex()}"


# ══════════════════════════════════════════════════════════════
# 工具：get_or_create（幂等的核心）
# ══════════════════════════════════════════════════════════════
def get_or_create(db, model, lookup: dict, values: dict | None = None):
    """按 lookup 里的条件查；查到就返回，查不到就创建。

    参数：
        model   模型类，比如 Role
        lookup  唯一键条件，比如 {"code": "admin"}
        values  创建时额外的字段，比如 {"name": "管理员"}
    返回：模型实例
    """
    obj = db.execute(select(model).filter_by(**lookup)).scalar_one_or_none()
    if obj is not None:
        return obj, False
    obj = model(**lookup, **(values or {}))
    db.add(obj)
    db.flush()      # flush 让它拿到 id，后面关联表要用
    return obj, True


# ══════════════════════════════════════════════════════════════
# 基础数据：角色 + 权限点 + 配置
# ══════════════════════════════════════════════════════════════
ROLES = [
    ("admin", "系统管理员", True),
    ("supervisor", "客服主管", True),
    ("agent", "客服", True),
]

# (code, name, resource, action)
PERMISSIONS = [
    ("ticket:read", "查看自己的工单", "ticket", "read"),
    ("ticket:read_all", "查看所有工单", "ticket", "read_all"),
    ("ticket:reassign", "改派工单", "ticket", "reassign"),
    ("ticket:close_force", "强制关闭工单", "ticket", "close_force"),
    ("ticket:export", "导出工单", "ticket", "export"),
    ("kb:read", "查看知识库", "kb", "read"),
    ("kb:write", "编辑知识库", "kb", "write"),
    ("kb:import", "批量导入知识", "kb", "import"),
    ("user:read", "查看员工", "user", "read"),
    ("user:write", "管理员工", "user", "write"),
    ("role:write", "分配角色权限", "role", "write"),
    ("system:config", "修改系统配置", "system", "config"),
    ("log:read", "查看日志", "log", "read"),
    ("dashboard:read", "查看看板", "dashboard", "read"),
    ("qa:review", "质检复核", "qa", "review"),
]

# 每个角色分到哪些权限点（写 code）
ROLE_PERMISSIONS = {
    "agent": ["ticket:read", "kb:read"],
    "supervisor": [
        "ticket:read", "ticket:read_all", "ticket:reassign", "ticket:export",
        "kb:read", "dashboard:read", "qa:review",
    ],
    "admin": [p[0] for p in PERMISSIONS],   # 全部
}

# (key, value, value_type, description)
CONFIGS = [
    ("kb.match_threshold", "0.50", "float", "知识匹配阈值，低于它就走建单"),
    ("kb.search_top_k", "3", "int", "检索返回几条候选"),
    ("ticket.sla_minutes", "30", "int", "首次响应 SLA（分钟）"),
    ("ticket.max_load_per_agent", "8", "int", "单人同时在办上限"),
    ("qa.sample_rate", "0.2", "float", "质检抽样比例"),
    ("visitor.notice", "", "string", "访客端顶部公告"),
]


def seed_base(db) -> None:
    """基础数据。生产环境也只跑这一段。"""
    print("\n── 基础数据 ──")

    roles = {}
    for code, name, builtin in ROLES:
        role, created = get_or_create(db, Role, {"code": code},
                                      {"name": name, "is_builtin": builtin})
        roles[code] = role
        print(f"  角色 {code:<12} {'新增' if created else '已存在，跳过'}")

    perms = {}
    for code, name, resource, action in PERMISSIONS:
        perm, created = get_or_create(db, Permission, {"code": code}, {
            "name": name, "resource": resource, "action": action,
        })
        perms[code] = perm
    print(f"  权限点 {len(PERMISSIONS)} 个 {'已同步' if True else ''}")

    # 角色-权限关联：只补缺的，不重复加
    for role_code, perm_codes in ROLE_PERMISSIONS.items():
        role = roles[role_code]
        existing = {p.code for p in role.permissions}
        added = 0
        for pc in perm_codes:
            if pc not in existing:
                role.permissions.append(perms[pc])
                added += 1
        print(f"  {role_code:<12} 权限 {len(existing)} → {len(role.permissions)}（新增 {added}）")

    for key, value, vtype, desc in CONFIGS:
        # 配置用"存在就不动"：免得每次重跑把你在后台调好的值覆盖掉
        _, created = get_or_create(db, SystemConfig, {"key": key}, {
            "value": value, "value_type": vtype, "description": desc,
        })
    print(f"  配置项 {len(CONFIGS)} 个 已同步")

    db.commit()


# ══════════════════════════════════════════════════════════════
# 演示数据：员工 + 知识 + 历史工单
# ══════════════════════════════════════════════════════════════
# (username, real_name, 角色, 技能标签)
USERS = [
    ("admin", "系统管理员", "admin", None),
    ("xiaowang", "王小明", "agent", ["账单", "发票"]),
    ("xiaoli", "李芳", "agent", ["账号", "退款"]),
    ("zhangjie", "张杰", "agent", ["技术", "故障"]),
    ("chenmo", "陈默", "supervisor", ["退款", "投诉"]),
]

# (code, name, sort_order)
CATEGORIES = [
    ("billing", "账单发票", 1),
    ("account", "账号问题", 2),
    ("refund", "退款政策", 3),
    ("tech", "技术故障", 4),
]

# (分类 code, 标题, 标签, 正文)
ARTICLES = [
    ("billing", "如何开具发票", ["发票", "开票"], "在「账单中心 → 发票管理」点击「申请开票」，填写抬头和税号，1 个工作日内发送到你的邮箱。"),
    ("billing", "发票红冲流程", ["发票", "红冲"], "发票开具后 30 天内可申请红冲。需在发票管理页提交红冲申请，并上传情况说明。"),
    ("billing", "发票抬头可以修改吗", ["发票", "抬头"], "发票开具前可随时修改抬头；已开具的发票需先红冲再重开。"),
    ("billing", "支持开增值税专用发票吗", ["发票", "专票"], "支持。需要在申请时选择「增值税专用发票」并填写完整的开票资料，包括公司名称、税号、地址电话、开户行及账号。"),
    ("billing", "账单在哪里查看", ["账单"], "在「账单中心」可以看到每月账单明细，支持导出 Excel。"),
    ("billing", "如何更换套餐", ["套餐", "账单"], "在「订阅管理」中选择目标套餐，按剩余天数折算差价，立即生效。"),
    ("account", "密码怎么重置", ["密码", "重置"], "在登录页点击「忘记密码」，输入注册邮箱，会收到重置链接，24 小时内有效。"),
    ("account", "如何修改绑定的手机号", ["手机号", "账号"], "登录后进入「账号设置 → 安全设置」，通过原手机号验证后即可更换。"),
    ("account", "账号被锁定了怎么办", ["锁定", "账号"], "连续 5 次密码错误会锁定 30 分钟。可等待自动解锁，或联系管理员手动解锁。"),
    ("account", "如何添加子账号", ["子账号", "账号"], "管理员在「员工管理」中新增员工账号，并为其分配角色和技能标签。"),
    ("refund", "退款多久到账", ["退款"], "审核通过后 1-3 个工作日原路退回，具体到账时间以银行为准。"),
    ("refund", "什么情况下可以退款", ["退款", "政策"], "未使用的订阅周期可申请按剩余天数比例退款；已使用超过 7 天的周期不支持退款。"),
    ("refund", "如何申请退款", ["退款", "申请"], "在「账单中心 → 订单详情」点击「申请退款」，填写原因后提交，客服会在 1 个工作日内处理。"),
    ("refund", "退款可以退到别的账户吗", ["退款"], "不支持。退款只能原路退回原支付账户，这是支付渠道的硬性要求。"),
    ("tech", "页面加载很慢怎么办", ["性能", "故障"], "先清理浏览器缓存并更换网络重试；若仍慢，请在「帮助中心」提交诊断信息。"),
    ("tech", "上传文件失败", ["上传", "故障"], "单个文件不超过 20MB，支持 pdf/jpg/png。超过限制会失败，请压缩后重试。"),
    ("tech", "数据会丢失吗", ["数据", "备份"], "系统每天凌晨自动备份，保留 30 天。误删数据可联系客服申请恢复。"),
    ("tech", "支持哪些浏览器", ["浏览器"], "支持 Chrome、Edge、Firefox 最近两个大版本，不支持 IE。"),
    ("tech", "接口返回 500 错误", ["接口", "故障"], "500 是服务端异常。请记录请求时间和接口路径，提交给技术支持排查。"),
    ("tech", "如何导出数据", ["导出", "数据"], "在列表页点击「导出」，支持 Excel 和 CSV 两种格式。"),
]


def seed_demo(db) -> None:
    """演示数据。只在开发环境跑。"""
    print("\n── 演示数据 ──")

    # ── 员工 ──
    roles = {r.code: r for r in db.execute(select(Role)).scalars()}
    users = []
    for username, real_name, role_code, skills in USERS:
        user, created = get_or_create(db, User, {"username": username}, {
            "password_hash": hash_password("123456"),
            "real_name": real_name,
            "skills": skills,
        })
        if created:
            user.roles.append(roles[role_code])
        users.append(user)
    print(f"  员工 {len(USERS)} 个（密码统一 123456）")

    # ── 知识分类 + 条目 ──
    cats = {}
    for code, name, sort_order in CATEGORIES:
        cat, _ = get_or_create(db, KbCategory, {"code": code},
                               {"name": name, "sort_order": sort_order})
        cats[code] = cat
    print(f"  知识分类 {len(CATEGORIES)} 个")

    article_count = 0
    for cat_code, title, tags, content in ARTICLES:
        # 用标题当唯一键：标题重复就跳过
        _, created = get_or_create(db, KbArticle, {"title": title}, {
            "category_id": cats[cat_code].id,
            "content": content,
            "tags": tags,
            "status": "published",
            # 造一点历史计数，让有用率报表有数据
            "hit_count": random.randint(0, 20),
            "useful_count": random.randint(0, 10),
            "useless_count": random.randint(0, 3),
        })
        article_count += 1 if created else 0
    print(f"  知识条目 {len(ARTICLES)} 条（新增 {article_count}）")

    # ── 历史会话 + 工单 ──
    # 已经有工单就不再造，保证幂等
    existing_tickets = db.execute(select(Ticket)).scalars().first()
    if existing_tickets:
        print("  历史工单已存在，跳过")
        return

    random.seed(42)          # 固定随机种子 → 每次造出来的数据一样，方便对比
    agents = [u for u in users if u.username in ("xiaowang", "xiaoli", "zhangjie", "chenmo")]
    statuses = ["closed"] * 12 + ["resolved"] * 4 + ["processing"] * 2 + ["assigned"] * 1 + ["pending"] * 1
    categories = ["billing", "account", "refund", "tech"]

    ticket_total = 0
    for i, status in enumerate(statuses):
        created = datetime.now(timezone.utc) - timedelta(
            days=random.randint(0, 6), hours=random.randint(0, 20)
        )
        conv = Conversation(
            visitor_key=f"visitor-{i:03d}",
            channel="web",
            status="closed" if status == "closed" else "open",
            created_at=created,
        )
        db.add(conv)
        db.flush()

        # 客户第一句
        db.add(Message(
            conversation_id=conv.id, sender="visitor",
            content=f"我想咨询一下{categories[i % 4]}相关的问题",
            created_at=created,
        ))

        # 不是每个会话都产生工单：这里 20 个会话对应 20 张单（演示数据刻意全部建单，
        # 真实情况大约一半；但看板要能算出"自助解决率"，需要另一批没建单的会话）
        cat_code = categories[i % 4]
        ticket = Ticket(
            conversation_id=conv.id,
            title=f"{cat_code} 咨询：客户提出问题 {i}",
            summary=f"客户咨询 {cat_code} 相关问题，需要人工跟进。",
            category=cat_code,
            priority=random.choice(["P0", "P1", "P2"]),
            status=status,
            assignee_id=random.choice(agents).id if status != "pending" else None,
            created_at=created,
            assigned_at=created + timedelta(minutes=2) if status != "pending" else None,
        )
        db.add(ticket)
        db.flush()
        ticket_total += 1

        # 客服首次回复（只有 assigned 之后的单才有）
        if status in ("processing", "resolved", "closed"):
            first_resp = created + timedelta(minutes=random.randint(1, 60))
            ticket.first_response_at = first_resp
            db.add(Message(
                conversation_id=conv.id, sender="agent",
                agent_id=ticket.assignee_id,
                content="您好，我是客服，正在为您处理。",
                created_at=first_resp,
            ))
            ticket.status = status
            db.add(TicketLog(
                ticket_id=ticket.id, operator_id=ticket.assignee_id,
                action="reply", to_value={"status": status},
                created_at=first_resp,
            ))

        if status in ("resolved", "closed"):
            resolved = created + timedelta(hours=random.randint(1, 8))
            ticket.resolved_at = resolved
            db.add(TicketLog(
                ticket_id=ticket.id, operator_id=ticket.assignee_id,
                action="resolve", from_value={"status": "processing"},
                to_value={"status": "resolved"}, created_at=resolved,
            ))
            db.add(Rating(
                ticket_id=ticket.id, score=random.choice([3, 4, 4, 5, 5, 5]),
                comment=random.choice([None, "解决了，谢谢", "还行", "回复有点慢"]),
                created_at=resolved,
            ))

        if status == "closed":
            ticket.closed_at = created + timedelta(hours=random.randint(9, 24))

    # ── 再造 10 个"AI 直接答上、没建单"的会话 —— 看板算自助解决率要用 ──
    for i in range(10):
        created = datetime.now(timezone.utc) - timedelta(days=random.randint(0, 6))
        conv = Conversation(visitor_key=f"visitor-ok-{i:03d}", status="closed", created_at=created)
        db.add(conv)
        db.flush()
        db.add(Message(conversation_id=conv.id, sender="visitor",
                       content="怎么开发票", created_at=created))
        db.add(Message(conversation_id=conv.id, sender="ai",
                       content="在账单中心 → 发票管理申请开票即可。",
                       kb_article_ids=[1], created_at=created + timedelta(seconds=2)))

    db.commit()
    print(f"  历史会话 30 个（其中 {ticket_total} 个建了工单，10 个 AI 直接答完）")


# ══════════════════════════════════════════════════════════════
def main() -> None:
    parser = argparse.ArgumentParser(description="灌入种子数据")
    parser.add_argument("--demo", action="store_true", help="额外灌入演示数据")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        seed_base(db)
        if args.demo:
            seed_demo(db)
        else:
            print("\n（未加 --demo，跳过演示数据）")
        print("\n完成。")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
