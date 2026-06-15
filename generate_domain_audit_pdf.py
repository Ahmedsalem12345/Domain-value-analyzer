from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    PageBreak,
)
import arabic_reshaper
from bidi.algorithm import get_display
from pathlib import Path


ROOT = Path(__file__).resolve().parent
OUT = ROOT / "Domain_Engine_Deep_Audit_AR.pdf"

FONT_PATHS = [
    "/Library/Fonts/Arial Unicode.ttf",
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "/System/Library/Fonts/SFArabic.ttf",
    "/System/Library/Fonts/GeezaPro.ttc",
]


def register_font():
    for path in FONT_PATHS:
        if Path(path).exists():
            try:
                pdfmetrics.registerFont(TTFont("ArabicFont", path))
                pdfmetrics.registerFont(TTFont("ArabicFontBold", path))
                return
            except Exception:
                continue
    raise RuntimeError("No Arabic-capable font found")


def rtl(text: str) -> str:
    if not text:
        return ""
    reshaped = arabic_reshaper.reshape(text)
    return get_display(reshaped)


def p(text, style):
    return Paragraph(rtl(text), style)


def cell(text, style):
    return Paragraph(rtl(str(text)), style)


def make_table(rows, widths=None, font_size=9):
    body = ParagraphStyle(
        "TableCell",
        fontName="ArabicFont",
        fontSize=font_size,
        leading=font_size + 4,
        alignment=TA_RIGHT,
    )
    header = ParagraphStyle(
        "TableHeader",
        fontName="ArabicFontBold",
        fontSize=font_size,
        leading=font_size + 4,
        alignment=TA_CENTER,
        textColor=colors.white,
    )
    shaped = []
    for i, row in enumerate(rows):
        shaped.append([cell(x, header if i == 0 else body) for x in row])
    t = Table(shaped, colWidths=widths, hAlign="RIGHT", repeatRows=1)
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#23395d")),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#b9c2d0")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f6f8fb")]),
            ]
        )
    )
    return t


def add_bullets(story, items, style):
    for item in items:
        story.append(p("• " + item, style))
    story.append(Spacer(1, 0.15 * cm))


def footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("ArabicFont", 8)
    canvas.setFillColor(colors.HexColor("#667085"))
    canvas.drawString(1.5 * cm, 1.0 * cm, f"{doc.page}")
    canvas.restoreState()


register_font()

styles = getSampleStyleSheet()
title = ParagraphStyle(
    "TitleAR",
    parent=styles["Title"],
    fontName="ArabicFontBold",
    fontSize=22,
    leading=30,
    alignment=TA_CENTER,
    spaceAfter=16,
)
h1 = ParagraphStyle(
    "H1AR",
    fontName="ArabicFontBold",
    fontSize=17,
    leading=24,
    alignment=TA_RIGHT,
    textColor=colors.HexColor("#17233c"),
    spaceBefore=14,
    spaceAfter=8,
)
h2 = ParagraphStyle(
    "H2AR",
    fontName="ArabicFontBold",
    fontSize=13,
    leading=20,
    alignment=TA_RIGHT,
    textColor=colors.HexColor("#25476a"),
    spaceBefore=10,
    spaceAfter=6,
)
body = ParagraphStyle(
    "BodyAR",
    fontName="ArabicFont",
    fontSize=10.5,
    leading=18,
    alignment=TA_RIGHT,
    spaceAfter=6,
)
note = ParagraphStyle(
    "NoteAR",
    fontName="ArabicFont",
    fontSize=9.5,
    leading=16,
    alignment=TA_RIGHT,
    textColor=colors.HexColor("#475467"),
    leftIndent=0,
    rightIndent=8,
    spaceAfter=6,
)

story = []

