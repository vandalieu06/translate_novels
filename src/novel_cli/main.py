from time import sleep

from novel_cli.decorators import calc_time
from novel_cli.origins import NovelFire as novelfire
from novel_cli.scrapping import ScrappingNovel


@calc_time
def extract_urls_chpaters(url: str):
    urls_chapters = ScrappingNovel().extract_pages_link(
        url, novelfire.container_filter, novelfire.filter_btn_next
    )
    urls_chapters_links = []
    for uc in urls_chapters:
        links = ScrappingNovel().extract_links_novel_chapters(
            uc, novelfire.container_chapters, novelfire.container_chapters_list
        )
        if links:
            urls_chapters_links += links
    return urls_chapters_links


@calc_time
def save_raw_chapters():
    url_novel = 'https://novelfire.net/book/inner-voice-all-heroines-hear-my-inner-voice/chapters'
    url_chapters = extract_urls_chpaters(url_novel)

    for i, url in enumerate(url_chapters):
        if (i + 1) % 50 == 0:
            print(f'End Bacth {(i + 1) / 50}')
            sleep(10)

        res = ScrappingNovel().extract_chapter(
            f'https://novelfire.net{url}',
            novelfire.chapter_title,
            novelfire.chapter_body_paragraphs,
            novelfire.chapter_paragraphs,
        )

        ScrappingNovel().save_chapter(
            novel_name='inner-voice-all-heroines-hear-my-inner-voice', res_novel=res
        )


def main():

    save_raw_chapters()


if __name__ == '__main__':
    main()
