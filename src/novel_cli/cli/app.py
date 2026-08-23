from novel_cli.core.repository import RepostoryNovel, RepostoryNovelChapter
from novel_cli.core.scrapper import ScrapperNovelFire
from novel_cli.core.translate import Translate

repo_novel = RepostoryNovel()
repo_chapter = RepostoryNovelChapter()


def print_novels(r: RepostoryNovel):
    novels = r.get_all()
    for n in novels:
        print(n.id, n.title)


def print_novel_chapters(r: RepostoryNovelChapter, novel_id: int, limit: int = 20):
    chapters = r.get_all(novel_id=novel_id)
    if chapters:
        for c in chapters[:limit]:
            print(c.id, " - ", c.num_chapter, " - ", c.title.strip())


def print_novel_chapters_by_id(r: RepostoryNovelChapter, chapter_id: int):
    chapter = r.get_by_id(id=chapter_id)
    if chapter:
        return chapter


def main():
    print("NOVELAS")
    print_novels(repo_novel)
    print()
    print("CAPITULOS")
    print_novel_chapters(repo_chapter, 1, 29)
    print()
    print("INDIVIDUAL")
    chapter = print_novel_chapters_by_id(repo_chapter, 885)
    if chapter:
        print(chapter.id)
        print(chapter.title)
        # print(chapter)
        # print(chapter.content)
        print("TRADUCCIONES")
        Translate("cdsd").translate_novel(chapter.content.split("\n"))


if __name__ == "__main__":
    main()

# novel = 'https://novelfire.net/book/inner-voice-all-heroines-hear-my-inner-voice'
# scrapper = ScrapperNovelFire(novel)
# portada = scrapper.get_portada()
# pages_links_chapetrs = scrapper.get_chapters_pages(portada.url_chapter)

# print(portada, '\n')
# print(pages_links_chapetrs, '\n')

# chapter_urls = []
# print('\n---LINK NOVELAS---')
# for i, url in enumerate(pages_links_chapetrs, start=1):
#     print(f'\n{i}: {url}')
#     links = scrapper.get_chapters_links(url)
#     chapter_urls += links
#     # print(links[:4])
#     # sleep(20)

# print('\n---Capitulo---')
# chapter = scrapper.get_chapter(chapter_urls[1])
# print(chapter)
