class NovelFire:
    """
    Classe que define todas las etoquetas necesarias para procesar los capitulos de una novel en novelfire
    """

    container_chapters: str = '.novel-body.container #chpagedlist'
    container_chapters_list: str = '.chapter-list > li > a'
    container_filter: str = '#chpagedlist'
    filter_btn_next: str = '.page-item > .page-link[rel="next"]'
    chapter_title: str = '.chapter-title'
    chapter_body_paragraphs: str = '#chapter-container > #content'
    chapter_paragraphs: str = '#chapter-container > #content > p'
