from setuptools import setup, find_packages

setup(
    name='kokos',
    description='KoKoS helper tool',
    author='Vyacheslav Boben',
    version='1.0.3',
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        'Click',
        'requests',
        'configparser',
        'colorama',
        'tqdm',
        'beautifulsoup4',
    ],
    entry_points='''
        [console_scripts]
        kks=kks.cli:cli
    ''',
)
