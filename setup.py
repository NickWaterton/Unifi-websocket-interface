import pathlib
from setuptools import setup, find_packages

HERE = pathlib.Path(__file__).parent

VERSION = '1.0'
PACKAGE_NAME = 'pyunifiwsi'
AUTHOR = 'Nick Waterton'
AUTHOR_EMAIL = 'nick.waterton@med.ge.com'
URL = 'https://github.com/NickWaterton/Unifi-websocket-interface'

LICENSE = 'GNU General Public License'
DESCRIPTION = 'A Websocket client for Unifi Controller and an example RPi based display program'
LONG_DESCRIPTION = (HERE / "README.md").read_text()
LONG_DESC_TYPE = "text/markdown"

INSTALL_REQUIRES = [
      'requests',
      'hjson',
      'bs4',
      'aiohttp',
      'asyncio',
]

setup(name=PACKAGE_NAME,
      version=VERSION,
      description=DESCRIPTION,
      long_description=LONG_DESCRIPTION,
      long_description_content_type=LONG_DESC_TYPE,
      author=AUTHOR,
      license=LICENSE,
      author_email=AUTHOR_EMAIL,
      url=URL,
      install_requires=INSTALL_REQUIRES,
      packages=find_packages()
      )