story.append(p("تدقيق عميق لمحرك تقييم الدومينات", title))
story.append(p("Domain Value Analyzer V4", title))
story.append(p("تحليل معماري ونقد استثماري للنظام من إدخال الدومين إلى قرار BUY / HOLD / PASS", body))
story.append(Spacer(1, 0.4 * cm))
story.append(
    make_table(
        [
            ["البند", "الخلاصة"],
            ["نوع التقرير", "تدقيق نظام كامل: الكود، منطق القرار، تدفق البيانات، ومحركات السكور"],
            ["الهدف العملي", "تحويل الأداة من مصفاة إشارات إلى ماكينة أفضل لاكتشاف كنوز الدومينات"],
            ["الحكم العام", "Research Prototype قوي، لكنه ليس Production-ready كآلة شراء آلية"],
            ["التقييم العام", "6.8 / 10"],
        ],
        widths=[4.3 * cm, 11.7 * cm],
        font_size=10,
    )
)

story.append(p("ملخص تنفيذي", h1))
story.append(
    p(
        "المشروع مبني حول فكرة صحيحة: لا يقيّم الدومين كسيو فقط، بل كأصل يمكن بيعه بربح. "
        "أقوى جزء فيه هو KPS لأنه يستند إلى بيانات مبيعات دومينات فعلية، ثم يمرر هذه الإشارة إلى النية التجارية، الطلب، السيولة، والتسعير. "
        "لكن المشكلة الجوهرية أن النظام يملك أدوات قوية ولا يملك طبقة معايرة واستراتيجية قرار بنفس القوة. لذلك يلتقط كثيرًا من الدومينات الجيدة، لكنه لا يفرز الذهب بدقة كافية.",
        body,
    )
)
story.append(
    p(
        "أخطر عيب ليس في وجود نقص واحد، بل في تداخل عدة أنظمة: KPS يدخل في أكثر من موضع، التصنيف الإجباري يغيّر تفسير نفس الدومين، الفلاتر قد تستبعد قبل أن تفهم القيمة، وقرار BUY/HOLD/PASS يعتمد على مجموع رقمي لا يميّز بين فرصة سائلة حقيقية وفرصة ذات إشارات جميلة لكن صعبة البيع.",
        body,
    )
)

story.append(p("كيف يعمل المشروع؟", h1))
story.append(p("1. البنية العامة للنظام", h2))
story.append(
    p(
        "التدفق التشغيلي يبدأ من app.py. المستخدم يدخل دومينات يدويًا أو يرفع CSV. يتم تنظيف الدومين، استخراج أعمدة مثل CPC وSV وREG وRDT وABY، ثم تخزينها في SQLite عبر database.py. بعد ذلك يستدعي المسار /api/start دالة process_domain في analyzer/pipeline.py لكل دومين.",
        body,
    )
)
add_bullets(
    story,
    [
        "config.py: مركز الثوابت: عتبات القرار، أوزان المحاور، مضاعفات TLD، قوائم النيتش، العقوبات.",
        "filters.py: بوابة الاستبعاد المبكر: علامات تجارية، كلمات محظورة، وقراءة لغوية للجبرش.",
        "market_scorer.py: القلب الاستثماري؛ يصنف نوع الدومين ويسجل المحاور الستة ويولد القرار.",
        "retail_kps.py: محرك Keyword Power Score القائم على retailstats، وهو أقوى إشارة سوقية في النظام.",
        "geo_service.py وword_data.py: كشف النيتش، الجغرافيا، الكلمات، الجمع والمفرد، وجودة السوق الجغرافي.",
        "enrichments.py: كشف سبام بسيط وتقدير سعر مرسخ ببيانات KPS عند توفرها.",
        "brandable_scorer.py: محرك مستقل لتقييم قابلية البراند، لكنه لا يغيّر القرار النهائي إلا كحقل إضافي.",
    ],
    body,
)

