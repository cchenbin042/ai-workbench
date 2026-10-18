"""Exercise the task workspace review prototype using local deterministic data."""
from pathlib import Path
from playwright.sync_api import sync_playwright, expect
import json

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'output/playwright'
OUT.mkdir(parents=True, exist_ok=True)
BROWSER = 'C:/Users/cb_lo/AppData/Local/ms-playwright/chromium-1208/chrome-win64/chrome.exe'
checks, errors, external = [], [], []

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, executable_path=BROWSER)
    context = browser.new_context(viewport={'width':1536,'height':1000}, reduced_motion='reduce')
    page = context.new_page()
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.on('request', lambda r: external.append(r.url) if not r.url.startswith('http://127.0.0.1:8765') and not r.url.startswith('blob:') else None)
    page.goto('http://127.0.0.1:8765/?view=task-workbench', wait_until='networkidle')
    expect(page.locator('.task-workspace h1')).to_contain_text('工具调用')
    expect(page.locator('.artifact-document')).to_contain_text('模型与运行时')
    page.screenshot(path=str(OUT / 'task-design-artifact.png'), full_page=True)
    checks.append('Task workspace combines the shared shell, conversation and editable artifact inspector')

    page.locator('#task-tab-steps').click()
    expect(page.locator('.execution-step.done')).to_have_count(4)
    page.screenshot(path=str(OUT / 'task-design-steps.png'), full_page=True)
    page.locator('#task-tab-sources').click()
    page.locator('.source-file').first.click()
    expect(page.locator('.source-preview pre')).to_contain_text('def execute_tool')
    page.screenshot(path=str(OUT / 'task-design-sources.png'), full_page=True)
    checks.append('Execution steps and source previews can be opened without accessing project files')

    page.locator('#task-tab-artifacts').click()
    page.locator('[data-action="task-artifact-mode"][data-value="edit"]').click()
    changed = '# 自己整理的工具调用笔记\n\n先解释分工，再验证失败处理。\n<script>window.unsafe = true</script>'
    page.locator('#task-artifact-editor').fill(changed)
    page.locator('#task-tab-sources').click()
    page.locator('#task-tab-artifacts').click()
    expect(page.locator('#task-artifact-editor')).to_have_value(changed)
    page.locator('[data-action="task-artifact-save"]').click()
    expect(page.locator('.artifact-document')).to_contain_text('自己整理')
    assert page.evaluate('window.unsafe === undefined')
    expect(page.locator('.task-state')).to_contain_text('已保存')
    page.reload(wait_until='networkidle')
    expect(page.locator('.artifact-document')).to_contain_text('自己整理')
    checks.append('Edited artifact survives inspector changes and reload; HTML is displayed as text')

    page.locator('#task-reply').fill('增加一个关于参数校验的练习。')
    page.locator('[data-action="task-reply-send"]').click()
    expect(page.locator('.conversation-scroll')).to_contain_text('增加一个关于参数校验')
    expect(page.locator('.artifact-document')).to_contain_text('自己整理')
    page.locator('[data-action="task-toggle-rail"]').click()
    expect(page.locator('.task-inspector')).not_to_be_visible()
    page.locator('[data-action="task-toggle-rail"]').click()
    expect(page.locator('.task-inspector')).to_be_visible()
    checks.append('Continued conversation preserves edited artifacts and inspector can collapse')

    page.locator('.wb-nav [data-page="home"]').click()
    page.locator('#task-prompt').fill('整理 Agent 面试问题')
    page.locator('[data-action="submit-task"]').click()
    page.locator('[data-action="task-run"]').click()
    page.locator('[data-action="task-cancel"]').click()
    page.wait_for_timeout(3600)
    expect(page.locator('.task-state')).to_contain_text('已取消')
    expect(page.locator('.artifact-document')).to_have_count(0)
    checks.append('Cancelled execution does not create a late result')

    page.locator('[data-action="task-run"]').click()
    page.locator('[data-action="task-fail"]').click()
    expect(page.locator('.execution-step.failed')).to_have_count(1)
    page.screenshot(path=str(OUT / 'task-design-error.png'), full_page=True)
    page.locator('[data-action="task-run"]').click()
    expect(page.locator('.artifact-document')).to_be_visible(timeout=6000)
    checks.append('Simulated failure keeps progress and retry reaches artifact review')

    page.locator('.wb-nav [data-page="home"]').click()
    page.locator('[data-action="setup-interview"]').first.click()
    page.locator('[data-action="start-interview"]').click()
    page.locator('#answer').fill('模型提出工具调用请求，程序负责参数校验和实际执行。')
    page.locator('[data-action="submit-answer"]').click()
    expect(page.locator('.interview-ledger')).to_contain_text('程序负责参数校验')
    expect(page.locator('.question-eyebrow')).to_contain_text('FOLLOW-UP')
    page.screenshot(path=str(OUT / 'task-design-interview.png'), full_page=True)
    checks.append('Interview retains submitted answers beside the active follow-up')

    page.get_by_role('button', name='设置', exact=True).click()
    page.locator('[data-action="settings-tab"][data-value="models"]').first.click()
    expect(page.locator('#model-key')).to_be_disabled()
    page.locator('[data-action="demo-model-fail"]').click()
    expect(page.locator('.connection-result.error')).to_contain_text('模拟密钥无效')
    page.screenshot(path=str(OUT / 'task-design-model-error.png'), full_page=True)
    page.locator('[data-action="demo-model-test"]').click()
    expect(page.locator('.connection-result.success')).to_contain_text('未联网')
    page.screenshot(path=str(OUT / 'task-design-models.png'), full_page=True)
    page.locator('[data-action="settings-tab"][data-value="tools"]').first.click()
    page.locator('[data-action="demo-mcp"]').click()
    page.locator('[data-action="settings-tab"][data-value="models"]').first.click()
    expect(page.locator('.connection-overview')).to_contain_text('已连接 · 演示')
    checks.append('Model settings separate text, speech and tools; success and failure remain explicitly simulated')

    page.locator('[data-page="tasks"]').first.click()
    expect(page.locator('.history-list [data-action="open-demo-task"]')).to_have_count(2)
    page.locator('[data-action="task-history-filter"][data-value="completed"]').click()
    expect(page.locator('.history-list [data-action="open-demo-task"]')).to_have_count(1)
    page.screenshot(path=str(OUT / 'task-design-history.png'), full_page=True)
    page.locator('[data-action="task-history-filter"][data-value="active"]').click()
    expect(page.locator('.history-list [data-action="open-demo-task"]')).to_have_count(1)
    page.locator('.history-list [data-action="open-demo-task"]').click()
    expect(page.locator('.artifact-document')).to_be_visible()
    checks.append('Task history filters saved and waiting tasks, and opens the saved task state')

    page.locator('.wb-nav [data-page="home"]').click()
    page.locator('#task-prompt').fill('检查中断后继续的流程')
    page.locator('[data-action="submit-task"]').click()
    page.locator('[data-action="task-run"]').click()
    page.reload(wait_until='networkidle')
    page.locator('[data-action="open-demo-task"]').first.click()
    expect(page.locator('.task-state')).to_contain_text('已中断')
    expect(page.locator('.artifact-document')).to_have_count(0)
    page.locator('[data-action="task-run"]').click()
    expect(page.locator('.artifact-document')).to_be_visible(timeout=6000)
    checks.append('Reload interrupts active work; resuming requires an explicit action and retains progress')

    for width in [1536,1280,1024,768,390]:
        page.set_viewport_size({'width':width,'height':1000})
        page.goto('http://127.0.0.1:8765/?view=task-workbench', wait_until='networkidle')
        expect(page.locator('.task-workspace')).to_be_visible()
        assert page.evaluate('document.documentElement.scrollWidth') <= width, width
        assert not page.evaluate('document.getElementById("main-content").scrollWidth > document.getElementById("main-content").clientWidth + 1'), width
        expect(page.locator('[data-action="task-artifact-save"]')).to_be_visible()
        page.screenshot(path=str(OUT / f'task-design-{width}.png'), full_page=True)
        page.get_by_role('button', name='设置', exact=True).click()
        page.locator('[data-action="settings-tab"][data-value="models"]').first.click()
        assert page.evaluate('document.documentElement.scrollWidth') <= width, (width,'models')
        assert not page.evaluate('document.getElementById("main-content").scrollWidth > document.getElementById("main-content").clientWidth + 1'), (width,'models')
        expect(page.locator('[data-action="demo-model-test"]')).to_be_visible()
        if width in [1536,390]:
            page.screenshot(path=str(OUT / f'task-design-models-{width}.png'), full_page=True)
    checks.append('Task workspace fits desktop, tablet and mobile widths without horizontal overflow')

    assert not errors, errors
    assert not external, external
    result = {'passed':True,'checks':checks,'page_errors':errors,'external_requests':external}
    (OUT / 'task-design-verification.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))
    browser.close()
