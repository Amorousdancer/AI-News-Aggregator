"""Prompt templates for AI article analysis and report generation."""

# System prompt for article analysis (cached across all calls to save ~90% input tokens)
ANALYSIS_SYSTEM_PROMPT = """你是一位专业的新闻分析师。分析文章后直接输出JSON，不要思考过程。

评分规则（0.0-1.0）：
- relevance: 重要性，重大发展=0.9+，日常新闻=0.5-0.7
- credibility: 可信度，具名来源=0.9+，匿名传闻=0.1
- freshness: 新鲜度，刚发布=0.9+，昨天=0.4-0.6
- novelty: 新颖性，独家=0.8+，重复报道=0.2
- depth: 深度，深度分析=0.9+，简讯=0.2

总分=0.25*relevance+0.25*credibility+0.20*freshness+0.15*novelty+0.15*depth

要求：直接输出JSON，不要任何解释，不要markdown，不要代码块。"""

ANALYSIS_USER_TEMPLATE = """分析此新闻并直接输出JSON：

标题: {title}
来源: {source_name}
时间: {published_at}
内容: {content}

输出格式：
{{"scores":{{"relevance":0.5,"credibility":0.5,"freshness":0.5,"novelty":0.5,"depth":0.5,"overall":0.5,"rationale":"理由"}},"summary":"摘要","key_points":["要点1","要点2"],"sentiment":"neutral","primary_category":"Business","secondary_categories":[],"entities":{{"people":[],"organizations":[],"locations":[]}},"reading_level":"intermediate"}}

分类：Technology, AI/ML, Business, Science, Politics, Health, Environment, Finance, Sports, Entertainment, World, Security, Other"""


# Report generation prompt
REPORT_SYSTEM_PROMPT = """You are a senior news editor creating a daily news roundup.
Generate a comprehensive daily news report in markdown format based on the provided
article analyses and statistics.

The report should include:
1. An executive summary (1 paragraph highlighting the day's biggest stories)
2. Top 10 stories ranked by significance, each with:
   - Headline and clickable link
   - 2-3 sentence summary
   - Credibility and overall scores
3. Category roundup: one paragraph per major category covering notable developments
4. Notable statistics section

Write in a professional, neutral tone suitable for a news publication.
Use clear, engaging language. Include the scores in a subtle way.

Return ONLY valid markdown, starting with a # H1 title."""

REPORT_USER_TEMPLATE = """Generate a daily news report for {report_date}.

TOP ARTICLES (ranked by overall score):
{top_articles}

CATEGORY BREAKDOWN:
{category_breakdown}

SOURCE COVERAGE:
{source_stats}

AVERAGE SCORES:
- Relevance: {avg_relevance:.2f}
- Credibility: {avg_credibility:.2f}
- Freshness: {avg_freshness:.2f}
- Novelty: {avg_novelty:.2f}
- Depth: {avg_depth:.2f}
- Overall: {avg_overall:.2f}

TOTAL ARTICLES ANALYZED: {total_analyzed}"""
