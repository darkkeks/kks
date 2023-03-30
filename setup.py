from setuptools import setup, find_packages
from kks import __version__


with open('README.md', 'r', encoding='utf-8') as f:
    readme = f.read()

setup(
    name='kokos',
    description='KoKoS helper tool',
    long_description=readme,
    long_description_content_type='text/markdown',
    author='Vyacheslav Boben',
    url='https://github.com/DarkKeks/kks',
    version=__version__,
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        'Click>=8', # TODO 8.1 when py3.6 support is dropped
        'requests>=2.27',  # TODO 2.28
        'configparser',
        'colorama',
        'tqdm',
        'beautifulsoup4',
        'html2text==2020.1.16',
        'pyyaml',
        "dataclasses;python_version<'3.7'",
        'setuptools',
    ],
    python_requires=">=3.6",
    entry_points='''
        [console_scripts]
        kks=kks.cli:cli
    ''',
)
