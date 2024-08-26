from setuptools import setup, find_packages

setup(
    name="GraphMigrate",
    version="0.1",
    packages=find_packages(),
    install_requires=[
        "PyQt6",
        "psycopg2-binary",
        "neo4j",
        "pymongo",
        "pandas",
        "networkx",
        "matplotlib",
    ],
    entry_points={
        "console_scripts": [
            "graphmigrate=main:main",
        ],
    },
)

