from concurrent.interpreters import create
from os import path

from peewee import *

from novel_cli.database.db import Novel


class RepostoryNovel:
    db = SqliteDatabase(
        path.abspath('D:/developer/projects/translate-novels/db/novel_cli.db')
    )
    name: str = 'novel'

    def create(self, title: str, description: str, img: str):
        Novel.create(title=title, description=description, img=img)

    def get(self, title: str):
        return Novel.get(title=title)


repo_novel = RepostoryNovel()
# repo_novel.create(
#     title='Inner Voice: All Heroines Hear My Inner Voice',
#     description="""Reincarnated and traveling to another world, Eiji Seiya initially thought the world was normal. That was what he thought before he met the heroine and protagonist of the franchise he had watched in his previous life.

# Not only that, after he awakened the Inner Voice System to grow strong by complaining about plot, heroine and protagonist in his heart to get many rewards.

# He is determined to increase his power so that he can save his home world, the world where he was reincarnated that was hit by the disaster “Honkai” and save beautiful girls like Kiana, Mai, Bronya, Rita and others who had tragic endings in the original works!

# “I will save them all!”""",
#     img='https://novelfire.net/server-1/inner-voice-all-heroines-hear-my-inner-voice.jpg',
# )

novel = repo_novel.get(title='Inner Voice: All Heroines Hear My Inner Voice')
print(novel.title, '\n', novel.description, '\n', novel.img)