story.append(p("2. التدفق الكامل من الدومين إلى القرار", h2))
story.append(
    make_table(
        [
            ["المرحلة", "ما يحدث", "الأثر على القرار"],
            ["الإدخال والتنظيف", "إزالة http وwww والتحقق من شكل الدومين", "الدومينات غير الصالحة لا تدخل التحليل"],
            ["الفلاتر المبكرة", "علامات تجارية، كلمات محظورة، جبرش", "قد تستبعد الدومين قبل أي تقدير سوقي"],
            ["كشف السياق", "detect_geo وdetect_niche وscore_kps", "بناء صورة عن الجغرافيا، المجال، وقوة الكلمة"],
            ["تصنيف النوع", "seo_keyword / local_service / global_service / brandable / content_media / low_value", "التصنيف يحدد قواعد المحاور اللاحقة"],
            ["المحاور الستة", "Commercial, Demand, Clarity, Buyers, Geo+Niche, Liquidity", "تكوين مجموع أولي من 100 قبل التعديلات"],
            ["العقوبات والمكافآت", "Personal name، Long unclear، age bonus، KPS evidence bonus", "تدفع النتيجة أعلى أو أسفل خارج المحاور"],
            ["مضاعف TLD", "يضرب مجموع المحاور الإيجابية فقط", ".com يحتفظ بالقيمة، والامتدادات الأضعف تخفض السكور"],
            ["القرار", "GEM ≥78، BUY ≥60، HOLD ≥40، أقل من ذلك PASS", "قرار نهائي واحد مبني على المجموع"],
            ["السعر", "estimate_historical_price يستخدم KPS avg وscore/type/niche/TLD", "ليس جزءًا من القرار لكنه يؤثر على قراءة الربحية"],
        ],
        widths=[3.1 * cm, 7.5 * cm, 5.4 * cm],
        font_size=8.8,
    )
)

story.append(p("3. نظام الفلترة Filtering Engine", h2))
story.append(
    p(
        "الفلاتر تعمل قبل السكور، وهذا يجعلها خط دفاع مفيد وخط خطر في نفس الوقت. trademark_filter يستبعد المطابقة التامة أو prefix/suffix للعلامات المعروفة، مع استثناء كلمات عامة مثل meta وdelta وgemini. hard_filter يستبعد كلمات مخاطر حقيقية مثل phishing وviagra وponzi. smart_readability_filter يحاول منع الجبرش عبر نسبة الحروف المتحركة، التكرار، وتجمعات الحروف الساكنة.",
        body,
    )
)
story.append(
    make_table(
        [
            ["القاعدة", "قوتها", "نقطة الضعف"],
            ["Trademark", "تمنع شراء دومينات قانونيًا خطرة مثل openaihelp.com", "قائمة ثابتة وليست بحثًا قانونيًا؛ وقد تخطئ في كلمات لها معنى عام"],
            ["Hard words", "تمنع الدومينات السامة بوضوح", "لا يوجد وزن للمخاطر المنظمة؛ إما استبعاد أو لا شيء"],
            ["Readability", "تزيل xzqwplm.com قبل استنزاف التحليل", "قد تظلم أسماء قصيرة غير إنجليزية أو براندات صعبة لكنها قابلة للبيع"],
            ["Spam detection", "يخصم بعد السكور لكلمات سبام محددة", "ليس تاريخًا حقيقيًا للسبام؛ هو قائمة كلمات فقط، والاسم يوحي بأكثر مما يفعل"],
        ],
        widths=[3.2 * cm, 6.0 * cm, 6.8 * cm],
        font_size=8.8,
    )
)

