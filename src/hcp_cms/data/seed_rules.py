"""
seed_rules.py — 從舊版 rules_config.py 移轉完整規則至 HCP CMS 資料庫。

執行方式：
    .venv/Scripts/python.exe -m hcp_cms.data.seed_rules
"""

from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

from hcp_cms.data.database import DatabaseManager
from hcp_cms.data.models import ClassificationRule, Company
from hcp_cms.data.repositories import CompanyRepository, RuleRepository


# ──────────────────────────────────────────────────────────────
#  公司 Domain 對照表（來自 rules_config.py COMPANY_ALIAS）
# ──────────────────────────────────────────────────────────────
COMPANY_DOMAINS: list[tuple[str, str]] = [
    ("aseglobal.com",   "日月光集團"),
    ("ares.com.tw",     "亞瑞斯科技"),
    ("glthome.com.tw",  "茂林光電"),
    ("tpi.com.tw",      "東培工業"),
    ("unimicron.com",   "欣興電子"),
    ("namchow.com.tw",  "南僑集團"),
    ("fuhsing.com.tw",  "台灣福興工業"),
    ("flexium.com.tw",  "Flexium（台郡）"),
    ("winfoundry.com",  "穩懋半導體"),
    ("sanfang.com.tw",  "三方"),
]


# ──────────────────────────────────────────────────────────────
#  完整分類規則（來自 rules_config.py）
# ──────────────────────────────────────────────────────────────
RULES: list[tuple[str, str, str, int]] = [
    # (rule_type, pattern, value, priority)

    # ── product ──────────────────────────────────────────────
    (r"product", r"\bHCP\b|HRLF|HPAF|HPKF|APPF|HRAF|HRKF|HR[A-Z]{1,2}F\d", "HCP", 1),
    (r"product", r"weblogic|WLS", "WebLogic", 2),
    (r"product", r"\bERP\b", "ERP", 3),

    # ── issue ─────────────────────────────────────────────────
    (r"issue", r"客[制製]|客製化|customize", "客制需求", 0),
    (
        r"issue",
        r"新增.*(?:功能|需求|設定|欄位|報表|作業)"
        r"|(?:功能|需求|設定|欄位).*新增"
        r"|new\s*feature|是否.*(?:可以|能夠).*新增"
        r"|希望.*新增|需求.*提出|增加.*功能",
        "NEW", 1,
    ),
    (
        r"issue",
        r"bug|patch|ip_\d"
        r"|程式(?:邏輯|錯誤|問題|異常)"
        r"|計算(?:有誤|錯誤|不對|有問題)"
        r"|計算結果.*(?:不正確|有誤|錯誤)"
        r"|(?:金額|數字).*(?:有誤|錯誤|不正確)"
        r"|系統.*(?:bug|程式邏輯)|邏輯.*(?:有誤|錯誤)",
        "BUG", 2,
    ),
    (
        r"issue",
        r"建議.*(?:改善|改進|調整|優化)|改善.*建議"
        r"|希望.*(?:改善|改進|調整|優化)|優化"
        r"|improvement|enhance",
        "建議改善", 3,
    ),
    (
        r"issue",
        r"邏輯|計算.*(?:方式|規則|依據|原則)"
        r"|規則.*(?:確認|咨詢|詢問)|確認.*(?:計算|規則|邏輯)"
        r"|咨詢.*(?:規則|邏輯|計算)|法規.*(?:適用|規定|依據)"
        r"|依據.*法規|如何計算.*(?:方式|規則)",
        "邏輯咨詢", 4,
    ),
    (
        r"issue",
        r"無法(?:操作|執行|存(?:檔)?|匯出|匯入|登入|開啟|點選|使用)"
        r"|(?:操作|功能|系統|頁面).*異常|異常.*(?:操作|功能|系統|頁面)"
        r"|畫面.*(?:錯誤|異常|空白|當機)|功能.*(?:失效|不正常|無反應)"
        r"|系統.*(?:當機|無回應|卡住)|不正常.*(?:顯示|運作)",
        "操作異常", 5,
    ),
    (
        r"issue",
        r"如何(?:操作|設定|使用|建立|新增|匯入|匯出)"
        r"|怎麼(?:操作|設定|使用)|操作.*(?:說明|步驟|方式|確認)"
        r"|請問.*如何|如何.*請問|確認.*操作|操作.*諮詢|請協助.*說明",
        "OP", 6,
    ),
    (r"issue", r"其他|其它", "OTH", 7),

    # ── error（功能模組）─────────────────────────────────────
    (
        r"error",
        r"(?:HCP.*)?(?:安裝|install)"
        r"|資料庫.*(?:錯誤|異常|連線|連接|掛掉|down)"
        r"|database.*(?:error|fail|down)|DB.*(?:錯誤|異常|連線)"
        r"|ORA-\d+|SQL.*(?:錯誤|error|exception)"
        r"|環境.*(?:複製|搬移|建立)|伺服器.*(?:異常|錯誤|無法連線)|weblogic",
        "HCP安裝&資料庫錯誤", 1,
    ),
    (r"error", r"ESS.*PHP|PHP.*ESS|ess.*php|php.*ess", "ESS(PHP)", 2),
    (r"error", r"\bESS\b|員工.*自助.*服務|自助.*服務.*員工|EEF\b", "ESS(.NET)", 3),
    (
        r"error",
        r"客[制製].*程式|程式.*客[制製]|客製化.*程式|客製.*開發|定製.*程式",
        "客製程式", 4,
    ),
    (
        r"error",
        r"\bGL\b|G/L|拋轉|總帳.*分錄|分錄.*會計|會計.*拋轉|拋轉.*會計",
        "GL拋轉作業", 5,
    ),
    (
        r"error",
        r"所得稅|扣繳.*(?:申報|憑單)|申報.*扣繳|稅務.*申報|申報.*稅務"
        r"|稅率.*設定|設定.*稅率|薪資.*申報.*稅|稅.*申報",
        "所得稅處理", 6,
    ),
    (
        r"error",
        r"勞退(?!.*公積)|二代健保|補充保費|團(?:體)?保(?:險)?"
        r"|勞保費(?!.*一般)|健保費(?!.*一般)|費率.*(?:勞|健|退)"
        r"|(?:勞|健).*保費.*計算",
        "勞健團保、二代健保、勞退", 7,
    ),
    (
        r"error",
        r"(?:勞|健)保.*(?:加保|退保|轉保|異動|申報)|投保薪資"
        r"|社保(?!.*費率)|社會保險|加保|退保|轉保",
        "社會保險管理", 8,
    ),
    (r"error", r"福利金|welfare.*金|福利.*金額", "福利金處理", 9),
    (
        r"error",
        r"調薪(?!.*報表)|試算.*薪(?!資報表)|加薪.*試算|試算.*加薪"
        r"|薪資.*調整.*試算|試算.*薪資.*調整",
        "調薪試算", 10,
    ),
    (
        r"error",
        r"薪資.*(?:報表|明細表|清冊|總表|匯出.*表)"
        r"|薪資單(?!.*計算)|薪資表(?!.*計算)|薪資.*列印",
        "薪資報表", 11,
    ),
    (
        r"error",
        r"薪資|計薪|薪酬|獎金|全勤.*獎|平均工資"
        r"|工資(?!.*計算規則)|底薪|薪水|計費.*加班",
        "薪資獎金計算", 12,
    ),
    (
        r"error",
        r"警示.*設定|設定.*警示|alert.*設定|設定.*alert"
        r"|通知.*設定(?!.*簽核)|提醒.*設定|排程.*未觸發|alarm.*設定",
        "警示系統設定", 13,
    ),
    (
        r"error",
        r"系統參數|參數.*設定|設定.*參數|參數.*維護|維護.*參數|基本參數",
        "系統參數(參數設定)", 14,
    ),
    (
        r"error",
        r"系統.*(?:帳號|使用者|帳戶|權限)|帳號.*(?:管理|建立|設定|鎖定)"
        r"|使用者.*(?:管理|權限|設定)|權限.*設定|設定.*權限|角色.*設定|role.*設定",
        "系統管理", 15,
    ),
    (
        r"error",
        r"簽核|簽呈|電子.*簽(?!.*薪)|審核.*流程|流程.*審核"
        r"|核准.*設定|設定.*核准|代理.*簽核|簽核.*代理|工作流程",
        "簽核流程管理", 16,
    ),
    (r"error", r"績效|考核|KPI|KRA|評核|評分.*考核|考核.*評分", "績效考核管理", 17),
    (r"error", r"獎懲|懲處|記過|申誡|嘉獎|獎勵.*記錄|記錄.*獎懲", "員工獎懲管理", 18),
    (
        r"error",
        r"教育訓練|員工.*訓練|訓練.*員工|訓練.*課程|課程.*訓練|培訓|訓練.*記錄|記錄.*訓練",
        "員工教育訓練", 19,
    ),
    (
        r"error",
        r"自助.*分析|分析.*作業|自助.*查詢(?!.*請假)|報表.*自助",
        "自助分析作業", 20,
    ),
    (
        r"error",
        r"匯入(?!.*薪資)|資料.*匯入|匯入.*資料|import.*資料|匯入匯出",
        "匯入匯出作業", 21,
    ),
    (r"error", r"人事.*報表|人員.*報表|HR.*報表(?!.*薪資)|人資.*報表", "人事報表", 22),
    (
        r"error",
        r"組織(?!.*績效)|部門.*(?:建立|新增|設定|異動)|建立.*部門"
        r"|成本中心|組織.*架構|架構.*組織|組織圖",
        "組織部門建立", 23,
    ),
    (r"error", r"合約|契約|contract", "合約管理", 24),
    (r"error", r"住宿|宿舍|accommodation", "住宿管理", 25),
    (
        r"error",
        r"用餐|員工.*餐(?!.*訓練)|餐廳.*管理|管理.*餐廳|餐費",
        "員工用餐管理", 26,
    ),
    (
        r"error",
        r"工時|加班.*(?:時數|計算|申請|費用|記錄)|出勤.*工時|工時.*出勤"
        r"|工作.*時數|時數.*工作|超時(?!.*打卡)|OT(?:\s|$)",
        "工時管理", 27,
    ),
    (
        r"error",
        r"刷卡|打卡|簽到.*簽退|考勤.*卡(?!.*異常)|卡機|感應.*卡|門禁.*出勤",
        "刷卡管理", 28,
    ),
    (
        r"error",
        r"彈休|補休|彈性.*休假|休假.*彈性|補假|換休|彈性.*假",
        "彈休管理", 29,
    ),
    (
        r"error",
        r"年假|特休|特別.*休假|年度.*假期|假期.*年度|特休.*結算|結算.*特休",
        "年假管理", 30,
    ),
    (
        r"error",
        r"差勤|請假|假單|出勤.*記錄|考勤(?!.*卡)|請假.*記錄|記錄.*請假|出缺勤",
        "差勤請假管理", 31,
    ),
    (
        r"error",
        r"行事曆|排班|班表|班別.*(?:設定|新增|異動)|輪班|排班.*設定",
        "行事曆與排班", 32,
    ),
    (
        r"error",
        r"人事.*資料|員工.*資料(?!.*報表)|人員.*資料(?!.*報表)"
        r"|員工建檔|人員建檔|基本資料.*員工|員工.*基本資料"
        r"|人事.*建立|員工.*異動(?!.*請假)",
        "人事資料管理", 33,
    ),

    # ── priority ─────────────────────────────────────────────
    (
        r"priority",
        r"[（(]急[)）]|【急】|緊急|urgent|asap|ASAP|patch|程式邏輯",
        "高", 1,
    ),

    # ── broadcast ────────────────────────────────────────────
    (r"broadcast", r"維護客戶|更新公告|公告通知|大PATCH更新|法規因應", "廣播", 1),
    (r"broadcast", r"系統更新|月份PATCH|HCP維護", "廣播", 2),
]


