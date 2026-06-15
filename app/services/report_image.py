"""
报告图片生成服务。

使用 Pillow 将课堂分析报告 + 家长报告渲染为 PNG 图片，
支持中文排版、自动换行、颜色标记，可直接下载分享。

图标使用纯 Unicode 符号（✓ ✗ ! ●），避免 emoji 在中文字体下显为方框。
"""
import io
import logging
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

# ─── 布局常量 ───
WIDTH = 800
PADDING_H = 40
PADDING_V = 24
HEADER_HEIGHT = 90
SECTION_GAP = 16
CARD_RADIUS = 8

# ─── 颜色 ───
COLOR_BG = (255, 255, 255)
COLOR_HEADER_BG = (26, 115, 232)
COLOR_HEADER_TEXT = (255, 255, 255)
COLOR_TITLE = (33, 33, 33)
COLOR_BODY = (51, 51, 51)
COLOR_MUTED = (136, 136, 136)
COLOR_SECTION_BG = (248, 249, 250)
COLOR_CARD_BG = (255, 255, 255)
COLOR_BORDER = (218, 220, 224)
COLOR_RED = (217, 48, 37)
COLOR_ORANGE = (230, 81, 0)
COLOR_GREEN = (24, 128, 56)
COLOR_BLUE = (26, 115, 232)
COLOR_DIVIDER = (232, 234, 237)

# ─── 字体缓存 ───
_fonts: dict[str, ImageFont.FreeTypeFont] = {}


