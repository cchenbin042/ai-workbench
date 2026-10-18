"""Check the design handoff from materials through reflection and recall."""
from pathlib import Path
from playwright.sync_api import sync_playwright, expect
import json

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'output/playwright'
BROWSER = 'C:/Users/cb_lo/AppData/Local/ms-playwright/chromium-1208/chrome-win64/chrome.exe'
URL = 'http://127.0.0.1:8765'
checks, errors, external = [], [], []

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, executable_path=BROWSER)
    page = browser.new_page(viewport={'width':1536, 'height':1000}, reduced_motion='reduce')
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.on('request', lambda r: external.append(r.url) if not r.url.startswith(URL) and not r.url.startswith('blob:') else None)
    page.goto(URL + '/?view=workspace', wait_until='networkidle')
    expect(page.locator('.material-library')).to_be_visible()
    page.locator('[data-action="material-open"][data-id="m-tools"]').click()
    expect(page.locator('.material-preview')).to_contain_text('worker_tools.py')
    page.screenshot(path=str(OUT / 'learning-materials.png'), full_page=True)
    checks.append('Library shows a selected source and its explicit sample provenance')

    page.locator('[data-action="material-add"]').click()
    page.locator('#material-title').fill('工具调用课堂笔记')
    page.locator('#material-text').fill('模型提出工具名称与参数。执行器验证输入并记录幂等标识。')
    page.locator('[data-action="material-save"]').click()
    expect(page.locator('.material-preview')).to_contain_text('幂等标识')
    page.reload(wait_until='networkidle')
    expect(page.locator('.material-library')).to_contain_text('工具调用课堂笔记')
    page.locator('.material-row').filter(has_text='工具调用课堂笔记').locator('[data-action="material-open"]').click()
    expect(page.locator('.material-preview')).to_contain_text('幂等标识')
    checks.append('Pasted notes remain local and survive reopening the library')

    page.locator('[data-action="materials-build"]').click()
    expect(page.locator('.build-material-summary')).to_contain_text('工具调用课堂笔记')
    checks.append('Selected materials appear in the question-builder scope')

    page.goto(URL + '/?view=report-example', wait_until='networkidle')
    expect(page.locator('.reflection-report')).to_be_visible()
    expect(page.locator('.report-answer-comparison').first).to_contain_text('你的原回答')
    page.locator('[data-action="report-notes"]').fill('下次先说明超时后是否真的执行成功，再说幂等。')
    page.locator('[data-action="save-report-note"]').click()
    page.locator('[data-action="report-review"]').click()
    page.screenshot(path=str(OUT / 'learning-report.png'), full_page=True)
    checks.append('Report links original answers, reference points and an editable reflection')

    page.reload(wait_until='networkidle')
    expect(page.locator('[data-action="report-notes"]')).to_have_value('下次先说明超时后是否真的执行成功，再说幂等。')
    page.locator('[data-action="nav"][data-page="reports"]').first.click()
    page.locator('[data-action="open-report"]').first.click()
    expect(page.locator('.reflection-report')).to_be_visible()
    checks.append('Saved report snapshots and reflection notes reopen independently of a new interview')

    page.locator('[data-action="nav"][data-page="review"]').first.click()
    expect(page.locator('.review-card')).to_have_count(1)
    page.locator('[data-action="start-recall"]').first.click()
    expect(page.locator('.recall-workbench')).to_be_visible()
    expect(page.locator('.recall-reference')).to_have_count(0)
    page.locator('#recall-answer').fill('先查状态，再通过幂等键避免重复副作用。')
    page.locator('[data-action="reveal-recall"]').click()
    expect(page.locator('.recall-reference')).to_be_visible()
    page.screenshot(path=str(OUT / 'learning-recall.png'), full_page=True)
    page.locator('[data-action="recall-rate"][data-value="recalled"]').click()
    expect(page.locator('.recall-result')).to_contain_text('借助参考完成')
    checks.append('Recall hides reference until requested and records assistance honestly')

    page.locator('[data-action="nav"][data-page="review"]').first.click()
    expect(page.locator('.review-card')).to_contain_text('借助参考完成')
    page.locator('[data-action="start-recall"]').first.click()
    expect(page.locator('#recall-answer')).to_have_value('')
    page.locator('#recall-answer').fill('先检查执行记录，使用唯一业务键和状态查询，避免盲目重试。')
    page.locator('[data-action="recall-rate"][data-value="recalled"]').click()
    expect(page.locator('.recall-result')).to_contain_text('独立回忆')
    page.reload(wait_until='networkidle')
    page.goto(URL + '/?view=review', wait_until='networkidle')
    expect(page.locator('.review-card')).to_contain_text('独立回忆')
    expect(page.locator('.review-card')).to_have_count(1)
    checks.append('Self review persists without silently removing a question as mastered')

    page.goto(URL + '/?view=bank', wait_until='networkidle')
    page.locator('#bank-topic').select_option('RAG')
    expect(page.locator('tbody tr')).to_have_count(1)
    page.locator('#bank-search').fill('不存在的关键词')
    expect(page.locator('.bank-empty-detail')).to_contain_text('没有匹配')
    page.locator('#bank-search').fill('')
    page.locator('[data-action="select-bank-all"]').check()
    page.locator('[data-action="selected-interview"]').click()
    expect(page.locator('#interview-count')).to_have_value('1')
    checks.append('Bank filters and empty detail agree; a single selected question creates one-question practice')

    page.goto(URL + '/?view=task-workbench', wait_until='networkidle')
    page.locator('[data-action="task-artifact-mode"][data-value="edit"]').click()
    page.locator('#task-artifact-editor').fill('本轮成果：只读工具要做路径和参数校验。')
    page.locator('[data-action="artifact-to-build"]').click()
    expect(page.locator('.build-material-summary')).to_contain_text('成果快照')
    expect(page.locator('#build-extra')).to_contain_text('继续整理任务成果')
    checks.append('Artifact handoff keeps a source snapshot without treating arbitrary Markdown as parsed questions')

    page.goto(URL + '/?view=agents', wait_until='networkidle')
    page.locator('[data-action="new-agent"]').click()
    page.locator('#agent-name').fill('边界与取舍教练')
    page.locator('#agent-prompt').fill('先问执行边界，再问验证方法。')
    page.locator('[name="agent-tool"][value="save_question_drafts"]').uncheck()
    page.locator('[data-action="save-agent"]').click()
    card=page.locator('.agent-list .panel').filter(has_text='边界与取舍教练')
    card.locator('[data-action="agent-detail"]').click()
    expect(page.locator('[name="agent-tool"][value="save_question_drafts"]')).not_to_be_checked()
    page.locator('#agent-prompt').fill('先问边界，然后要求举一个验证例子。')
    page.locator('[data-action="save-agent"]').click()
    page.reload(wait_until='networkidle')
    expect(page.locator('.agent-list')).to_contain_text('要求举一个验证例子')
    checks.append('Agent prompt and selected tool scope remain editable and persist locally')

    page.goto(URL + '/?view=settings', wait_until='networkidle')
    page.locator('[data-action="settings-tab"][data-value="tools"]').click()
    expect(page.locator('[data-action="mcp-preview-call"]').first).to_be_disabled()
    page.locator('[data-action="demo-mcp"]').click()
    expect(page.locator('[data-action="mcp-preview-call"][data-value="timeout"]')).to_be_enabled(timeout=3000)
    page.locator('[data-action="mcp-tool-toggle"][data-value="read_file"]').click()
    expect(page.locator('[data-action="mcp-tool-toggle"][data-value="read_file"]')).to_have_attribute('aria-checked','false')
    page.locator('[data-action="mcp-preview-call"][data-value="timeout"]').click()
    expect(page.locator('.mcp-call-result')).to_contain_text('超时')
    page.screenshot(path=str(OUT / 'learning-mcp.png'), full_page=True)
    checks.append('MCP design separates service connection, per-tool switches and simulated timeout state')

    for width in [1536,1280,1024,768,390]:
        page.set_viewport_size({'width':width, 'height':1000})
        for view in ['workspace','bank','report-example','review','agents','settings']:
            page.goto(URL + '/?view=' + view, wait_until='networkidle')
            assert page.evaluate('document.documentElement.scrollWidth') <= width, (width,view)
            assert not page.evaluate('document.getElementById("main-content").scrollWidth > document.getElementById("main-content").clientWidth + 1'), (width,view,'inner overflow')
        if width in [1536,390]:
            page.goto(URL + '/?view=report-example', wait_until='networkidle')
            page.screenshot(path=str(OUT / f'learning-report-{width}.png'), full_page=True)
            page.goto(URL + '/?view=workspace', wait_until='networkidle')
            page.screenshot(path=str(OUT / f'learning-materials-{width}.png'), full_page=True)
    checks.append('Materials, question library, report and review fit five viewport widths')
    assert not errors, errors
    assert not external, external
    result = {'passed':True,'checks':checks,'page_errors':errors,'external_requests':external}
    (OUT / 'learning-design-verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))
    browser.close()
