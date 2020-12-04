from setuptools import setup, find_packages
from distutils.util import convert_path

ver_ns = {}
ver_path = convert_path('kks/__version__.py')
with open(ver_path) as file:
    exec(file.read(), ver_ns)

with open('README.md', 'r', encoding='utf-8') as f:
    readme = f.read()

setup(
    name='kokos',
    description='KoKoS helper tool',
    long_description=readme,
    long_description_content_type='text/markdown',
    author='Vyacheslav Boben',
    url='https://github.com/DarkKeks/kks',
    version=ver_ns['__version__'],
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        'Click',
        'requests',
        'configparser',
        'colorama',
        'tqdm',
        'beautifulsoup4',
        'html2text==2020.1.16',
        'pyyaml'
    ],
    entry_points='''
        [console_scripts]
        kks=kks.cli:cli
    ''',
)
