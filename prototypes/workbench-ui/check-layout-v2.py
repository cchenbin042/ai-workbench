"""Validate the reference-inspired shared shell and three task modules."""
from pathlib import Path
from playwright.sync_api import sync_playwright, expect
import json

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'output/playwright'
OUT.mkdir(parents=True,exist_ok=True)
BROWSER='C:/Users/cb_lo/AppData/Local/ms-playwright/chromium-1208/chrome-win64/chrome.exe'
checks=[]
errors=[]
external=[]

with sync_playwright() as p:
    browser=p.chromium.launch(headless=True,executable_path=BROWSER)
    context=browser.new_context(viewport={'width':1536,'height':1000},reduced_motion='reduce')
    page=context.new_page()
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.on('request',lambda r:external.append(r.url) if not r.url.startswith('http://127.0.0.1:8765') and not r.url.startswith('blob:') else None)
    page.goto('http://127.0.0.1:8765',wait_until='networkidle')
    expect(page.locator('.workspace-switch')).to_have_count(0)
    expect(page.locator('.breadcrumb')).not_to_contain_text('个人成长工作区')
    expect(page.locator('.scene-tab')).to_have_count(3)
    expect(page.locator('.context-picker').first).to_contain_text('选择工作空间')
    baseline=page.locator('.wb-nav').inner_text()
    checks.append('Workspace selector removed from shell header and placed below task input')

    for scene,term in [('office','面试题库'),('develop','代码讲解'),('design','界面草图')]:
        page.locator('[data-action="switch-scene"][data-value="'+scene+'"]').click()
        expect(page.locator('.task-shortcuts')).to_contain_text(term)
        assert page.locator('.wb-nav').inner_text()==baseline
        assert page.locator('.suggestion-card').count()==4
        page.screenshot(path=str(OUT/('layout-v2-'+scene+'.png')),full_page=True)
    checks.append('Office, development and design change central content while global navigation remains identical')

    page.locator('[data-action="switch-scene"][data-value="develop"]').click()
    page.locator('.task-shortcuts [data-action="task-template"]').first.click()
    expect(page.locator('#task-prompt')).to_have_value('项目理解')
    page.locator('#task-prompt').fill('帮我理清 Agent 项目的工具调用流程')
    page.locator('[data-action="switch-scene"][data-value="design"]').click()
    expect(page.locator('#task-prompt')).to_have_value('帮我理清 Agent 项目的工具调用流程')
    page.locator('.composer-context [data-action="workspace-picker"]').click()
    page.locator('[data-action="choose-workspace"][data-value="tiangong_agent"]').click()
    expect(page.locator('.composer-context')).to_contain_text('tiangong_agent')
    expect(page.locator('#task-prompt')).to_have_value('帮我理清 Agent 项目的工具调用流程')
    page.locator('[data-action="add-context"]').click()
    page.locator('[data-action="attach-demo"][data-value="worker_tools.py"]').click()
    expect(page.locator('.composer-attachments')).to_contain_text('worker_tools.py')
    page.locator('[data-action="access-picker"]').click()
    page.locator('[data-action="choose-access"][data-value="confirm-write"]').click()
    expect(page.locator('.composer-context')).to_contain_text('修改前确认')
    checks.append('Task draft survives module changes, context attachment, workspace and access selection')

    page.locator('[data-action="submit-task"]').click()
    expect(page.locator('.task-message p').first).to_have_text('帮我理清 Agent 项目的工具调用流程')
    expect(page.locator('.task-metadata')).to_contain_text('tiangong_agent')
    assert page.locator('.wb-nav').inner_text()==baseline
    page.screenshot(path=str(OUT/'layout-v2-task-preview.png'),full_page=True)
    page.locator('[data-action="open-demo-task"]').first.click()
    expect(page.locator('.task-message p').first).to_have_text('帮我理清 Agent 项目的工具调用流程')
    checks.append('Submitting a task opens a structured demo session and adds a task-history entry')

    for target in ['assistant','agents','automations','workspace','more']:
        page.locator('.wb-nav [data-page="'+target+'"]').click()
        assert page.locator('.wb-nav').inner_text()==baseline
        assert page.locator('h1').count()==1
    page.locator('[data-page="bank"]').first.click()
    expect(page.locator('h1')).to_contain_text('题库')
    checks.append('Shared sidebar opens assistant, tools, schedules, library and app directory without replacing navigation')

    for width in [1536,1280,1024,768,390]:
        page.set_viewport_size({'width':width,'height':950})
        page.locator('.wb-nav [data-page="home"]').click()
        for scene in ['office','develop','design']:
            page.locator('[data-action="switch-scene"][data-value="'+scene+'"]').click()
            assert page.evaluate('document.documentElement.scrollWidth')<=width
            overflow=page.evaluate('document.getElementById("main-content").scrollWidth > document.getElementById("main-content").clientWidth+1')
            assert not overflow,(width,scene,'main content overflows horizontally')
            expect(page.locator('.composer-context')).to_be_visible()
        page.screenshot(path=str(OUT/('layout-v2-'+str(width)+'.png')),full_page=True)
    checks.append('All three modules fit at 1536, 1280, 1024, 768 and 390px without horizontal overflow')
    assert not errors,errors
    assert not external,external
    result={'passed':True,'checks':checks,'page_errors':errors,'external_requests':external}
    (OUT/'layout-v2-verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))
    browser.close()
