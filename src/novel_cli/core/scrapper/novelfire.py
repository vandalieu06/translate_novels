import re
from dataclasses import dataclass
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

from novel_cli.core.models.models import NovelChapterModel


@dataclass
class Selectores:
    """Classe de selectores de novelfire y similares"""

    # Portadas
    title: str = '.novel-info .main-head .novel-title'
    img_cover: str = '.header-body .fixed-img .cover img'
    url_chapters: str = '.novel-body #info .content-nav .chapter-latest-container'

    # Botones de paginas de capitulos
    filter: str = '#chpagedlist'
    filter_btn_next: str = '.page-item > .page-link[rel="next"]'

    # Lista links de capitulos
    chapters: str = '.novel-body.container #chpagedlist'
    chapters_list: str = '.chapter-list > li > a'

    # Capitulos
    chapter_title: str = '.chapter-title'
    chapter_body_paragraphs: str = '#chapter-container > #content'
    chapter_paragraphs: str = '#chapter-container > #content > p'


@dataclass
class PortadaData:
    title: str | None
    img_cover: str | None
    url_chapter: str | None


class ScrapperNovelFire:
    """Classe para extraer portada y capitulos de novela novelfire"""

    novel_url: str
    base_dir: str = 'output'

    def __init__(self, novel_url):
        self.novel_url = novel_url

    def get_portada(self) -> PortadaData:
        with sync_playwright() as p:
            browser = p.firefox.launch(headless=True)
            page = browser.new_page()
            page.goto(self.novel_url, wait_until='networkidle')

            # Paso 1 - Obtener titulo
            s_title = page.wait_for_selector(Selectores.title)
            if not s_title:
                raise Exception()

            title = s_title.text_content()

            # Paso 2 - Obtener imagen
            s_cover = page.wait_for_selector(Selectores.img_cover)
            if not s_cover:
                raise Exception()

            cover = s_cover.get_attribute('src')

            # Paso 3 - Obtener url de listado capitulos
            s_url_chapters = page.wait_for_selector(Selectores.url_chapters)
            if not s_url_chapters:
                raise Exception()

            url_chapters = s_url_chapters.get_attribute('href')

            page.close

        return PortadaData(
            title=title,
            img_cover=cover,
            url_chapter=url_chapters,
        )

    def get_chapters_pages(self, page_chapter: str) -> list:
        urls: list[str] = []
        selector_filter = Selectores.filter
        selector_btn_next = Selectores.filter_btn_next

        with sync_playwright() as p:
            browser = p.firefox.launch(headless=True)
            page = browser.new_page()
            page.goto(page_chapter, wait_until='networkidle')
            while True:
                current_url = page.url
                if current_url not in urls:
                    urls.append(current_url)

                container_filter = page.wait_for_selector(selector_filter)

                if not container_filter:
                    break

                btn_next_url = container_filter.query_selector(selector_btn_next)

                if not btn_next_url:
                    break

                is_disabled = page.eval_on_selector(
                    f'{selector_filter} {selector_btn_next}',
                    "el => el.closest('li').classList.contains('disabled')",
                )

                if is_disabled:
                    break

                btn_next_url.click()
                page.wait_for_load_state('networkidle')

            page.close
        return urls

    def get_chapters_links(self, url: str) -> list:
        with sync_playwright() as p:
            browser = p.firefox.launch(headless=True)
            page = browser.new_page()
            page.goto(url, wait_until='networkidle')

            container_list_chapters = page.wait_for_selector(Selectores.chapters)
            if not container_list_chapters:
                return []

            list_chapters = container_list_chapters.query_selector_all(
                Selectores.chapters_list
            )
            domain_page = urlparse(page.url).hostname
            urls = [
                f'https://{domain_page}{c.get_attribute(name="href")}'
                for c in list_chapters
            ]
            page.close

        return urls

    def get_chapter(self, url) -> NovelChapterModel:
        print(url)
        with sync_playwright() as p:
            browser = p.firefox.launch(headless=True)
            page = browser.new_page()
            page.goto(url, wait_until='networkidle')

            selector_title_chapter = page.wait_for_selector(Selectores.chapter_title)
            if not selector_title_chapter:
                assert Exception('Error')

            title_chapter = selector_title_chapter.text_content()

            get_num = re.match(r'Chapter\s+(\d+)', title_chapter)
            num_chapter = int(get_num.group(1))

            page.wait_for_selector(Selectores.chapter_body_paragraphs)
            paragraphs = page.locator(Selectores.chapter_paragraphs).all_inner_texts()
            clean_paragraphs = '\n\n'.join(paragraphs)

            browser.close()

            return NovelChapterModel(
                title=title_chapter,
                num_chapter=num_chapter,
                content=clean_paragraphs,
            )
