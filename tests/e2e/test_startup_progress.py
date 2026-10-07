import pytest

from helpers import wait_app_ready

pytestmark = pytest.mark.e2e

# #progress の表示内容（hidden のときは空文字）の変化を、起動前から記録する
RECORDER = """
(() => {
  window.__progressLog = [];
  const record = () => {
    const el = document.getElementById('progress');
    if (!el) return;
    const text = el.hidden ? '' : el.textContent.trim();
    const log = window.__progressLog;
    if (log[log.length - 1] !== text) log.push(text);
  };
  new MutationObserver(record).observe(document, {subtree: true, childList: true, characterData: true, attributes: true, attributeFilter: ['hidden']});
  document.addEventListener('DOMContentLoaded', record);
})();
"""


def test_startup_progress_stages_in_order(page, app_url):
    page.add_init_script(RECORDER)
    page.goto(app_url)
    wait_app_ready(page)
    page.wait_for_function("document.documentElement.dataset.startupStage === 'ready'")
    # フォント取得の表示などが後続しても、起動段階の順序だけを見る
    log = page.evaluate("window.__progressLog")
    print("progress log:", log)

    def is_startup(text):
        return "Python 実行環境" in text or text.startswith("ライブラリを")

    runtime = next(i for i, t in enumerate(log) if "Python 実行環境" in t)
    packages = next(i for i, t in enumerate(log) if t.startswith("ライブラリを読み込み中"))
    assert runtime < packages, log
    # 起動中の表示の後に、起動表示ではないもの（非表示、または続くフォント取得の表示）へ遷移する＝準備完了
    last_startup = max(i for i, t in enumerate(log) if is_startup(t))
    assert last_startup < len(log) - 1 or not log[-1], log
    assert page.locator("#progress").get_attribute("aria-live") == "polite"