story.append(p("4. نظام التقييم Scoring System", h2))
story.append(
    p(
        "النظام يعلن أن المحاور تساوي 100 نقطة: 25 للنية التجارية، 20 للطلب، 15 للوضوح، 15 لحوض المشترين، 15 للجغرافيا والنيتش، و10 للسيولة. لكن في الواقع القرار النهائي ليس فقط هذه المحاور؛ هناك مضاعف TLD، عقوبات، مكافأة عمر للبراندات، ومكافأة KPS مباشرة. لذلك مجموع المحاور ليس القصة كاملة.",
        body,
    )
)
story.append(
    make_table(
        [
            ["المحور", "المدخلات", "طريقة الحساب", "القوة", "الضعف"],
            ["Clarity", "الكلمة، القواميس، geo، niche، KPS coverage", "يعطي نقاطًا للكلمة المفهومة، الجيو الصافي، المركب، أو تغطية KPS", "يلتقط أمثلة مثل parallelai.com عندما يغطي KPS معظم الاسم", "لا يقيس جودة المعنى التجاري بعمق؛ parallel+ai واضح لكن ليس بالضرورة مشتريه كثيرون"],
            ["Geo + Niche", "detect_geo، detect_niche، جودة السوق الجغرافي", "مصفوفة نيتش tier × جودة سوق 1-4", "أفضل جزء في فهم local services", "يخلط أحيانًا السوق المحلي الحقيقي مع سوق .com الإنجليزي؛ omdurmaninsurance.com بقي BUY رغم ضعف الجيو"],
            ["Buyer Pool", "نوع الدومين، niche profitability، REG، RDT، KPS total sales", "local_service يبدأ عالياً، brandable يعتمد على REG والكلمات", "يفهم أن miamilawyer له مشترون أكثر من zentrova", "سهل التضخيم بسبب KPS/RDT حتى عندما المشتري النهائي غير واضح"],
            ["Liquidity", "نوع الدومين، CPC، age، KPS sales، جودة الجيو", "local service سريع إذا السوق جيد، SEO يتأثر بالـ CPC، brandable بطيء", "يفرق بين البيع السريع والاسم الجميل", "لا يستخدم بيانات sell-through فعلية ولا تكلفة الاستحواذ"],
            ["Commercial Intent", "KPS، CPC، niche boost، transactional words", "KPS هو الأساس ثم CPC وboost", "يركز على مبيعات فعلية لا انطباع لغوي فقط", "KPS يهيمن؛ myshop4less.com حصل على 15 تجاريًا رغم أنه low_value"],
            ["Market Demand", "KPS sales، SV، RDT، REG، ABY", "نقاط حسب حجم مبيعات KPS ثم إشارات السوق", "يعمل بدون APIs مدفوعة", "يمزج طلب الكلمة مع طلب الدومين نفسه؛ كلمة قوية داخل اسم ضعيف قد ترفع النتيجة أكثر من اللازم"],
        ],
        widths=[2.3 * cm, 3.0 * cm, 3.6 * cm, 3.5 * cm, 3.6 * cm],
        font_size=7.3,
    )
)

story.append(PageBreak())
story.append(p("KPS Engine", h1))
story.append(
    p(
        "KPS هو أهم جزء في المشروع لأنه يحاول الإجابة على السؤال الأقرب للربح: هل الكلمات داخل هذا الدومين لها مبيعات دومينات حقيقية؟ الملف retail_kps.py يحمّل retailstats_20260427.csv أولًا، ثم يستخرج الكلمات عبر Weighted Interval Scheduling لاختيار كلمات غير متداخلة، ثم يحسب signal لكل token بناءً على المبيعات والأسعار والموقع داخل الاسم.",
        body,
    )
)
add_bullets(
    story,
    [
        "الاستخراج: يبحث في كل كلمات retailstats، يتجنب stopwords والرموز القصيرة الضعيفة، ثم يختار أفضل تغطية غير متداخلة.",
        "السكور: يعتمد على log(total_sales)، log(price_est)، max price، position weight، وdampening للتذبذب CV.",
        "التجميع: لا يجمع كل الكلمات بعنف؛ يأخذ أفضل token كمرساة ويضيف combo boost مضبوطًا للأنماط مثل geo+service أو premium_cluster.",
        "الثقة: kps_confidence من 0 إلى 1، لكنها في التطبيق الحالي غالبًا تصبح 1 بسرعة، مما يضعف قيمتها كفرامل.",
        "الاستهلاك downstream: يدخل KPS في Commercial Intent، Market Demand، Buyer Pool، Liquidity، Clarity boost، KPS Evidence Bonus، والتسعير.",
    ],
    body,
)
story.append(
    make_table(
        [
            ["الدومين", "سلوك النظام الحالي", "قراءة نقدية"],
            ["parallelai.com", "BUY 65، KPS premium 78.9، tokens: parallel + ai، وضوح 11", "مثال جيد: KPS أنقذ اسمًا لا تكفيه القواميس التقليدية. لكن Buyer Pool وLiquidity افتراضيان أكثر من كونهما مبنيين على مشترين محددين."],
            ["myshop4less.com", "HOLD 44، low_value، KPS premium بسبب shop + less", "False positive جزئي: الاسم ضعيف تجاريًا، لكن KPS أعطاه نية وطلبًا أكبر مما يستحق."],
            ["omdurmaninsurance.com", "BUY 70 رغم GeoNiche 5 وسيولة 6", "هنا يظهر تضارب: النظام يعرف أن الجيو ضعيف لكنه لا يخفض القرار بما يكفي."],
            ["casino.com", "BUY 66 وليس GEM رغم KPS ultra وسعر تقديري كبير", "قد يكون التصنيف والمحاور غير مناسبة للكلمات premium single-word؛ النظام لا يملك مسارًا خاصًا لأصول الدرجة النادرة."],
            ["taxi.com", "HOLD 48 رغم KPS ultra وسعر تقديري 19k-41k", "مثال على ضياع الذهب: كلمة قصيرة تجارية عالمية قد تُظلم لأنها لا تدخل نيتش واضح ولا حوض مشترين مضبوط."],
        ],
        widths=[3.0 * cm, 5.3 * cm, 7.7 * cm],
        font_size=8.2,
    )
)

