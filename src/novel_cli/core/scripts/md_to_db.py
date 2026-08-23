from novel_cli.repository.novel import RepostoryNovel, RepostoryNovelChapter
from pathlib import Path

repo_novel = RepostoryNovel()
repo_novel_chapter = RepostoryNovelChapter()

novel_db = repo_novel.get_by_id(1)
novel_id = novel_db.id

path_novel = Path(
    "/home/jhonny/dev/projects/translate_novels/output/inner-voice-all-heroines-hear-my-inner-voice/raw"
)

for item in path_novel.iterdir():
    path_file = path_novel.joinpath(item.name)
    with open(path_file, "r", encoding="utf-8") as f:
        content = f.read()
        clean_content = content.split("\n\n")

        novel_title = clean_content[:1][0].replace("##", "")
        novel_content = "\n\n".join(clean_content[1:])
        repo_novel_chapter.add(
            novel_id=novel_id, title=novel_title, content=novel_content
        )
        print(novel_title)

# repo_novel.create(
#     title='Inner Voice: All Heroines Hear My Inner Voice',
#     description=inspect.cleandoc("""
#           Reincarnated and traveling to another world, Eiji Seiya initially thought the world was normal. That was what he thought before he met the heroine and protagonist of the franchise he had watched in his previous life.
#
#           Not only that, after he awakened the Inner Voice System to grow strong by complaining about plot, heroine and protagonist in his heart to get many rewards.
#           He is determined to increase his power so that he can save his home world, the world where he was reincarnated that was hit by the disaster “Honkai” and save beautiful girls like Kiana, Mai, Bronya, Rita and others who had tragic endings in the original works!
#
#           “I will save them all!”"""),
#     img='https://novelfire.net/server-1/inner-voice-all-heroines-hear-my-inner-voice.jpg',
# )

# novel = repo_novel.get(title='Inner Voice: All Heroines Hear My Inner Voice')
# print(novel.title, '\n', novel.description, '\n', novel.img)
