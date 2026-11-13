"""Generate the buildless GitHub Pages demo in docs/."""

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = "https://github.com/SavDen/CheckStock"


def artifacts():
    html = (ROOT / "app/templates/index.html").read_text()
    html = html.replace('href="/static/', 'href="./static/').replace('src="/static/', 'src="./static/')
    html = html.replace(
        '<script defer src="./static/app.js"></script>',
        '<script defer src="./static/demo-store.js"></script><script defer src="./static/app.js"></script>',
    )
    html = html.replace('href="/docs"', f'href="{REPO}#readme"').replace(
        "Документация API", "Код и инструкция"
    )
    html = (
        html.replace("Локальный демомагазин", "Демонстрационные данные в браузере")
        .replace("Изменения сохраняются в базе данных", "Изменения сохраняются в этом браузере")
        .replace("Загружаем остатки из PostgreSQL…", "Загружаем демонстрационные остатки…")
    )
    notice = f'''<section class="demo-notice" aria-label="Демонстрационный режим"><div><strong>Демоверсия · данные в вашем браузере</strong><p>Можно проводить операции и обновлять страницу. Серверная версия с PostgreSQL запускается по инструкции в репозитории.</p></div><div class="demo-actions"><a class="button small secondary" href="{REPO}/raw/refs/heads/main/docs/demo/checkstock-demo.mp4">Скачать видео</a><button class="button small secondary" id="reset-demo">Сбросить демо</button></div></section>'''
    html = html.replace('<main id="main">', '<main id="main">' + notice)
    reset = """<dialog id="demo-reset-dialog" aria-labelledby="reset-title"><form method="dialog"><div class="dialog-head"><div><h2 id="reset-title">Начать демо заново?</h2><p>Вернутся исходные 25 единиц товара. Ваши демонстрационные операции в этом браузере будут удалены.</p></div></div><div class="dialog-footer"><button class="button secondary" value="cancel" autofocus>Отмена</button><button class="button primary" value="reset">Сбросить демо</button></div></form></dialog>"""
    html = html.replace("</body>", reset + "\n</body>")
    yield ROOT / "docs/index.html", html.encode()
    yield ROOT / "docs/.nojekyll", b""
    for p in sorted((ROOT / "app/static").rglob("*")):
        if not p.is_file():
            continue
        content = p.read_bytes()
        if p.name == "style.css":
            css = content.decode().replace("url('/static/fonts/Onest.ttf')", "url('./fonts/Onest.ttf')")
            css += "\n.demo-notice{display:flex;justify-content:space-between;align-items:center;gap:20px;padding:17px 20px;margin-bottom:28px;background:#edf1e4;border-radius:10px;color:#435d3a}.demo-notice strong{font-size:12px;font-weight:600}.demo-notice p{font-size:11px;margin:6px 0 0;max-width:72ch}.demo-actions{display:flex;gap:8px;flex-shrink:0}@media(max-width:1100px){.demo-notice{align-items:flex-start;flex-direction:column;gap:12px}}@media(max-width:420px){.demo-notice{padding:16px}.demo-actions{flex-wrap:wrap}}\n"
            content = css.encode()
        yield ROOT / "docs/static" / p.relative_to(ROOT / "app/static"), content


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    stale = []
    for path, content in artifacts():
        if args.check:
            if not path.exists() or path.read_bytes() != content:
                stale.append(str(path.relative_to(ROOT)))
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
    if stale:
        raise SystemExit("Rebuild Pages files: " + ", ".join(stale))
    print("Pages assets are current" if args.check else "GitHub Pages demo generated in docs/")


if __name__ == "__main__":
    main()