story.append(p("كيف يتم اتخاذ القرار النهائي؟", h2))
story.append(
    p(
        "القرار النهائي لا يصدر من قاعدة واحدة، بل من مجموع رقمي: axes_sum يضرب في TLD multiplier، ثم تضاف العقوبات والمكافآت. بعد ذلك يتم ضغط النتائج فوق 70 بمنحنى diminishing returns، ثم تطبق العتبات: GEM من 78، BUY من 60، HOLD من 40، PASS أقل من 40. المشكلة أن العتبات لا تفهم نوع الفرصة. BUY في local service ضعيف الجيو ليس مثل BUY في كلمة عالمية قصيرة.",
        body,
    )
)

story.append(p("العيوب القاتلة داخل المشروع", h1))
story.append(
    make_table(
        [
            ["العيب", "السبب", "مثال واقعي", "تأثيره على الربحية"],
            ["KPS يملك نفوذًا واسعًا بلا حوكمة كافية", "يدخل في عدة محاور ثم كـ bonus وتسعير", "myshop4less.com يتحول إلى HOLD رغم low_value", "يضيع وقت البحث اليدوي على دومينات مزيفة الإشارة"],
            ["التصنيف الإجباري يختزل الدومين في نوع واحد", "domain_type واحد يتحكم في كل المحاور", "casino.com خرج brandable/BUY بدل مسار premium keyword خاص", "قد تفلت أصول ممتازة من GEM أو تُفهم في السوق الخطأ"],
            ["لا يوجد فصل بين قيمة الكلمة وقابلية بيع الاسم الحالي", "KPS يقيس keyword market لا sell-through للدومين نفسه", "insurance داخل omdurmaninsurance يرفع الدومين رغم ضعف الجيو", "شراء دومينات تحمل كلمة ذهبية داخل تركيب غير قابل للبيع"],
            ["جودة الجيو تعرف الخطر لكنها لا توقفه", "GeoNiche ينخفض، لكن BuyerPool/Liquidity لا تسقط كفاية", "omdurmaninsurance.com = BUY 70", "رأس المال يذهب لأسواق لا يوجد فيها مشترون فعليون بسهولة"],
            ["Brandable engine منفصل عن القرار", "يسجل BrandableScore بعد القرار ولا يعيد وزن النتيجة", "marklogic.com HOLD وBrandableScore 56 لا يغير المسار", "تفويت أسماء براند جيدة أو رفع أسماء keyword ضعيفة بلا توازن"],
            ["الفلاتر قبل الفهم الكامل", "استبعاد مبكر قبل score/domain context", "أسماء غير إنجليزية أو صعبة النطق قد تسقط كجبرش", "False negatives في براندات قصيرة أو أسواق غير إنجليزية"],
            ["التسعير قد يبدو أدق من حقيقته", "Price estimate يرسو على avg KPS حتى لو التركيب مختلف", "bestinsurance.com سعر مرتفع بسبب insurance suffix", "توقع ربح غير واقعي يؤدي لمزايدات شراء خاطئة"],
            ["لا يوجد calibration dataset للقرارات", "الاختبارات تركز على KPS parsing ولا توجد labels بيع/عدم بيع", "pytest غير مثبت في venv الحالي", "النظام لا يعرف إن كان BUY يحقق sell-through فعلاً"],
        ],
        widths=[3.3 * cm, 4.3 * cm, 3.8 * cm, 4.6 * cm],
        font_size=7.4,
    )
)