def _find_chinese_font(size: int = 18) -> ImageFont.FreeTypeFont:
    """查找系统可用的中文字体。

    按优先级尝试多个常见路径，确保中文能正常渲染。
    """
    cache_key = f"body_{size}"
    if cache_key in _fonts:
        return _fonts[cache_key]

    # Windows / Linux / macOS 常见中文字体路径
    candidates = [
        # Windows
        "C:/Windows/Fonts/msyh.ttc",       # 微软雅黑
        "C:/Windows/Fonts/msyhbd.ttc",     # 微软雅黑粗体
        "C:/Windows/Fonts/simhei.ttf",     # 黑体
        "C:/Windows/Fonts/simsun.ttc",     # 宋体
        "C:/Windows/Fonts/simfang.ttf",    # 仿宋
        "C:/Windows/Fonts/kaiu.ttf",       # 楷体
        # macOS
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
        "/System/Library/Fonts/STHeiti Light.ttc",
        "/System/Library/Fonts/STHeiti Medium.ttc",
        # Linux
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
        "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    ]

    for path in candidates:
        if Path(path).exists():
            try:
                font = ImageFont.truetype(path, size)
                _fonts[cache_key] = font
                logger.debug(f"Using Chinese font: {path}")
                return font
            except Exception:
                continue

    # 最终兜底：PIL 默认字体（无法渲染中文）
    logger.warning("No Chinese font found, Chinese characters may not render")
    font = ImageFont.load_default()
    _fonts[cache_key] = font
    return font


def _get_font(size: int = 18, bold: bool = False) -> ImageFont.FreeTypeFont:
    """获取指定大小的字体（自动查找中文字体）。"""
    cache_key = f"{'bold' if bold else 'body'}_{size}"
    if cache_key in _fonts:
        return _fonts[cache_key]

    # 粗体尝试微软雅黑粗体
    if bold:
        bold_candidates = [
            "C:/Windows/Fonts/msyhbd.ttc",
            "C:/Windows/Fonts/simhei.ttf",
        ]
        for path in bold_candidates:
            if Path(path).exists():
                try:
                    font = ImageFont.truetype(path, size)
                    _fonts[cache_key] = font
                    return font
                except Exception:
                    pass

    # 回退到普通字体
    font = _find_chinese_font(size)
    _fonts[cache_key] = font
    return font


def _font_line_height(font: ImageFont.FreeTypeFont) -> int:
    """根据字体实际度量值计算行高（含行间距）。

    Pillow 的 FreeTypeFont 没有直接返回 line-height 的方法，
    通过 textbbox 测量「汉」的上下高度，加 1.7× 安全间距。
    """
    # 使用临时 draw 测量
    measure_img = Image.new("RGB", (1, 1))
    measure_draw = ImageDraw.Draw(measure_img)
    bbox = measure_draw.textbbox((0, 0), "汉", font=font)
    char_h = bbox[3] - bbox[1]
    return max(int(char_h * 1.7), font.size + 10)


def _measure_text(s: str, font: ImageFont.FreeTypeFont) -> int:
    """测量文本宽度（像素）。"""
    measure_img = Image.new("RGB", (1, 1))
    measure_draw = ImageDraw.Draw(measure_img)
    bbox = measure_draw.textbbox((0, 0), s, font=font)
    return bbox[2] - bbox[0]


# ═══════════════════════════════════════════════════════════
# 文本换行
# ═══════════════════════════════════════════════════════════

def _wrap_lines(
    draw: ImageDraw.Draw,
    text: str,
    font: ImageFont.FreeTypeFont,
    max_width: int,
) -> list[str]:
    """将文本按 max_width 拆分为多行（支持显式换行 \\n）。"""
    if not text:
        return []
    lines: list[str] = []
    # 先按显式换行拆分段落，再逐段按宽度换行
    for paragraph in text.split("\n"):
        if not paragraph:
            lines.append("")  # 空行
            continue
        current = ""
        for ch in paragraph:
            test = current + ch
            bbox = draw.textbbox((0, 0), test, font=font)
            if (bbox[2] - bbox[0]) > max_width and current:
                lines.append(current)
                current = ch
            else:
                current = test
        if current:
            lines.append(current)
    return lines


def _draw_wrapped_text(
    draw: ImageDraw.Draw,
    text: str,
    font: ImageFont.FreeTypeFont,
    x: int,
    y: int,
    max_width: int,
    color: tuple = COLOR_BODY,
) -> int:
    """绘制自动换行的文本，返回绘制后的 y 坐标。"""
    if not text:
        return y

    line_height = _font_line_height(font)
    lines = _wrap_lines(draw, text, font, max_width)

    for i, line in enumerate(lines):
        draw.text((x, y + i * line_height), line, font=font, fill=color)
    return y + len(lines) * line_height


# ═══════════════════════════════════════════════════════════
# 绘制辅助
# ═══════════════════════════════════════════════════════════

def _draw_section_header(
    draw: ImageDraw.Draw,
    title: str,
    y: int,
    font: ImageFont.FreeTypeFont,
) -> int:
    """绘制章节标题，返回标题下方的 y 坐标。"""
    lh = _font_line_height(font)
    draw.text((PADDING_H, y), title, font=font, fill=COLOR_TITLE)
    return y + lh + 8


def _draw_card(
    draw: ImageDraw.Draw,
    x: int,
    y: int,
    width: int,
    content_height: int,
    fill: tuple = COLOR_CARD_BG,
) -> None:
    """绘制圆角卡片背景。"""
    draw.rounded_rectangle(
        (x, y, x + width, y + content_height),
        radius=CARD_RADIUS,
        fill=fill,
        outline=COLOR_BORDER,
    )


def _is_placeholder_evidence(text: str) -> bool:
    """判断 evidence 是否为 AI 生成的占位文本（非真实证据）。"""
    if not text:
        return True
    placeholders = [
        "课堂转录中未找到",
        "未找到该知识点",
        "转录中未提及",
        "未找到相关讨论",
    ]
    return any(p in text for p in placeholders)


# ═══════════════════════════════════════════════════════════
# 知识点卡片
# ═══════════════════════════════════════════════════════════

def _draw_kp_item(
    draw: ImageDraw.Draw,
    kp: dict,
    y: int,
    body_font: ImageFont.FreeTypeFont,
    small_font: ImageFont.FreeTypeFont,
) -> int:
    """绘制单个知识点卡片，返回卡片底部的 y 坐标。

    使用 ✓ ✗ ! 等纯 Unicode 符号替代 emoji，确保中文字体正常渲染。
    """
    card_x = PADDING_H + 12
    card_w = WIDTH - PADDING_H * 2 - 24
    inner_x = card_x + 16
    inner_w = card_w - 32

    name = kp.get("name", "")
    covered = kp.get("covered", False)
    understanding = kp.get("student_understanding", "")
    evidence_raw = kp.get("evidence") or ""
    has_real_evidence = not _is_placeholder_evidence(evidence_raw)
    evidence_text = evidence_raw[:200] if has_real_evidence else ""

    body_lh = _font_line_height(body_font)
    small_lh = _font_line_height(small_font)

    # 计算卡片高度
    text_y = y + 14
    name_h = body_lh + 4
    card_h = 14 + name_h + 6   # 名称行
    card_h += small_lh + 4     # 状态行

    # 证据行（使用 _wrap_lines 正确计算行数）
    if has_real_evidence and evidence_text:
        evidence_label = "证据: " + evidence_text
        evidence_lines = _wrap_lines(draw, evidence_label, small_font, inner_w)
        card_h += len(evidence_lines) * small_lh + 6

    card_h += 12  # bottom padding

    # 绘制卡片背景
    _draw_card(draw, card_x, y, card_w, card_h)

    # 知识点名称
    draw.text((inner_x, text_y), name, font=body_font, fill=COLOR_TITLE)
    text_y += name_h + 6

    # 状态行 — 使用 ✓ ✗ ! 替代 emoji
    if covered:
        left_text = "✓ 知识点已覆盖"
        draw.text((inner_x, text_y), left_text, font=small_font, fill=COLOR_GREEN)
        left_w = _measure_text(left_text, small_font)
        sep_x = inner_x + left_w + 8
        draw.text((sep_x, text_y), "|", font=small_font, fill=COLOR_MUTED)

        if understanding == "已掌握":
            right_text = "✓ 学生已掌握"
            right_color = COLOR_GREEN
        elif understanding == "存疑":
            right_text = "⚠ 学生存疑"
            right_color = COLOR_ORANGE
        elif understanding == "未掌握":
            right_text = "✗ 学生未掌握"
            right_color = COLOR_RED
        else:
            right_text = "？学生待确认"
            right_color = COLOR_MUTED
        draw.text((sep_x + 14, text_y), right_text, font=small_font, fill=right_color)
    else:
        draw.text((inner_x, text_y), "✗ 知识点未覆盖", font=small_font, fill=COLOR_MUTED)
    text_y += small_lh + 4

    # 证据（使用换行绘制，防止溢出卡片）
    if has_real_evidence and evidence_text:
        evidence_label = "证据: " + evidence_text
        _draw_wrapped_text(
            draw, evidence_label, small_font, inner_x, text_y,
            inner_w, COLOR_MUTED,
        )

    return y + card_h + 10


def _count_wrapped_lines(
    draw: ImageDraw.Draw,
    text: str,
    font: ImageFont.FreeTypeFont,
    max_width: int,
) -> int:
    """计算文本换行后的行数。"""
    return len(_wrap_lines(draw, text, font, max_width))


# ═══════════════════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════════════════

def generate_report_image(
    session_title: str = "",
    student_name: str = "",
    class_date: str = "",
    knowledge_points: list[dict] | None = None,
    classroom_performance: dict | None = None,
    reinforcement_plan: list[dict] | None = None,
    parent_report: str = "",
) -> bytes:
    """生成课堂分析报告的 PNG 图片。

    Args:
        session_title: 课堂标题。
        student_name: 学生姓名。
        class_date: 上课日期。
        knowledge_points: 知识点覆盖列表。
        classroom_performance: 课堂互动数据。
        reinforcement_plan: 巩固建议列表。
        parent_report: 家长报告文本。

    Returns:
        PNG 图片的 bytes。
    """
    knowledge_points = knowledge_points or []
    reinforcement_plan = reinforcement_plan or []

    # ── 字体 ──
    title_font = _get_font(24, bold=True)
    subtitle_font = _get_font(14)
    section_font = _get_font(18, bold=True)
    body_font = _get_font(15)
    small_font = _get_font(13)
    legend_font = _get_font(12)

    # ── 各行高（基于实际字体度量）──
    section_lh = _font_line_height(section_font)
    body_lh = _font_line_height(body_font)
    small_lh = _font_line_height(small_font)
    legend_lh = _font_line_height(legend_font)

    # 内容区宽度（预计算与实际绘制保持一致）
    content_width = WIDTH - PADDING_H * 2

    # ── 创建临时 draw 用于文本测量 ──
    tmp_img = Image.new("RGB", (1, 1))
    tmp_draw = ImageDraw.Draw(tmp_img)

    # ── 预计算总高度 ──
    total_h = HEADER_HEIGHT + PADDING_V

    # 知识点覆盖
    kp_section_h = 0
    if knowledge_points:
        kp_section_h += section_lh + 8  # 标题
        kp_section_h += legend_lh + 8   # 图例行
        for kp in knowledge_points:
            name = kp.get("name", "")
            evidence_raw = kp.get("evidence") or ""
            has_real = not _is_placeholder_evidence(evidence_raw)
            evidence_text = evidence_raw[:200] if has_real else ""

            # 名称高度
            name_lines = _wrap_lines(tmp_draw, name, body_font, content_width - 56)
            item_h = 14 + len(name_lines) * body_lh + 6

            # 状态行
            item_h += small_lh + 4

            # 证据行
            if has_real and evidence_text:
                ev_lines = _wrap_lines(
                    tmp_draw, "证据: " + evidence_text, small_font, content_width - 56
                )
                item_h += len(ev_lines) * small_lh + 6

            item_h += 12 + 10  # padding + gap
            kp_section_h += item_h
        kp_section_h += SECTION_GAP

    # 课堂互动
    interaction_h = 0
    if classroom_performance:
        interaction_h += section_lh + 8 + body_lh + 8  # 标题 + 一行内容
        key_qs = classroom_performance.get("key_questions") or []
        if key_qs:
            interaction_h += small_lh * len(key_qs)
        interaction_h += 8 + SECTION_GAP

    # 巩固建议
    plan_h = 0
    if reinforcement_plan:
        plan_h += section_lh + 8  # 标题
        plan_h += legend_lh + 8   # 图例行
        for item in reinforcement_plan:
            plan_h += body_lh + 4  # area + priority
            reason = item.get("reason", "")
            if reason:
                reason_lines = _wrap_lines(
                    tmp_draw, reason, small_font, content_width - 40
                )
                plan_h += len(reason_lines) * small_lh + 4
            exercise = item.get("suggested_exercise_type", "")
            if exercise:
                plan_h += small_lh + 2
            plan_h += 10  # item gap
        plan_h += SECTION_GAP

    # 家长报告
    parent_h = 0
    if parent_report:
        parent_h += section_lh + 8  # 标题
        parent_lines = _wrap_lines(
            tmp_draw, parent_report, body_font, content_width - 8
        )
        parent_h += len(parent_lines) * body_lh + 16 + SECTION_GAP

    # 水印/页脚
    footer_h = 40

    total_h += kp_section_h + interaction_h + plan_h + parent_h + footer_h + PADDING_V

    # ── 创建画布 ──
    img = Image.new("RGB", (WIDTH, total_h), COLOR_BG)
    draw = ImageDraw.Draw(img)
    y = 0

    # ── 头部 ──
    draw.rectangle((0, 0, WIDTH, HEADER_HEIGHT), fill=COLOR_HEADER_BG)
    draw.text((PADDING_H, 20), "课堂分析报告", font=title_font, fill=COLOR_HEADER_TEXT)
    date_str = class_date or datetime.now().strftime("%Y年%m月%d日")
    subtitle = (
        f"{session_title}  |  {student_name}  |  {date_str}"
        if student_name
        else f"{session_title}  |  {date_str}"
    )
    draw.text((PADDING_H, 56), subtitle, font=subtitle_font, fill=(255, 255, 255, 200))
    y = HEADER_HEIGHT + PADDING_V

    # ── 知识点覆盖 ──
    if knowledge_points:
        section_bottom = y + kp_section_h - SECTION_GAP
        draw.rounded_rectangle(
            (PADDING_H - 8, y - 8, WIDTH - PADDING_H + 8, section_bottom + 8),
            radius=12, fill=COLOR_SECTION_BG,
        )
        y = _draw_section_header(draw, "知识点覆盖", y, section_font)

        # 图例
        legend_items = [
            ("✓ 已掌握", COLOR_GREEN),
            ("⚠ 存疑", COLOR_ORANGE),
            ("✗ 未掌握", COLOR_RED),
            ("？待确认", COLOR_MUTED),
            ("✗ 未覆盖", COLOR_MUTED),
        ]
        lx = PADDING_H + 4
        for text, color in legend_items:
            draw.text((lx, y), text, font=legend_font, fill=color)
            lx += _measure_text(text, legend_font) + 16
        y += legend_lh + 8

        for kp in knowledge_points:
            y = _draw_kp_item(draw, kp, y, body_font, small_font)

        y += SECTION_GAP - 10

    # ── 课堂互动 ──
    if classroom_performance:
        cp = classroom_performance
        section_bottom = y + interaction_h - SECTION_GAP
        draw.rounded_rectangle(
            (PADDING_H - 8, y - 8, WIDTH - PADDING_H + 8, section_bottom + 8),
            radius=12, fill=COLOR_SECTION_BG,
        )
        y = _draw_section_header(draw, "课堂互动", y, section_font)

        q_count = cp.get("student_questions_count", 0)
        engagement = cp.get("engagement_level", "—")
        ratio = cp.get("teacher_student_ratio", "—")
        summary = f"学生提问：{q_count} 次  |  参与度：{engagement}  |  师生对话比：{ratio}"
        draw.text((PADDING_H + 4, y), summary, font=body_font, fill=COLOR_BODY)
        y += body_lh + 8

        key_qs = cp.get("key_questions") or []
        if key_qs:
            draw.text((PADDING_H + 4, y), "关键问题：", font=small_font, fill=COLOR_MUTED)
            y += small_lh
            for q in key_qs:
                draw.text((PADDING_H + 4, y), f"* {q}", font=small_font, fill=COLOR_BODY)
                y += small_lh
        y += SECTION_GAP

    # ── 巩固建议 ──
    if reinforcement_plan:
        section_bottom = y + plan_h - SECTION_GAP
        draw.rounded_rectangle(
            (PADDING_H - 8, y - 8, WIDTH - PADDING_H + 8, section_bottom + 8),
            radius=12, fill=COLOR_SECTION_BG,
        )
        y = _draw_section_header(draw, "巩固建议", y, section_font)

        # 优先级图例 — 使用 ● 替代 emoji 圆点
        legend_items = [
            ("● 高优先级", "需要立即重点巩固", COLOR_RED),
            ("● 中优先级", "建议近期加强练习", COLOR_ORANGE),
            ("● 低优先级", "适当关注即可", COLOR_GREEN),
        ]
        lx = PADDING_H + 4
        for icon_text, desc, color in legend_items:
            draw.text((lx, y), f"{icon_text}：{desc}", font=legend_font, fill=color)
            lx += _measure_text(f"{icon_text}：{desc}", legend_font) + 20
        y += legend_lh + 8

        for item in reinforcement_plan:
            area = item.get("area", "")
            priority = item.get("priority", "中")
            reason = item.get("reason", "")
            exercise = item.get("suggested_exercise_type", "")

            # 优先级颜色
            if priority == "高":
                p_color = COLOR_RED
            elif priority == "中":
                p_color = COLOR_ORANGE
            else:
                p_color = COLOR_GREEN

            # 建议项标题 — ● 颜色表示优先级
            item_x = PADDING_H + 4
            draw.text((item_x, y), f"● {area}", font=body_font, fill=p_color)
            y += body_lh + 4

            if reason:
                y = _draw_wrapped_text(
                    draw, reason, small_font, item_x + 16, y,
                    content_width - 56, COLOR_MUTED,
                )
                y += 4

            if exercise:
                draw.text(
                    (item_x + 16, y),
                    f"建议练习: {exercise}",
                    font=small_font, fill=COLOR_BLUE,
                )
                y += small_lh + 2

            y += 10  # item gap
        y += SECTION_GAP - 10

    # ── 家长报告 ──
    if parent_report:
        section_bottom = y + parent_h - SECTION_GAP
        draw.rounded_rectangle(
            (PADDING_H - 8, y - 8, WIDTH - PADDING_H + 8, section_bottom + 8),
            radius=12, fill=COLOR_SECTION_BG,
        )
        y = _draw_section_header(draw, "家长反馈报告", y, section_font)
        # 预计算与绘制使用一致的 max_width
        y = _draw_wrapped_text(
            draw, parent_report, body_font, PADDING_H + 4, y,
            content_width - 8, COLOR_BODY,
        )
        y += SECTION_GAP

    # ── 页脚 ──
    footer_y = total_h - footer_h
    draw.line((PADDING_H, footer_y, WIDTH - PADDING_H, footer_y), fill=COLOR_DIVIDER, width=1)
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    footer_text = f"由 教师助手 生成  |  {generated_at}"
    fw = _measure_text(footer_text, legend_font)
    draw.text(((WIDTH - fw) // 2, footer_y + 12), footer_text, font=legend_font, fill=COLOR_MUTED)

    # ── 导出为 PNG bytes ──
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()
