import os
from datetime import datetime
from os import path

from playwright.sync_api import sync_playwright


class ScrappingNovel:
    """
    Clsse parta extrapar capitulos de novelas
    De momento sin portada
    """

    base_dir: str = 'output'

    def __init__(self):
        pass

    def extract_pages_link(
        self,
        url: str,
        selector_filter: str,
        selector_btn_next: str,
    ) -> list[str]:
        urls: list[str] = []

        with sync_playwright() as p:
            browser = p.firefox.launch(headless=True)
            page = browser.new_page()
            page.goto(url, wait_until='networkidle')

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

    def extract_links_novel_chapters(
        self, url: str, container: str, container_links: str
    ) -> list:
        with sync_playwright() as p:
            browser = p.firefox.launch(headless=True)
            page = browser.new_page()
            page.goto(url, wait_until='networkidle')

            container_list_chapters = page.wait_for_selector(container)

            if not container_list_chapters:
                return []

            list_chapters = container_list_chapters.query_selector_all(container_links)
            urls = [c.get_attribute(name='href') for c in list_chapters]
            page.close

        return urls

    def extract_chapter(
        self, url, selector_title: str, selector_body: str, selector_paragraphs: str
    ) -> dict:
        with sync_playwright() as p:
            browser = p.firefox.launch(headless=True)
            page = browser.new_page()
            page.goto(url, wait_until='networkidle')

            selector_title_chapter = page.wait_for_selector(selector_title)
            if not selector_title_chapter:
                return {'error': 'not locator title chapter'}

            title_chapter = selector_title_chapter.text_content()

            page.wait_for_selector(selector_body)
            paragraphs = page.locator(selector_paragraphs).all_inner_texts()
            browser.close()

            response = {'title': title_chapter, 'content': paragraphs}

            return response

    def save_chapter(self, novel_name: str, res_novel: dict, dir: str = base_dir):
        dir_name = path.join(dir, novel_name)
        if not path.exists(dir_name):
            os.mkdir(dir_name)

        dir_name = path.join(dir_name, 'raw')
        if not path.exists(dir_name):
            os.mkdir(dir_name)

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename_chapter = res_novel['title'].split(':')[0].lower().replace(' ', '')
        output = path.join(dir_name, f'{filename_chapter}_{timestamp}.md')

        paragraphs: list = res_novel['content']
        paragraphs_format = '\n\n'.join(paragraphs)

        with open(output, 'w', encoding='utf-8') as f:
            f.write(f'## {res_novel["title"]}\n\n')
            f.write(paragraphs_format)
            f.close()