story.append(p("لماذا لا يخرج أفضل الدومينات رغم امتلاكه أدوات قوية؟", h2))
story.append(
    p(
        "لأن النظام ممتاز في التقاط signals، لكنه أضعف في ترتيبها استثماريًا. الذهب الحقيقي يحتاج ثلاث طبقات لا تكفي واحدة منها وحدها: معنى قوي، مشترون واضحون، وسيولة واقعية بسعر دخول مناسب. المشروع يقيس كل طبقة جزئيًا، لكنه يسمح لإشارة واحدة مثل KPS أو local_service base أن تغطي على ضعف طبقة أخرى. لذلك تظهر دومينات جيدة، لكن قائمة القمة ليست بالضرورة أفضل قائمة للشراء.",
        body,
    )
)
add_bullets(
    story,
    [
        "High-value domains تضيع عندما تكون كلمة قصيرة عالمية لا تدخل نيتش واضح، مثل taxi.com الذي خرج HOLD.",
        "False positives تظهر عندما توجد كلمة مباعة داخل تركيب تسويقي ضعيف، مثل myshop4less.com.",
        "Local-service domains تُرفع بقواعد buyer pool عامة حتى عندما الجيو ضعيف في سوق .com الإنجليزي.",
        "القرار النهائي لا يعرف تكلفة acquisition ولا هامش الربح المتوقع ولا sell-through probability.",
    ],
    body,
)

story.append(PageBreak())
story.append(p("التحسينات الاستراتيجية", h1))
story.append(p("1. تحسينات فورية Quick Wins", h2))
add_bullets(
    story,
    [
        "أضف حقل RiskFlags مستقل: weak_geo_market، kps_overrides_low_value، poor_brand_fit، low_confidence_price.",
        "اخفض القرار درجة واحدة تلقائيًا عندما يكون GeoNiche ≤5 مع Geo+Niche domain إلا إذا كان هناك REG/RDT قوي جدًا أو CPC حقيقي.",
        "امنع low_value من الوصول إلى HOLD/BUY عبر KPS وحده إلا إذا كانت التغطية ≥0.8 والثقة عالية والكلمات ليست common inflated.",
        "اعرض axes_sum قبل وبعد TLD وKPS bonus في UI حتى يرى المستخدم سبب الرفع أو الخفض.",
        "ثبت pytest أو أضفه إلى requirements.txt حتى تصبح اختبارات KPS قابلة للتشغيل فورًا.",
    ],
    body,
)

story.append(p("2. تحسينات متوسطة", h2))
add_bullets(
    story,
    [
        "افصل KPS إلى قيمتين: KeywordMarketValue وNameFit. الأولى تقيس مبيعات الكلمة، والثانية تقيس هل التركيب الحالي قابل للبيع.",
        "استبدل قرار النوع الواحد بنظام multi-label: يمكن للدومين أن يكون AI keyword + brandable + global service مع أوزان.",
        "أضف Sellability Gate قبل BUY: وضوح كاف، مشتري محدد، امتداد مناسب، وعدم وجود خطر جيو أو تركيب ضعيف.",
        "أعد معايرة عتبات GEM/BUY حسب نوع الدومين. local_service ليس مثل single-word premium وليس مثل brandable.",
        "استخدم price-to-score sanity check: إذا السعر المقدر عالٍ لكن السيولة أو buyer pool منخفضة، أضف تحذيرًا ولا ترفع القرار.",
        "اجعل confidence حقيقية: لا تكفي 10 مبيعات عامة للوصول إلى 1.0؛ يجب احتساب position confidence وcoverage confidence وvariance.",
    ],
    body,
)