def seed(conn: sqlite3.Connection, verbose: bool = True) -> dict:
    """移轉完整規則與公司 domain 至資料庫。"""
    rule_repo = RuleRepository(conn)
    company_repo = CompanyRepository(conn)

    stats = {"rules_deleted": 0, "rules_inserted": 0, "companies_inserted": 0, "companies_skipped": 0}

    # ── 清除舊規則（保留 handler / progress，只換 product/issue/error/priority/broadcast）
    for rtype in ("product", "issue", "error", "priority", "broadcast"):
        deleted = conn.execute(
            "DELETE FROM classification_rules WHERE rule_type = ?", (rtype,)
        ).rowcount
        stats["rules_deleted"] += deleted
    conn.commit()

    # ── 插入完整規則
    for rule_type, pattern, value, priority in RULES:
        rule_repo.insert(ClassificationRule(
            rule_type=rule_type,
            pattern=pattern,
            value=value,
            priority=priority,
        ))
        stats["rules_inserted"] += 1

    # ── 插入公司 Domain（company_id 用 domain 的前綴取名）
    existing = {row[0] for row in conn.execute("SELECT domain FROM companies").fetchall()}
    for domain, name in COMPANY_DOMAINS:
        if domain in existing:
            stats["companies_skipped"] += 1
            continue
        company_id = domain.split(".")[0].upper()
        # 確保 company_id 不重複
        suffix = 1
        base_id = company_id
        while conn.execute("SELECT 1 FROM companies WHERE company_id = ?", (company_id,)).fetchone():
            company_id = f"{base_id}{suffix}"
            suffix += 1
        company_repo.insert(Company(
            company_id=company_id,
            name=name,
            domain=domain,
        ))
        stats["companies_inserted"] += 1

    if verbose:
        print(f"規則：刪除舊規則 {stats['rules_deleted']} 條，新增 {stats['rules_inserted']} 條")
        print(f"公司：新增 {stats['companies_inserted']} 家，跳過已存在 {stats['companies_skipped']} 家")

    return stats


def main() -> None:
    db_path = Path(os.environ.get("APPDATA", str(Path.home()))) / "HCP_CMS" / "cs_tracker.db"
    if not db_path.exists():
        print(f"資料庫不存在：{db_path}")
        sys.exit(1)
    db = DatabaseManager(db_path)
    db.initialize()
    seed(db.connection, verbose=True)
    db.close()
    print("移轉完成！")


if __name__ == "__main__":
    main()