story.append(p("3. تحسينات عميقة Architectural Refactor", h2))
add_bullets(
    story,
    [
        "ابن طبقة Decision Engine منفصلة عن Scoring Engine. السكور يصف الإشارات، أما القرار فيطبق قواعد الاستثمار والمخاطر.",
        "استخدم نموذج ranker فوق المحاور: OpportunityScore = expected resale value × sell-through probability - acquisition cost - risk penalty.",
        "اجعل KPS خدمة مستقلة تعيد token_details كاملة، alternative parses، وسبب اختيار parse، وليس فقط best_match.",
        "أضف Benchmark Set حقيقي: دومينات مباعة، دومينات غير مباعة، دومينات اشتريت وخسرت، ودومينات ربحت. بدون ذلك ستبقى المعايرة ذوقية.",
        "أنشئ Buyer Intent Simulator: من هم المشترون؟ كم عددهم؟ هل هم SMB محليون أم startups أم affiliate marketers؟ ما قناة البيع؟",
        "حوّل الفلاتر من hard exclusion إلى staged risk scoring لبعض الحالات، مع إبقاء trademark والخطر القانوني كاستبعاد صارم.",
    ],
    body,
)

story.append(p("تقييم النظام", h1))
story.append(
    make_table(
        [
            ["المحور", "التقييم", "السبب المختصر"],
            ["KPS Engine", "8.0 / 10", "تصميم جيد بعد إعادة البناء: WIS، log signal، confidence، وتغطية. يحتاج معايرة أقسى للثقة وNameFit."],
            ["Clarity Axis", "7.0 / 10", "يفهم الكلمات والجيو وKPS coverage، لكنه لا يفرق دائمًا بين وضوح لغوي ووضوح بيعي."],
            ["Geo + Niche", "7.5 / 10", "مصفوفة ذكية جدًا، لكنها لا تملك veto كافيًا عند الأسواق الضعيفة."],
            ["Buyer Pool", "6.5 / 10", "منطقي كتصور، لكنه يعتمد على قواعد عامة لا على تعداد مشترين فعلي."],
            ["Liquidity", "6.0 / 10", "بداية جيدة، لكن لا توجد sell-through data أو قنوات بيع أو سعر دخول."],
            ["Filtering", "6.5 / 10", "مفيد أمنيًا، لكنه مبكر وثابت وقد ينتج false negatives."],
            ["Pricing", "5.8 / 10", "KPS anchoring مفيد، لكن نطاقات السعر قد تعطي ثقة أكثر مما ينبغي."],
            ["Architecture", "6.2 / 10", "المكونات واضحة، لكن القرار والتقييم والتسعير متشابكة."],
            ["Testing/Production", "4.8 / 10", "توجد اختبارات KPS، لكن البيئة لا تشغل pytest ولا يوجد benchmark ربحي."],
            ["التقييم العام", "6.8 / 10", "نواة قوية تحتاج حوكمة قرار ومعايرة ربحية."],
        ],
        widths=[4.0 * cm, 2.4 * cm, 9.6 * cm],
        font_size=8.6,
    )
)

story.append(p("هل النظام Production-ready؟", h2))
story.append(
    p(
        "الحكم الصريح: النظام ليس Production-ready كآلة شراء آلية. هو Research Prototype قوي ومفيد جدًا للفرز الأولي والتحليل المساعد. يمكن استخدامه لتقليل قائمة كبيرة إلى قائمة مرشحين، لكن لا ينبغي أن يشتري أو يوصي بشراء نهائي بدون مراجعة بشرية وسعر دخول وبيانات سوق إضافية.",
        body,
    )
)
story.append(p("الخلاصة الاستثمارية", h2))
story.append(
    p(
        "لتحويله إلى ماكينة ربح، لا تبدأ بزيادة القوائم أو إضافة كلمات. ابدأ بفصل الإشارات عن القرار. اجعل KPS يقول: هذه الكلمة لها سوق. واجعل Decision Engine يسأل: هل هذا الاسم بهذه الصيغة وبهذا الامتداد وبهذا السعر يمكن بيعه لمشتر واضح خلال مدة مقبولة؟ عندها فقط ستبدأ الأداة في استخراج الذهب بدل استخراج كل ما يلمع.",
        body,
    )
)

doc = SimpleDocTemplate(
    str(OUT),
    pagesize=A4,
    rightMargin=1.45 * cm,
    leftMargin=1.45 * cm,
    topMargin=1.45 * cm,
    bottomMargin=1.45 * cm,
    title="Domain Engine Deep Audit AR",
    author="Codex",
)
doc.build(story, onFirstPage=footer, onLaterPages=footer)
print(OUT)
